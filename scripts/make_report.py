#!/usr/bin/env python3
"""Rebuild the HTML/JSON report for a completed run from its audit trail."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secverify.config import settings
from secverify.reports.build_report import build_report_for_run
from secverify.telemetry.audit import AuditStore


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--api-mode", default="DEMO_REPLAY")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    audit = AuditStore(settings.artifacts_dir / "runs")
    events = audit.events_for_run(args.run_id)
    if not events:
        print(f"no audit events found for run {args.run_id}")
        return 1
    html, jsn = build_report_for_run(audit, args.run_id, {"api_mode": args.api_mode})
    outdir = Path(args.outdir) if args.outdir else settings.artifacts_dir / args.run_id
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.html").write_text(html, encoding="utf-8")
    (outdir / "report.json").write_text(jsn, encoding="utf-8")
    print(f"rebuilt from {len(events)} events -> {outdir / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
