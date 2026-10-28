#!/usr/bin/env python3
"""M0 gate 1: plain chat smoke against Intern-S2 (spec §7.2).

Without INTERN_API_KEY prints LIVE_BLOCKED and exits 3 - that is a valid,
honest result; mock output is never produced here.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secverify.config import settings
from secverify.model.intern_client import InternClient, LiveBlocked


def main() -> int:
    client = InternClient()
    print(f"model={client.model} url={client.api_url} key={'set' if client.live_ready else 'MISSING'}")
    if not client.live_ready:
        print("LIVE_BLOCKED: no INTERN_API_KEY configured; user must apply for a key")
        print(f"(replay reason: {settings.replay_mode_reason})")
        return 3
    turn = client.request_chat_sync(messages=[{"role": "user", "content": "回复两个字：在线"}])
    print(f"api_mode={turn.api_mode.value} model={turn.model_id} finish={turn.finish_reason} "
          f"latency_ms={turn.latency_ms:.0f}")
    if turn.api_mode.value != "LIVE_OK":
        print(f"error: {turn.error}")
        return 1
    print(f"content: {turn.content[:200]}")
    client.write_evidence(turn, Path("evidence/live_chat_smoke.json"))
    print("evidence -> evidence/live_chat_smoke.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
