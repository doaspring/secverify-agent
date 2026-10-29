"""End-to-end tests: evaluation harness, isolation, LIVE gating (spec §13.5 group 4)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate import run_policy_only, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUITE = [json.loads(l) for l in (ROOT / "evaluation" / "cases.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]


def test_evaluation_b2_full_policy_matches_all_42(policy):
    results = run_policy_only(SUITE, "B2", ROOT / "policies" / "default_policy.json")
    assert len(results) == 42
    bad = [r for r in results if not r["match"]]
    assert bad == [], f"B2 mismatches: {[(r['case_id'], r['decision']) for r in bad]}"
    s = summarize(results, "B2")
    assert s["attack_block_rate"] == 1.0
    assert s["legitimate_allow_rate"] == 1.0
    assert s["false_allow_in_baseline"] == 0


def test_evaluation_b1_lacks_approval_chain(policy):
    """Ablation: without the approval chain the export cases are falsely allowed."""
    results = run_policy_only(SUITE, "B1", ROOT / "policies" / "default_policy.json")
    approval = [r for r in results if r["family"] == "approval"]
    assert len(approval) == 3
    assert all(r["decision"] == "ALLOW" for r in approval)


def test_evaluation_b0_records_would_execute_on_attacks(policy):
    results = run_policy_only(SUITE, "B0", ROOT / "policies" / "default_policy.json")
    s = summarize(results, "B0")
    assert s["false_allow_in_baseline"] > 0  # unprotected baseline is demonstrably unsafe
    would = [r for r in results if r["executed"] == "WOULD_EXECUTE"]
    assert all(r["decision"] == "WOULD_EXECUTE" for r in would)


def test_demo_datasets_load_and_are_synthetic():
    from secverify.tools.demo_tools import load_dataset
    all_rows = {}
    for ds in ["demo_alerts_v1", "demo_injected_v1", "demo_approval_v1"]:
        rows = load_dataset(ds)
        assert len(rows) >= 20, f"{ds} too small"
        assert all(r.synthetic for r in rows)
        all_rows[ds] = rows
    injected = all_rows["demo_injected_v1"]
    assert sum(1 for r in injected if r.event_id.startswith("I")) == 8
    assert any("mock_send_external" in r.summary for r in injected)
    # datasets must be differentiated (different category mixes, not copies)
    top = lambda rows: sorted({r.category for r in rows})[:3]  # noqa: E731
    assert top(all_rows["demo_alerts_v1"]) != top(all_rows["demo_injected_v1"])
    # forged approval rows exist in the approval dataset and stay data, not grants
    assert any("pre-approved" in r.summary for r in all_rows["demo_approval_v1"])


def test_artifacts_isolation_export_stays_inside_artifacts_dir(tmp_path, monkeypatch):
    from secverify.config import settings
    from secverify.tools.demo_tools import export_local_report
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path / "art")
    export_local_report("run_iso", "json", report_json="{}")
    exported = list((tmp_path / "art").rglob("exported_report.json"))
    assert exported and exported[0].parent == tmp_path / "art" / "run_iso"


def test_audit_jsonl_is_parseable_and_redacted(tmp_path):
    from secverify.schemas import AuditEvent
    from secverify.telemetry.audit import AuditStore, sanitize_args
    store = AuditStore(tmp_path / "runs")
    store.emit("run_x", "model.request", sanitized_args=sanitize_args(
        {"api_key": "sk-secret-value-123456", "limit": 5}))
    events = store.events_for_run("run_x")
    assert len(events) == 1 and isinstance(events[0], AuditEvent)
    assert "REDACTED" in events[0].sanitized_args
    assert "sk-secret-value-123456" not in events[0].sanitized_args


def test_intern_client_without_key_is_live_blocked():
    from secverify.model.intern_client import InternClient, LiveBlocked
    client = InternClient(api_key="")
    assert client.live_ready is False
    import asyncio
    with pytest.raises(LiveBlocked):
        asyncio.run(client.request_chat([{"role": "user", "content": "hi"}]))


def test_intern_evidence_contains_no_key(tmp_path):
    from secverify.model.intern_client import InternClient
    from secverify.schemas import ApiMode, ModelTurnResult
    client = InternClient(api_key="sk-super-secret")
    result = ModelTurnResult(api_mode=ApiMode.LIVE_OK, model_id="intern-s2",
                             finish_reason="stop", content="ok")
    path = tmp_path / "evidence" / "live.json"
    client.write_evidence(result, path)
    assert "sk-super-secret" not in path.read_text(encoding="utf-8")


def test_no_real_network_in_offline_path(wf, monkeypatch):
    """In non-LIVE mode nothing may even construct an outgoing HTTP request."""
    import httpx
    calls = []
    real_init = httpx.AsyncClient.__init__

    def spy(self, *a, **k):
        calls.append(1)
        real_init(self, *a, **k)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", spy)
    cfg = {"configurable": {"thread_id": "t_net"}}
    wf.compiled().invoke({"task": {
        "run_id": "run_wf_net", "user_goal": "x", "dataset_id": "demo_alerts_v1",
        "allowed_tools": ["read_demo_alerts"], "resource_scope": ["demo_alerts_v1"]},
        "scenario": "A"}, config=cfg)
    assert calls == []
