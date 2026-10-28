"""Deterministic PolicyEngine - the only source of ALLOW (spec §6).

Canonical decision order (V1.1 spec §6.2), first hit wins:
  R001_UNKNOWN_TOOL -> R002_FORBIDDEN_TOOL -> R003_INVALID_ARGUMENTS ->
  R004_NOT_AUTHORIZED -> R005_RESOURCE_OUT_OF_SCOPE -> R006_BUDGET_LIMIT ->
  R007_APPROVAL_REQUIRED -> R008_AUTHORIZED
Semantic (model-driven) tightening may only turn ALLOW into DENY/REQUIRE_APPROVAL
and must use R9xx_SEMANTIC_* rule ids. Any internal error fails closed (R000).
"""
from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any, Optional, Protocol
from uuid import uuid4

import json

from pydantic import BaseModel, Field, ValidationError

from secverify.schemas import (
    PolicyAction,
    PolicyDecision,
    TaskSpec,
    ToolRequest,
    sha256_of,
    utc_now_iso,
)
from secverify.security.tool_registry import TOOL_SCHEMA_VERSION, get_tool, registry

_APPROVAL_VALIDATE_COUNTER = itertools.count(1)


class RolePolicy(BaseModel):
    tools: list[str]
    resource_scope: list[str]
    require_approval: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    policy_version: str = "1.0"
    default_decision: str = "DENY"
    roles: dict[str, RolePolicy]
    forbidden_tools: list[str] = Field(default_factory=list)
    network_egress_enabled: bool = False
    max_tool_calls_per_run: int = 12
    max_rows_per_read: int = 100
    approval_ttl_seconds: int = 300


def load_policy(path: Path) -> Policy:
    return Policy.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


class BudgetTracker(Protocol):
    def executed_calls(self, run_id: str) -> int: ...


class ApprovalCheck(Protocol):
    def approval_matches(self, req: ToolRequest, policy_version: str) -> bool: ...


class PolicyEngine:
    def __init__(self, policy: Policy, budget: BudgetTracker, approvals: ApprovalCheck):
        self.policy = policy
        self.budget = budget
        self.approvals = approvals

    # -- capability intersection (spec §6.1): TaskSpec ∩ role, LLM never writes it
    def effective_capabilities(self, task: TaskSpec) -> set[str]:
        role = self.policy.roles.get(task.actor_role)
        if role is None:
            return set()
        return set(role.tools) & set(task.allowed_tools)

    def _decide(
        self, req: ToolRequest, action: PolicyAction, rule: str, reason: str,
        approval_required: bool = False,
    ) -> PolicyDecision:
        return PolicyDecision(
            decision_id=f"dec_{uuid4().hex[:10]}",
            run_id=req.run_id,
            call_id=req.call_id,
            action=action,
            rule_ids=[rule],
            reason=reason,
            approval_required=approval_required,
            policy_version=self.policy.policy_version,
            source_segment_ids=req.source_segment_ids,
        )

    def enforce(self, req: ToolRequest, task: TaskSpec) -> PolicyDecision:
        try:
            return self._enforce(req, task)
        except Exception as exc:  # fail closed (spec §6.3, G1)
            return self._decide(
                req, PolicyAction.DENY, "R000_POLICY_INTERNAL_ERROR",
                f"policy engine internal error, failing closed: {type(exc).__name__}",
            )

    def _enforce(self, req: ToolRequest, task: TaskSpec) -> PolicyDecision:
        # 1. fixed ToolRegistry membership (schema pinning)
        spec = get_tool(req.tool_name)
        if spec is None:
            return self._decide(req, PolicyAction.DENY, "R001_UNKNOWN_TOOL",
                                "工具不在固定ToolRegistry内")
        # 2. forbidden tools / egress - name-level deny, no arg parsing needed
        if req.tool_name in self.policy.forbidden_tools:
            return self._decide(req, PolicyAction.DENY, "R002_FORBIDDEN_TOOL",
                                "禁止工具：任何日志、工具输出或模型文字都不能授权外发/删除")
        if spec.category == "decoy":
            return self._decide(req, PolicyAction.DENY, "R002_FORBIDDEN_TOOL",
                                "诱捕工具永远拒绝且无真实副作用")
        if self.policy.network_egress_enabled is False and req.tool_name in {"mock_send_external"}:
            return self._decide(req, PolicyAction.DENY, "R002_FORBIDDEN_TOOL",
                                "network_egress_enabled=false")
        # 3. argument validation (schema shape); numeric caps are policy's job (R006)
        try:
            parsed = spec.schema.model_validate(req.arguments)
        except ValidationError:
            return self._decide(req, PolicyAction.DENY, "R003_INVALID_ARGUMENTS",
                                "参数未通过固定schema校验（枚举、格式或长度非法），fail-closed")
        # 4. TaskSpec.allowed_tools ∩ role capabilities
        if req.tool_name not in self.effective_capabilities(task):
            return self._decide(req, PolicyAction.DENY, "R004_NOT_AUTHORIZED",
                                "工具不在本次任务授权与角色能力交集内")
        # 5. resource scope: dataset_id enum membership / run_id ownership
        scope_msg = self._resource_in_scope(parsed, task)
        if scope_msg is not None:
            return self._decide(req, PolicyAction.DENY, "R005_RESOURCE_OUT_OF_SCOPE", scope_msg)
        # 6. budget and parameter caps
        if self.budget.executed_calls(req.run_id) >= self.policy.max_tool_calls_per_run:
            return self._decide(req, PolicyAction.DENY, "R006_BUDGET_LIMIT",
                                f"超过单次运行工具调用上限{self.policy.max_tool_calls_per_run}")
        cap = getattr(parsed, "limit", None)
        if cap is not None and cap > self.policy.max_rows_per_read:
            return self._decide(req, PolicyAction.DENY, "R006_BUDGET_LIMIT",
                                f"limit={cap}超过max_rows_per_read={self.policy.max_rows_per_read}")
        # 7. approval gate - token bound to run_id + canonical(tool,args) + version,
        #    single use; model self-claims never create tokens
        if req.tool_name in self.policy.roles[task.actor_role].require_approval \
                or req.tool_name in task.require_approval:
            if not self.approvals.approval_matches(req, self.policy.policy_version):
                return self._decide(req, PolicyAction.REQUIRE_APPROVAL, "R007_APPROVAL_REQUIRED",
                                    "敏感导出需人工审批；审批令牌单次有效且绑定当前参数",
                                    approval_required=True)
        # 8. allow
        return self._decide(req, PolicyAction.ALLOW, "R008_AUTHORIZED",
                            "已授权工具且资源在演示范围内，允许沙盒内执行")

    def _resource_in_scope(self, parsed: BaseModel, task: TaskSpec) -> Optional[str]:
        dataset_id = getattr(parsed, "dataset_id", None)
        if dataset_id is not None and dataset_id not in task.resource_scope:
            return f"数据集{dataset_id}不在本次任务resource_scope内"
        run_id_arg = getattr(parsed, "run_id", None)
        if run_id_arg is not None and run_id_arg != task.run_id:
            return f"run_id={run_id_arg}不属于当前运行，禁止跨运行读取/写入"
        return None


class InMemoryBudget:
    """Counts EXECUTED calls per run (denied proposals do not consume budget)."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def executed_calls(self, run_id: str) -> int:
        return self._counts.get(run_id, 0)

    def increment(self, run_id: str) -> None:
        self._counts[run_id] = self._counts.get(run_id, 0) + 1

    def reset(self, run_id: str) -> None:
        self._counts.pop(run_id, None)


def semantic_tighten(
    decision: PolicyDecision, new_action: PolicyAction, rule: str, reason: str
) -> PolicyDecision:
    """SemanticRiskReviewer hook: may only tighten ALLOW (spec §6.2)."""
    if decision.action == PolicyAction.ALLOW and new_action != PolicyAction.ALLOW:
        return decision.model_copy(
            update={"action": new_action, "rule_ids": decision.rule_ids + [rule], "reason": reason}
        )
    return decision
