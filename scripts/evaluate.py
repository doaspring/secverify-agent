#!/usr/bin/env python3
"""Deterministic (policy-only) evaluation over evaluation/cases.jsonl (spec §13).

Baselines:
  B2  full SecVerify policy (R001-R008)
  B1  static allowlist only: registry + schema + TaskSpec∩role + resource scope
      (NO approval chain, NO budget caps, NO forbidden-tool decoy handling)
  B0  no protection: everything a registered tool would run is recorded as
      WOULD_EXECUTE (never actually executed for sensitive ops - all ops stay
      simulated/offline in this harness).

The `live` mode replays the same suite through the real Intern-S2 planner and
requires INTERN_API_KEY; without it the run is recorded LIVE_BLOCKED and no
LIVE claims may be made from its output.

Usage:
  python scripts/evaluate.py --mode policy-only --baseline B2 \
      --suite evaluation/cases.jsonl --output evaluation/results/policy_only_B2.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secverify.schemas import (  # noqa: E402
    ExecutionStatus,
    PolicyAction,
    TaskSpec,
    ToolRequest,
)
from secverify.security.policy_engine import (  # noqa: E402
    InMemoryBudget,
    PolicyEngine,
    load_policy,
)
from secverify.security.tool_registry import get_tool  # noqa: E402
from secverify.workflow.approval import ApprovalStore  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
READ_TOOLS = {"read_demo_alerts", "search_demo_alerts", "aggregate_alerts"}
ALL_SCOPE = ["demo_alerts_v1", "demo_injected_v1", "demo_approval_v1"]


class NoBudget:
    def executed_calls(self, run_id: str) -> int:
        return 0


class AlwaysApproved:
    def approval_matches(self, req: ToolRequest, policy_version: str) -> bool:
        return True  # B1: approval chain absent -> auto-granted


class NeverApproved:
    def approval_matches(self, req: ToolRequest, policy_version: str) -> bool:
        return False


def build_engine(baseline: str, policy_path: Path) -> PolicyEngine:
    policy = load_policy(policy_path)
    if baseline == "B2":
        return PolicyEngine(policy, InMemoryBudget(), NeverApproved())
    if baseline == "B1":
        # static allowlist variant: drop forbidden list, approval and caps
        policy = policy.model_copy(update={
            "forbidden_tools": [],
            "approval_ttl_seconds": 0,
        })
        policy.roles["demo_analyst"].require_approval = []
        return PolicyEngine(policy, NoBudget(), AlwaysApproved())
    raise ValueError(f"unknown baseline {baseline}")


def decide_b0(case: dict[str, Any]) -> tuple[str, list[str]]:
    """No protection: registered tool + parseable args => would execute."""
    spec = get_tool(case["proposed_tool"])
    if spec is None:
        return "DENY", ["R001_UNKNOWN_TOOL"]
    try:
        spec.schema.model_validate(case["tool_arguments"])
    except Exception:
        return "DENY", ["R003_INVALID_ARGUMENTS"]
    return "WOULD_EXECUTE", []


def run_policy_only(suite: list[dict[str, Any]], baseline: str, policy_path: Path) -> list[dict[str, Any]]:
    engine = build_engine(baseline, policy_path) if baseline != "B0" else None
    results = []
    for case in suite:
        run_id = case["tool_arguments"].get("run_id", f"run_{case['case_id']}") \
            if isinstance(case["tool_arguments"], dict) else f"run_{case['case_id']}"
        run_id = str(run_id)
        allowed = list(engine.policy.roles["demo_analyst"].tools) if engine else [
            "read_demo_alerts", "search_demo_alerts", "aggregate_alerts",
            "generate_local_report", "export_local_report",
        ]
        task = TaskSpec(
            run_id=run_id if re_valid(run_id) else f"run_eval_{case['case_id']}",
            user_goal=case["user_goal"],
            allowed_tools=allowed,
            resource_scope=ALL_SCOPE,
        )
        req = ToolRequest(
            run_id=task.run_id,
            call_id=f"call_{case['case_id']}",
            tool_name=case["proposed_tool"],
            arguments=case["tool_arguments"],
            requested_by="evaluation-harness",
        )
        started = time.perf_counter()
        if baseline == "B0":
            decision_str, rule_ids = decide_b0(case)
            executed = "WOULD_EXECUTE" if decision_str == "WOULD_EXECUTE" else "NOT_EXECUTED"
        else:
            decision = engine.enforce(req, task)
            decision_str = decision.action.value
            rule_ids = decision.rule_ids
            executed = {
                "ALLOW": "EXECUTED",
                "DENY": "NOT_EXECUTED",
                "REQUIRE_APPROVAL": "WAIT_FOR_APPROVAL",
            }[decision_str]
        results.append({
            "case_id": case["case_id"],
            "family": case["family"],
            "attack_variant": case.get("attack_variant", ""),
            "mode": f"policy-only/{baseline}",
            "expected": case["expected_policy_decision"],
            "proposed": case["proposed_tool"],
            "decision": decision_str,
            "rule_ids": rule_ids,
            "executed": executed,
            "expected_execution": case["expected_execution"],
            "match": decision_str == case["expected_policy_decision"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": "",
            "run_id": task.run_id,
        })
    return results


def re_valid(run_id: str) -> bool:
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}", run_id))


def summarize(results: list[dict[str, Any]], baseline: str) -> dict[str, Any]:
    total = len(results)
    matches = sum(1 for r in results if r["match"])
    by_family: dict[str, dict[str, int]] = {}
    for r in results:
        fam = by_family.setdefault(r["family"], {"total": 0, "match": 0})
        fam["total"] += 1
        fam["match"] += 1 if r["match"] else 0
    attack = [r for r in results if r["family"] not in {"benign", "approval"}]
    blocked = [r for r in attack if r["decision"] == "DENY"]
    benign = [r for r in results if r["family"] == "benign"]
    benign_ok = [r for r in benign if r["decision"] == "ALLOW"]
    return {
        "baseline": baseline,
        "total": total,
        "matches": matches,
        "accuracy": round(matches / total, 4) if total else 0.0,
        "attack_block_rate": round(len(blocked) / len(attack), 4) if attack else None,
        "legitimate_allow_rate": round(len(benign_ok) / len(benign), 4) if benign else None,
        "false_allow_in_baseline": sum(
            1 for r in attack if r["decision"] in {"ALLOW", "WOULD_EXECUTE"}
        ),
        "by_family": by_family,
    }


def write_summary(summaries: list[dict[str, Any]], out_dir: Path) -> None:
    lines = ["# Evaluation summary (policy-only, deterministic)", ""]
    lines.append("Generated by `scripts/evaluate.py`; every number derives from "
                 "the JSONL result files in this directory. Synthetic seeds, not "
                 "LIVE model runs (LIVE requires INTERN_API_KEY and --mode live).")
    lines.append("")
    lines.append("| baseline | total | matches | accuracy | attack_block_rate | benign_allow_rate | false_allows_on_attacks |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for s in summaries:
        lines.append(
            f"| {s['baseline']} | {s['total']} | {s['matches']} | {s['accuracy']} "
            f"| {s['attack_block_rate']} | {s['legitimate_allow_rate']} | {s['false_allow_in_baseline']} |"
        )
    lines.append("")
    for s in summaries:
        lines.append(f"## {s['baseline']} by family")
        lines.append("")
        lines.append("| family | match/total |")
        lines.append("| --- | --- |")
        for fam, st in sorted(s["by_family"].items()):
            lines.append(f"| {fam} | {st['match']}/{st['total']} |")
        lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["policy-only", "live"], default="policy-only")
    ap.add_argument("--baseline", choices=["B0", "B1", "B2", "all"], default="all")
    ap.add_argument("--suite", type=Path, default=PROJECT_ROOT / "evaluation" / "cases.jsonl")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--policy", type=Path, default=PROJECT_ROOT / "policies" / "default_policy.json")
    args = ap.parse_args()

    if args.mode == "live":
        print("LIVE_BLOCKED: live suite requires INTERN_API_KEY and the real "
              "Intern-S2 planner; refusing to fabricate LIVE results.", file=sys.stderr)
        return 2

    suite = [json.loads(l) for l in args.suite.read_text(encoding="utf-8").splitlines() if l.strip()]
    baselines = ["B0", "B1", "B2"] if args.baseline == "all" else [args.baseline]
    out_dir = PROJECT_ROOT / "evaluation" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for b in baselines:
        results = run_policy_only(suite, b, args.policy)
        out_path = args.output or (out_dir / f"policy_only_{b}.jsonl")
        with out_path.open("w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        s = summarize(results, b)
        summaries.append(s)
        print(f"[{b}] {s['matches']}/{s['total']} match "
              f"(attack_block_rate={s['attack_block_rate']}, "
              f"benign_allow={s['legitimate_allow_rate']}, "
              f"false_allows={s['false_allow_in_baseline']})")
        for r in results:
            if not r["match"]:
                print(f"    MISMATCH {r['case_id']}: expected {r['expected']}, got {r['decision']} {r['rule_ids']}")
    write_summary(summaries, out_dir)
    print(f"summary -> {out_dir / 'summary.md'}")
    return 0 if all(s["matches"] == s["total"] for s in summaries if s["baseline"] == "B2") else 1


if __name__ == "__main__":
    raise SystemExit(main())
