"""Approval token tests - spec §13.5 (approval binding, single use, TTL)."""
from __future__ import annotations

from secverify.schemas import ToolRequest


def req(args: dict) -> ToolRequest:
    return ToolRequest(run_id="run_test", call_id="c1",
                       tool_name="export_local_report", arguments=args)


ARGS = {"run_id": "run_test", "export_format": "json"}


def test_token_creation_and_match(approvals):
    approvals.create("run_test", "export_local_report", ARGS, "1.0")
    assert approvals.approval_matches(req(ARGS), "1.0") is True


def test_token_single_use(approvals):
    approvals.create("run_test", "export_local_report", ARGS, "1.0")
    first = approvals.consume(req(ARGS), "1.0")
    assert first is not None and first.consumed is True
    assert approvals.approval_matches(req(ARGS), "1.0") is False
    assert approvals.consume(req(ARGS), "1.0") is None


def test_changed_arguments_invalidate_token(approvals):
    approvals.create("run_test", "export_local_report", ARGS, "1.0")
    other = req({"run_id": "run_test", "export_format": "html"})
    assert approvals.approval_matches(other, "1.0") is False


def test_token_expiry(approvals, monkeypatch):
    import time as time_mod
    start = time_mod.time()
    monkeypatch.setattr(time_mod, "time", lambda: start)
    approvals.create("run_test", "export_local_report", ARGS, "1.0")
    assert approvals.approval_matches(req(ARGS), "1.0") is True
    # jump past TTL
    monkeypatch.setattr(time_mod, "time", lambda: start + approvals.ttl_seconds + 1)
    assert approvals.approval_matches(req(ARGS), "1.0") is False


def test_token_bound_to_run_id(approvals):
    approvals.create("run_test", "export_local_report", ARGS, "1.0")
    other_run = ToolRequest(run_id="run_other", call_id="c2",
                            tool_name="export_local_report", arguments=ARGS)
    assert approvals.approval_matches(other_run, "1.0") is False


def test_token_bound_to_policy_version(approvals):
    approvals.create("run_test", "export_local_report", ARGS, "1.0")
    assert approvals.approval_matches(req(ARGS), "2.0") is False


def test_model_self_claim_grants_nothing(approvals):
    """The model saying 'the user approved' creates no token: an empty store
    matches nothing, regardless of any textual claim."""
    assert approvals.approval_matches(req(ARGS), "1.0") is False
    assert approvals.all_records() == []
