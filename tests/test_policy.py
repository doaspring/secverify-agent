"""Policy engine tests - spec §13.5 group 2 (deterministic enforcement)."""
from __future__ import annotations

import pytest

from secverify.schemas import PolicyAction
from secverify.security.policy_engine import semantic_tighten


def decide(engine, req, task):
    return engine.enforce(req, task)


# ---------------------------------------------------------------- allow path
def test_allow_whitelisted_read(engine, make_task, make_request):
    d = decide(engine, make_request("read_demo_alerts", {"dataset_id": "demo_alerts_v1", "limit": 25}), make_task())
    assert d.action == PolicyAction.ALLOW
    assert d.rule_ids == ["R008_AUTHORIZED"]


# ----------------------------------------------------------------- deny path
def test_forbidden_tool_denied(engine, make_task, make_request):
    d = decide(engine, make_request("mock_send_external",
                                    {"destination_id": "demo_sink", "payload_ref": "x"}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R002_FORBIDDEN_TOOL"])


def test_decoy_delete_denied_regardless_of_role_claim(engine, make_task, make_request):
    d = decide(engine, make_request("mock_delete_all", {"dataset_id": "demo_alerts_v1"}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R002_FORBIDDEN_TOOL"])


def test_unknown_tool_r001(engine, make_task, make_request):
    d = decide(engine, make_request("shell_exec", {"cmd": "ls"}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R001_UNKNOWN_TOOL"])


def test_not_in_taskspec_r004(engine, make_task, make_request):
    task = make_task(allowed_tools=["read_demo_alerts"])  # aggregate not granted
    d = decide(engine, make_request("aggregate_alerts", {"dataset_id": "demo_alerts_v1", "group_by": "severity"}), task)
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R004_NOT_AUTHORIZED"])


def test_resource_out_of_scope_r005(engine, make_task, make_request):
    task = make_task(resource_scope=["demo_alerts_v1"])
    d = decide(engine, make_request("read_demo_alerts", {"dataset_id": "demo_approval_v1", "limit": 5}), task)
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R005_RESOURCE_OUT_OF_SCOPE"])


def test_invalid_dataset_enum_r003(engine, make_task, make_request):
    d = decide(engine, make_request("read_demo_alerts", {"dataset_id": "not_granted_1", "limit": 5}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R003_INVALID_ARGUMENTS"])


def test_limit_over_cap_r006(engine, make_task, make_request):
    d = decide(engine, make_request("read_demo_alerts", {"dataset_id": "demo_alerts_v1", "limit": 500}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R006_BUDGET_LIMIT"])


def test_negative_limit_r003(engine, make_task, make_request):
    d = decide(engine, make_request("read_demo_alerts", {"dataset_id": "demo_alerts_v1", "limit": -1}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R003_INVALID_ARGUMENTS"])


def test_run_id_traversal_r003(engine, make_task, make_request):
    d = decide(engine, make_request("generate_local_report", {"run_id": "../root"}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R003_INVALID_ARGUMENTS"])


def test_cross_run_reference_r005(engine, make_task, make_request):
    d = decide(engine, make_request("export_local_report",
                                    {"run_id": "run_other", "export_format": "json"}), make_task())
    assert d.rule_ids == ["R005_RESOURCE_OUT_OF_SCOPE"]


def test_budget_exceeded_r006(engine, policy, make_task, make_request):
    class Full:
        def executed_calls(self, run_id):
            return policy.max_tool_calls_per_run

    full_engine = engine.__class__(policy, Full(), engine.approvals)
    d = decide(full_engine, make_request("read_demo_alerts", {"dataset_id": "demo_alerts_v1", "limit": 5}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.DENY, ["R006_BUDGET_LIMIT"])


# ------------------------------------------------------------- approval gate
def test_export_requires_approval_r007(engine, make_task, make_request):
    d = decide(engine, make_request("export_local_report",
                                    {"run_id": "run_test", "export_format": "json"}), make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.REQUIRE_APPROVAL, ["R007_APPROVAL_REQUIRED"])
    assert d.approval_required is True


def test_export_with_valid_token_allows(engine, approvals, make_task, make_request):
    req = make_request("export_local_report", {"run_id": "run_test", "export_format": "json"})
    approvals.create("run_test", "export_local_report", req.arguments, engine.policy.policy_version)
    d = decide(engine, req, make_task())
    assert (d.action, d.rule_ids) == (PolicyAction.ALLOW, ["R008_AUTHORIZED"])


# ------------------------------------------------------ order & fail-closed
def test_rule_order_forbidden_before_invalid_args(engine, make_task, make_request):
    """A forbidden tool with garbage args must report R002, not R003."""
    d = decide(engine, make_request("mock_send_external", {"garbage": True}), make_task())
    assert d.rule_ids == ["R002_FORBIDDEN_TOOL"]


def test_internal_error_fails_closed(engine, make_task, make_request, monkeypatch):
    from secverify.security import policy_engine as pe

    def boom(self, req, task):
        raise RuntimeError("simulated engine bug")

    monkeypatch.setattr(pe.PolicyEngine, "_enforce", boom)
    d = decide(engine, make_request("read_demo_alerts", {"dataset_id": "demo_alerts_v1", "limit": 5}), make_task())
    assert d.action == PolicyAction.DENY
    assert d.rule_ids == ["R000_POLICY_INTERNAL_ERROR"]


def test_semantic_tighten_only_tightens(engine, make_task, make_request):
    from secverify.schemas import PolicyDecision

    allow = PolicyDecision(decision_id="d", run_id="r", call_id="c", action=PolicyAction.ALLOW,
                           rule_ids=["R008_AUTHORIZED"], reason="", policy_version="1.0")
    tightened = semantic_tighten(allow, PolicyAction.DENY, "R901_SEMANTIC_SUSPECT", "suspicious")
    assert tightened.action == PolicyAction.DENY and "R901_SEMANTIC_SUSPECT" in tightened.rule_ids
    # cannot loosen a DENY
    deny = allow.model_copy(update={"action": PolicyAction.DENY})
    assert semantic_tighten(deny, PolicyAction.ALLOW, "R902", "x").action == PolicyAction.DENY
