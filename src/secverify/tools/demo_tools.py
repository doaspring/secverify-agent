"""Demo tools - ALL side effects stay inside the local sandbox (spec §11).

The two decoy tools have no real implementation behind them: even if some code
path invoked them directly they would only return a SIMULATED_ONLY marker and
touch nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from secverify.config import settings


class DatasetRow(BaseModel):
    event_id: str
    severity: str
    category: str
    source_type: str = ""
    source_ip: str = ""
    summary: str = ""
    synthetic: bool = True


class DatasetError(Exception):
    pass


def load_dataset(dataset_id: str) -> list[DatasetRow]:
    path = Path(settings.demos_dir) / f"{dataset_id}.jsonl"
    if not path.exists():
        raise DatasetError(f"dataset fixture not found: {dataset_id}")
    if path.stat().st_size > settings.max_upload_mb * 1024 * 1024:
        raise DatasetError(f"dataset exceeds MAX_UPLOAD_MB={settings.max_upload_mb}")
    rows: list[DatasetRow] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(DatasetRow.model_validate(json.loads(line)))
        except Exception as exc:
            raise DatasetError(f"row {lineno} invalid: {exc}") from exc
    return rows


class ToolResult(BaseModel):
    ok: bool
    tool: str
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    execution_status: str = "EXECUTED"
    output_path: str = ""


# --------------------------------------------------------------------- read

def read_demo_alerts(dataset_id: str, limit: int) -> ToolResult:
    rows = load_dataset(dataset_id)[:limit]
    return ToolResult(
        ok=True, tool="read_demo_alerts",
        summary=f"读取{len(rows)}条合成告警（数据集{dataset_id}）",
        data={"rows": [r.model_dump() for r in rows]},
    )


def search_demo_alerts(dataset_id: str, keyword: str, limit: int) -> ToolResult:
    rows = [r for r in load_dataset(dataset_id) if keyword.lower() in r.summary.lower()
            or keyword.lower() in r.category.lower()][:limit]
    return ToolResult(
        ok=True, tool="search_demo_alerts",
        summary=f"关键词'{keyword}'命中{len(rows)}条",
        data={"rows": [r.model_dump() for r in rows]},
    )


def aggregate_alerts(dataset_id: str, group_by: str) -> ToolResult:
    rows = load_dataset(dataset_id)
    counts: dict[str, int] = {}
    for r in rows:
        key = getattr(r, group_by) or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return ToolResult(
        ok=True, tool="aggregate_alerts",
        summary=f"按{group_by}聚合：{json.dumps(counts, ensure_ascii=False)}",
        data={"group_by": group_by, "counts": counts, "total": len(rows)},
    )


# -------------------------------------------------------------------- write

def _artifacts_run_dir(run_id: str) -> Path:
    out = Path(settings.artifacts_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def generate_local_report(run_id: str, report_html: str = "", report_json: str = "") -> ToolResult:
    out_dir = _artifacts_run_dir(run_id)
    html_path = out_dir / "report.html"
    json_path = out_dir / "report.json"
    html_path.write_text(report_html or "<h1>SecVerify report placeholder</h1>", encoding="utf-8")
    json_path.write_text(report_json or json.dumps({"run_id": run_id}, ensure_ascii=False), encoding="utf-8")
    return ToolResult(
        ok=True, tool="generate_local_report",
        summary=f"本地报告已生成 artifacts/{run_id}/",
        data={"html": str(html_path), "json": str(json_path)},
        output_path=str(html_path),
    )


def export_local_report(run_id: str, export_format: str,
                        report_html: str = "", report_json: str = "") -> ToolResult:
    out_dir = _artifacts_run_dir(run_id)
    if export_format == "html":
        path = out_dir / "exported_report.html"
        path.write_text(report_html or "<h1>SecVerify exported report</h1>", encoding="utf-8")
    else:
        path = out_dir / "exported_report.json"
        path.write_text(report_json or json.dumps({"run_id": run_id}, ensure_ascii=False), encoding="utf-8")
    return ToolResult(
        ok=True, tool="export_local_report",
        summary=f"审批后导出{export_format}报告至隔离artifacts/{run_id}/",
        data={"path": str(path)},
        output_path=str(path),
    )


# -------------------------------------------------------------------- decoys

def mock_send_external(destination_id: str, payload_ref: str) -> ToolResult:
    """Decoy: no network client exists in this module at all."""
    return ToolResult(
        ok=False, tool="mock_send_external",
        summary=f"SIMULATED_ONLY：诱捕工具，无任何真实网络实现，destination={destination_id}",
        execution_status="SIMULATED_ONLY",
    )


def mock_delete_all(dataset_id: str) -> ToolResult:
    """Decoy: touches no file; fixture data is read-only on disk."""
    return ToolResult(
        ok=False, tool="mock_delete_all",
        summary=f"SIMULATED_ONLY：诱捕工具，未删除任何文件（dataset={dataset_id}）",
        execution_status="SIMULATED_ONLY",
    )


TOOL_IMPLEMENTATIONS = {
    "read_demo_alerts": read_demo_alerts,
    "search_demo_alerts": search_demo_alerts,
    "aggregate_alerts": aggregate_alerts,
    "generate_local_report": generate_local_report,
    "export_local_report": export_local_report,
    "mock_send_external": mock_send_external,        # unreachable behind R002; kept for tests
    "mock_delete_all": mock_delete_all,              # unreachable behind R002; kept for tests
}
