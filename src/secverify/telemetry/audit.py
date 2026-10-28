"""Append-only audit trail: JSONL per run + SQLite index (spec §5.4, §10).

Never stores raw API keys or oversized raw payloads; args are sanitised and
every executed result is reduced to a sha256.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator, Optional

from secverify.schemas import AuditEvent, utc_now_iso

_SENSITIVE_KEY = re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)")


def sanitize_args(args: Any, limit: int = 200) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(args)
    def _redact(match: re.Match[str]) -> str:
        return match.group(1) + '"***REDACTED***"'
    text = re.sub(r'("(?:[^"]*(?:key|token|secret|password)[^"]*)"\s*:\s*)"[^"]*"', _redact, text, flags=re.IGNORECASE)
    return text[:limit]


class AuditStore:
    def __init__(self, runs_dir: Path, sqlite_path: Optional[Path] = None):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._sqlite_path = sqlite_path
        self._counter = 0

    # ---------------------------------------------------------------- writing
    def emit(
        self,
        run_id: str,
        event_type: str,
        *,
        node: str = "",
        model_id: str = "",
        tool_call_id: str = "",
        proposed_tool: str = "",
        policy_action: str = "",
        rule_ids: Optional[list[str]] = None,
        sanitized_args: str = "",
        source_ids: Optional[list[str]] = None,
        latency_ms: float = 0.0,
        execution_status: str = "",
        output_hash: str = "",
        detail: Optional[dict[str, Any]] = None,
    ) -> AuditEvent:
        self._counter += 1
        event = AuditEvent(
            event_id=f"evt_{self._counter:06d}",
            run_id=run_id,
            utc_timestamp=utc_now_iso(),
            event_type=event_type,
            node=node,
            model_id=model_id,
            tool_call_id=tool_call_id,
            proposed_tool=proposed_tool,
            policy_action=policy_action,
            rule_ids=rule_ids or [],
            sanitized_args=sanitized_args,
            source_ids=source_ids or [],
            latency_ms=latency_ms,
            execution_status=execution_status,
            output_hash=output_hash,
            detail=detail or {},
        )
        path = self.runs_dir / run_id / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")
        self._sqlite_append(event)
        return event

    def _sqlite_append(self, event: AuditEvent) -> None:
        if self._sqlite_path is None:
            return
        import sqlite3

        with sqlite3.connect(self._sqlite_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS audit_events (
                       event_id TEXT PRIMARY KEY, run_id TEXT, utc_timestamp TEXT,
                       event_type TEXT, node TEXT, proposed_tool TEXT,
                       policy_action TEXT, rule_ids TEXT, execution_status TEXT,
                       payload TEXT)""",
            )
            conn.execute(
                "INSERT OR REPLACE INTO audit_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    event.event_id, event.run_id, event.utc_timestamp, event.event_type,
                    event.node, event.proposed_tool, event.policy_action,
                    json.dumps(event.rule_ids), event.execution_status,
                    event.model_dump_json(),
                ),
            )

    # ---------------------------------------------------------------- reading
    def events_for_run(self, run_id: str) -> list[AuditEvent]:
        path = self.runs_dir / run_id / "audit.jsonl"
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(AuditEvent.model_validate_json(line))
        return out

    def runs(self) -> list[str]:
        return sorted(p.name for p in self.runs_dir.iterdir() if p.is_dir())
