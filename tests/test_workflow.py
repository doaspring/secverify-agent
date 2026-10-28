"""LangGraph workflow tests - spec §13.5 group 1 (interrupt, branches, states)."""
from __future__ import annotations

import pytest
from langgraph.types import Command

from secverify.config import settings
from secverify.schemas import ApiMode, TaskSpec
from secverify.workflow.graph import SecVerifyWorkflow


@pytest.fixture
def wf(tmp_path):
    return SecVerifyWorkflow(runs_dir=tmp_path / "runs")


def task_for(scenario: str, run_id: str) -> TaskSpec:
    ds = {"A": "demo_alerts_v1", "B": "demo_injected_v1", "C": "demo_approval_v1"}[scenario]
    return TaskSpec(
        run_id=run_id, user_goal="demo", dataset_id=ds,
        allowed_tools=["read_demo_alerts", "search_demo_alerts", "aggregate_alerts",
                       "generate_local_report", "export_local_report"],
        resource_scope=["demo_alerts_v1", "demo_injected_v1", "demo_approval_v1"],
    )


def run(wf, scenario, run_id, cfg):
    return wf.compiled().invoke({"task": task_for(scenario, run_id).model_dump(),
                                 "scenario": scenario}, config=cfg)


def test_scenario_a_completes(wf):
    cfg = {"configurable": {"thread_id": "t_a"}}
    final = run(wf, "A", "run_wf_a", cfg)
    assert final["run_status"] == "COMPLETED"
    assert final["executed_count"] == 3 and final["blocked_count"] == 0


def test_scenario_b_blocks_and_continues_original_task(wf):
    cfg = {"configurable": {"thread_id": "t_b"}}
    final = run(wf, "B", "run_wf_b", cfg)
    tools = [(t["tool"], t["action"], t["status"]) for t in final["timeline"]]
    assert ("mock_send_external", "DENY", "NOT_EXECUTED") in tools
    # task continuation after block (§13.3 metric 7): aggregate + report still run
    assert ("aggregate_alerts", "ALLOW", "EXECUTED") in tools
    assert ("generate_local_report", "ALLOW", "EXECUTED") in tools
    assert final["blocked_count"] == 1 and final["executed_count"] == 3
    assert "阻断后原任务仍安全完成" in final["final_answer"]


def test_scenario_c_interrupts_for_approval(wf):
    cfg = {"configurable": {"thread_id": "t_c"}}
    partial = run(wf, "C", "run_wf_c", cfg)
    assert partial["run_status"] == "WAIT_APPROVAL"
    snap = wf.compiled().get_state(cfg)
    assert snap.next == ("request_approval",)
    intr = snap.tasks[0].interrupts[0].value
    assert intr["tool"] == "export_local_report"
    assert intr["arguments"]["export_format"] == "json"


def test_scenario_c_approval_executes_export(wf):
    cfg = {"configurable": {"thread_id": "t_c2"}}
    run(wf, "C", "run_wf_c2", cfg)
    final = wf.compiled().invoke(Command(resume={"approved": True}), config=cfg)
    assert final["run_status"] == "COMPLETED"
    statuses = {t["status"] for t in final["timeline"]}
    assert "EXECUTED" in statuses
    exported = settings.artifacts_dir / "run_wf_c2" / "exported_report.json"
    assert exported.exists()


def test_scenario_c_rejection_writes_nothing(wf):
    cfg = {"configurable": {"thread_id": "t_c3"}}
    run(wf, "C", "run_wf_c3", cfg)
    final = wf.compiled().invoke(Command(resume={"approved": False}), config=cfg)
    actions = [t["action"] for t in final["timeline"]]
    assert "REJECTED_BY_USER" in actions
    assert not (settings.artifacts_dir / "run_wf_c3" / "exported_report.json").exists()


def test_offline_runs_are_labelled_demo_replay(wf):
    cfg = {"configurable": {"thread_id": "t_mode"}}
    final = run(wf, "A", "run_wf_mode", cfg)
    assert final["api_mode"] in (ApiMode.DEMO_REPLAY.value, ApiMode.LIVE_BLOCKED.value)
    assert "DEMO_REPLAY" in final["api_detail"] or "LIVE_BLOCKED" in final["api_detail"]


def test_audit_chain_complete_for_run(wf):
    cfg = {"configurable": {"thread_id": "t_audit"}}
    run(wf, "B", "run_wf_audit", cfg)
    events = wf.audit.events_for_run("run_wf_audit")
    types = {e.event_type for e in events}
    assert {"run.created", "model.tool_proposed", "policy.decision",
            "tool.executed", "tool.denied", "run.completed"} <= types
    for e in events:  # trace completeness (§13.3 metric 6)
        assert e.event_id and e.utc_timestamp


def test_report_generated_in_artifacts(wf):
    cfg = {"configurable": {"thread_id": "t_rep"}}
    run(wf, "A", "run_wf_rep", cfg)
    out = settings.artifacts_dir / "run_wf_rep"
    assert (out / "report.html").exists() and (out / "report.json").exists()
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "mock_send_external" not in html or "DENY" in html  # no false execution claims
    assert "append-only" in html


def test_provenance_records_run_segments(wf):
    cfg = {"configurable": {"thread_id": "t_prov"}}
    run(wf, "A", "run_wf_prov", cfg)
    segs = wf.provenance.segments_for_run("run_wf_prov")
    labels = {s.trust_label.value for s in segs}
    assert "USER_INSTRUCTION" in labels and "UNTRUSTED_LOG" in labels
    assert "MODEL_DERIVED" in labels
