"""HTML/JSON run report built ONLY from audit events (spec §12, §17).

Every number in the report is derived from the append-only audit trail, so the
report can be re-derived and diffed at any time.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from secverify.schemas import AuditEvent
from secverify.telemetry.audit import AuditStore


def summarize_events(events: list[AuditEvent]) -> dict[str, Any]:
    decisions = [e for e in events if e.event_type == "policy.decision" or e.policy_action]
    executed = [e for e in events if e.execution_status == "EXECUTED"]
    denied = [e for e in events if e.event_type == "tool.denied"]
    proposed = [e for e in events if e.event_type == "model.tool_proposed"]
    return {
        "total_events": len(events),
        "tool_proposals": len(proposed),
        "policy_decisions": len(decisions),
        "executed": len(executed),
        "denied": len(denied),
        "waited_approval": len([e for e in events if e.execution_status == "WAIT_FOR_APPROVAL"]),
        "executed_tools": sorted({e.proposed_tool for e in executed}),
        "denied_tools": sorted({e.proposed_tool for e in denied}),
        "denied_rules": sorted({r for e in denied for r in e.rule_ids}),
        "latency_ms_by_tool": {
            t: round(max((e.latency_ms for e in executed if e.proposed_tool == t), default=0.0), 2)
            for t in sorted({e.proposed_tool for e in executed})
        },
        "task_continued_after_block": len(denied) > 0 and len(executed) > 0,
    }


def build_html(run_id: str, events: list[AuditEvent], header: dict[str, Any]) -> str:
    s = summarize_events(events)
    rows = "\n".join(
        f"<tr><td>{html.escape(e.utc_timestamp)}</td>"
        f"<td>{html.escape(e.event_type)}</td>"
        f"<td>{html.escape(e.proposed_tool or e.node)}</td>"
        f"<td>{html.escape(e.policy_action)}</td>"
        f"<td>{html.escape(','.join(e.rule_ids))}</td>"
        f"<td>{html.escape(e.execution_status)}</td>"
        f"<td>{html.escape(e.sanitized_args[:80])}</td></tr>"
        for e in events
    )
    meta = html.escape(json.dumps(header, ensure_ascii=False))
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>SecVerify run {html.escape(run_id)}</title>
<style>
body{{font-family:system-ui,'Segoe UI',sans-serif;margin:24px;color:#1a1a2e;background:#fafbfd}}
h1{{font-size:20px}} h2{{font-size:15px;margin-top:24px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
td,th{{border:1px solid #d7dce3;padding:4px 8px;text-align:left}}
th{{background:#eef2f7}}
.k{{display:inline-block;padding:2px 8px;border-radius:10px;background:#e8eef7;margin-right:6px}}
.badge-DENY{{background:#fdecea;color:#b02a37;font-weight:600}}
.badge-ALLOW{{background:#e7f5ec;color:#1c6e3c}}
.badge-REQUIRE_APPROVAL{{background:#fff4e0;color:#9a6200}}
.badge-EXECUTED{{background:#e7f5ec;color:#1c6e3c}}
.badge-NOT_EXECUTED{{background:#fdecea;color:#b02a37}}
.badge-WAIT_FOR_APPROVAL{{background:#fff4e0;color:#9a6200}}
.badge-SIMULATED_ONLY{{background:#eeeeee;color:#555}}
</style></head><body>
<h1>SecVerify Agent · 可信执行报告 · run <code>{html.escape(run_id)}</code></h1>
<p><span class="k">模式: {html.escape(str(header.get('api_mode','')))}</span>
<span class="k">模型: {html.escape(str(header.get('model_id','')))}</span>
<span class="k">策略版本: {html.escape(str(header.get('policy_version','')))}</span></p>
<h2>汇总</h2>
<table><tr><th>提议</th><th>决策</th><th>已执行</th><th>已阻断</th><th>等待审批</th><th>阻断后任务延续</th></tr>
<tr><td>{s['tool_proposals']}</td><td>{s['policy_decisions']}</td><td>{s['executed']}</td>
<td>{s['denied']}</td><td>{s['waited_approval']}</td><td>{'是' if s['task_continued_after_block'] else '—'}</td></tr></table>
<h2>事件时间线（append-only审计）</h2>
<table><tr><th>时间(UTC)</th><th>事件</th><th>工具/节点</th><th>裁决</th><th>规则</th><th>执行状态</th><th>参数(脱敏)</th></tr>
{rows}</table>
<h2>机器可读元数据</h2>
<pre>{meta}</pre>
</body></html>"""


def build_report_for_run(
    audit: AuditStore, run_id: str, header: dict[str, Any] | None = None
) -> tuple[str, str]:
    events = audit.events_for_run(run_id)
    header = header or {}
    payload = {
        "run_id": run_id,
        "header": header,
        "summary": summarize_events(events),
        "events": [e.model_dump() for e in events],
    }
    return (
        build_html(run_id, events, header),
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
