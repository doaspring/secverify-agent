"""ToolGateway - the SECOND, mandatory enforcement point (spec §4).

LangGraph nodes calling tools always go through execute(). The gateway re-runs
the deterministic policy engine on every call even if a node already checked:
the node-level check is UX, the gateway check is the security boundary.
Approved REQUIRE_APPROVAL calls consume their single-use token here.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from secverify.schemas import (
    ExecutionStatus,
    PolicyAction,
    PolicyDecision,
    TaskSpec,
    ToolRequest,
    sha256_of,
)
from secverify.security.policy_engine import InMemoryBudget, PolicyEngine
from secverify.security.tool_registry import get_tool
from secverify.telemetry.audit import AuditStore, sanitize_args
from secverify.tools.demo_tools import TOOL_IMPLEMENTATIONS, ToolResult
from secverify.workflow.approval import ApprovalStore


class GatewayOutcome(BaseModel):
    decision: PolicyDecision
    result: Optional[ToolResult] = None
    execution_status: ExecutionStatus

    @property
    def executed(self) -> bool:
        return self.execution_status == ExecutionStatus.EXECUTED


class ToolGateway:
    def __init__(
        self,
        engine: PolicyEngine,
        budget: InMemoryBudget,
        approvals: ApprovalStore,
        audit: AuditStore,
        report_provider=None,
    ):
        self.engine = engine
        self.budget = budget
        self.approvals = approvals
        self.audit = audit
        # report_provider(run_id) -> (html, json) lets report tools embed the
        # real run summary instead of a placeholder
        self.report_provider = report_provider

    def execute(
        self,
        req: ToolRequest,
        task: TaskSpec,
        *,
        node: str = "tool_gateway",
        pre_checked_decision: Optional[PolicyDecision] = None,
    ) -> GatewayOutcome:
        started = time.perf_counter()

        # ---- mandatory second enforcement, regardless of node-level check ----
        decision = self.engine.enforce(req, task)
        if pre_checked_decision is not None \
                and pre_checked_decision.action == PolicyAction.REQUIRE_APPROVAL:
            # this call came through the approval execution path: the gateway
            # consumes the single-use token right before executing; a missing,
            # consumed or expired token (replay) is an outright DENY here
            consumed = self.approvals.consume(req, decision.policy_version) \
                if decision.action == PolicyAction.ALLOW else None
            if consumed is None:
                decision = PolicyDecision(
                    decision_id=decision.decision_id,
                    run_id=req.run_id,
                    call_id=req.call_id,
                    action=PolicyAction.DENY,
                    rule_ids=["R007_APPROVAL_REQUIRED"],
                    reason="审批令牌不存在/已用尽/已过期，拒绝执行（单次有效）",
                    approval_required=True,
                    policy_version=decision.policy_version,
                    source_segment_ids=req.source_segment_ids,
                )

        latency = (time.perf_counter() - started) * 1000
        args_text = sanitize_args(req.arguments)

        if decision.action == PolicyAction.DENY:
            self.audit.emit(
                req.run_id, "tool.denied", node=node, tool_call_id=req.call_id,
                proposed_tool=req.tool_name, policy_action=decision.action.value,
                rule_ids=decision.rule_ids, sanitized_args=args_text,
                latency_ms=latency, execution_status=ExecutionStatus.NOT_EXECUTED.value,
                source_ids=req.source_segment_ids,
                detail={"reason": decision.reason, "requested_by": req.requested_by},
            )
            return GatewayOutcome(decision=decision, execution_status=ExecutionStatus.NOT_EXECUTED)

        if decision.action == PolicyAction.REQUIRE_APPROVAL:
            self.audit.emit(
                req.run_id, "approval.wait", node=node, tool_call_id=req.call_id,
                proposed_tool=req.tool_name, policy_action=decision.action.value,
                rule_ids=decision.rule_ids, sanitized_args=args_text,
                latency_ms=latency, execution_status=ExecutionStatus.WAIT_FOR_APPROVAL.value,
                source_ids=req.source_segment_ids, detail={"reason": decision.reason},
            )
            return GatewayOutcome(decision=decision, execution_status=ExecutionStatus.WAIT_FOR_APPROVAL)

        # ---- ALLOW: dispatch to the sandboxed implementation ----
        impl = TOOL_IMPLEMENTATIONS.get(req.tool_name)
        if impl is None:  # defensive: registry and impl table must stay aligned
            self.audit.emit(
                req.run_id, "tool.denied", node=node, tool_call_id=req.call_id,
                proposed_tool=req.tool_name, policy_action=PolicyAction.DENY.value,
                rule_ids=["R001_UNKNOWN_TOOL"], sanitized_args=args_text,
                latency_ms=latency, execution_status=ExecutionStatus.NOT_EXECUTED.value,
                detail={"reason": "no implementation registered"},
            )
            return GatewayOutcome(
                decision=decision.model_copy(
                    update={"action": PolicyAction.DENY, "rule_ids": ["R001_UNKNOWN_TOOL"]}
                ),
                execution_status=ExecutionStatus.NOT_EXECUTED,
            )

        started_exec = time.perf_counter()
        kwargs = dict(req.arguments)
        if req.tool_name in {"generate_local_report", "export_local_report"} \
                and self.report_provider is not None:
            html, jsn = self.report_provider(req.run_id)
            kwargs.setdefault("report_html", html)
            kwargs.setdefault("report_json", jsn)
        result: ToolResult = impl(**kwargs)
        exec_latency = (time.perf_counter() - started_exec) * 1000

        status = ExecutionStatus.SIMULATED_ONLY if result.execution_status == "SIMULATED_ONLY" \
            else ExecutionStatus.EXECUTED
        if status == ExecutionStatus.EXECUTED:
            self.budget.increment(req.run_id)

        self.audit.emit(
            req.run_id, "tool.executed", node=node, tool_call_id=req.call_id,
            proposed_tool=req.tool_name, policy_action=decision.action.value,
            rule_ids=decision.rule_ids, sanitized_args=args_text,
            latency_ms=exec_latency, execution_status=status.value,
            output_hash=sha256_of(result.summary),
            source_ids=req.source_segment_ids,
            detail={"summary": result.summary[:200], "output_path": result.output_path},
        )
        return GatewayOutcome(decision=decision, result=result, execution_status=status)
