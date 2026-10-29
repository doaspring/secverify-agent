"""Shared fixtures: artifacts isolation + fresh workflow per test."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secverify.config import settings  # noqa: E402
from secverify.schemas import TaskSpec  # noqa: E402
from secverify.security.policy_engine import InMemoryBudget, PolicyEngine, load_policy  # noqa: E402
from secverify.workflow.approval import ApprovalStore  # noqa: E402

ALLOWED = ["read_demo_alerts", "search_demo_alerts", "aggregate_alerts",
           "generate_local_report", "export_local_report"]
SCOPE = ["demo_alerts_v1", "demo_injected_v1", "demo_approval_v1"]


@pytest.fixture(autouse=True)
def isolate_artifacts(tmp_path, monkeypatch):
    """Never let tests write into the real project artifacts dir, and never
    let a real .env API key turn unit tests into LIVE calls."""
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path / "artifacts")
    monkeypatch.setattr(settings, "intern_api_key", "")
    monkeypatch.setattr(settings, "execution_mode", "DEMO_REPLAY")
    yield


@pytest.fixture
def policy():
    return load_policy(Path(__file__).resolve().parents[1] / "policies" / "default_policy.json")


@pytest.fixture
def approvals(policy):
    return ApprovalStore(ttl_seconds=policy.approval_ttl_seconds)


@pytest.fixture
def engine(policy, approvals):
    return PolicyEngine(policy, InMemoryBudget(), approvals)


@pytest.fixture
def make_task():
    def _make(**overrides) -> TaskSpec:
        base = dict(
            run_id="run_test",
            user_goal="汇总演示告警",
            dataset_id="demo_alerts_v1",
            allowed_tools=list(ALLOWED),
            resource_scope=list(SCOPE),
        )
        base.update(overrides)
        return TaskSpec(**base)
    return _make


@pytest.fixture
def make_request():
    from secverify.schemas import ToolRequest

    def _make(tool_name: str, arguments: dict, call_id: str = "call_test") -> ToolRequest:
        return ToolRequest(run_id="run_test", call_id=call_id,
                           tool_name=tool_name, arguments=arguments)
    return _make


@pytest.fixture
def wf(tmp_path):
    from secverify.workflow.graph import SecVerifyWorkflow
    return SecVerifyWorkflow(runs_dir=tmp_path / "runs")
