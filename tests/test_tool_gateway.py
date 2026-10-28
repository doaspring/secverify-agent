"""ToolGateway tests - spec §13.5 (second enforcement point, sandbox)."""
from __future__ import annotations

import pytest

from secverify.schemas import ExecutionStatus, PolicyAction
from secverify.security.policy_engine import InMemoryBudget, PolicyEngine
from secverify.security.tool_gateway import ToolGateway
from secverify.telemetry.audit import AuditStore
from secverify.tools.demo_tools import mock_delete_all, mock_send_external


@pytest.fixture
def gateway(policy, approvals, tmp_path):
    budget = InMemoryBudget()
    engine = PolicyEngine(policy, budget, approvals)
    audit = AuditStore(tmp_path / "runs")
    return ToolGateway(engine, budget, approvals, audit), audit, budget


def test_gateway_reenforces_even_if_node_checked(gateway, make_task, make_request):
    """A node may believe a call is fine; the gateway is the security boundary."""
    gw, audit, _ = gateway
    req = make_request("mock_send_external", {"destination_id": "x", "payload_ref": "y"})
    outcome = gw.execute(req, make_task(), pre_checked_decision=None)
    assert outcome.decision.action == PolicyAction.DENY
    assert outcome.execution_status == ExecutionStatus.NOT_EXECUTED


def test_read_returns_synthetic_data(gateway, make_task, make_request):
    gw, _, _ = gateway
    outcome = gw.execute(make_request("read_demo_alerts",
                                      {"dataset_id": "demo_alerts_v1", "limit": 4}), make_task())
    assert outcome.executed and outcome.result.ok
    assert len(outcome.result.data["rows"]) == 4


def test_aggregate_is_deterministic(gateway, make_task, make_request):
    gw, _, _ = gateway
    args = {"dataset_id": "demo_alerts_v1", "group_by": "severity"}
    a = gw.execute(make_request("aggregate_alerts", args), make_task())
    b = gw.execute(make_request("aggregate_alerts", args), make_task())
    assert a.result.data["counts"] == b.result.data["counts"]
    assert a.result.data["counts"]["high"] == 2  # demo_alerts_v1 fixture


def test_export_without_approval_waits_and_writes_nothing(gateway, make_task, make_request):
    gw, _, _ = gateway
    outcome = gw.execute(make_request("export_local_report",
                                      {"run_id": "run_test", "export_format": "json"}), make_task())
    assert outcome.execution_status == ExecutionStatus.WAIT_FOR_APPROVAL
    assert outcome.result is None


def test_export_after_approval_executes_once_then_token_dead(gateway, make_task, make_request, approvals):
    gw, _, _ = gateway
    req = make_request("export_local_report", {"run_id": "run_test", "export_format": "json"})
    from secverify.schemas import PolicyDecision
    pre = PolicyDecision(decision_id="d", run_id="run_test", call_id=req.call_id,
                         action=PolicyAction.REQUIRE_APPROVAL, rule_ids=["R007_APPROVAL_REQUIRED"],
                         reason="", policy_version="1.0")
    approvals.create("run_test", "export_local_report", req.arguments, "1.0")
    first = gw.execute(req, make_task(), pre_checked_decision=pre)
    assert first.executed
    from secverify.config import settings
    exported = settings.artifacts_dir / "run_test" / "exported_report.json"
    assert exported.exists()
    # second attempt with the same (consumed) token must be denied
    second = gw.execute(req, make_task(), pre_checked_decision=pre)
    assert second.decision.action == PolicyAction.DENY
    assert "R007" in second.decision.rule_ids[0]


def test_audit_records_executed_and_denied(gateway, make_task, make_request):
    gw, audit, _ = gateway
    gw.execute(make_request("read_demo_alerts", {"dataset_id": "demo_alerts_v1", "limit": 2}), make_task())
    gw.execute(make_request("mock_delete_all", {"dataset_id": "demo_alerts_v1"}), make_task())
    events = audit.events_for_run("run_test")
    types = {e.event_type for e in events}
    assert {"tool.executed", "tool.denied"} <= types
    denied = [e for e in events if e.event_type == "tool.denied"][0]
    assert denied.rule_ids == ["R002_FORBIDDEN_TOOL"]
    assert denied.execution_status == "NOT_EXECUTED"


def test_decoy_implementations_have_no_side_effects():
    """Even calling the decoy implementations directly changes nothing."""
    out_send = mock_send_external("demo_sink", "x")
    out_del = mock_delete_all("demo_alerts_v1")
    assert out_send.execution_status == out_del.execution_status == "SIMULATED_ONLY"
    assert out_send.ok is False and out_del.ok is False
