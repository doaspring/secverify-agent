#!/usr/bin/env python3
"""M0 gate 2: real tool-call round trip with Intern-S2 (spec §7.2).

Sends tools=[{type:function,...}] with a side-effect-free test function,
verifies the response contains an actual tool_calls list (not text claiming a
call), executes the local harmless function, and sends the tool message back
for a second real round. Evidence (redacted) goes to evidence/live_tool_call.json.

LIVE_BLOCKED (exit 3) without a key is an honest passing state for offline dev.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from secverify.model.intern_client import InternClient, LiveBlocked
from secverify.security.tool_registry import tool_schemas_for_api

TEST_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Return the sum of two integers. Pure computation, no side effects.",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
        },
    }
]


def add_numbers(a: int, b: int) -> int:
    return a + b


async def main_async() -> int:
    client = InternClient()
    print(f"model={client.model} key={'set' if client.live_ready else 'MISSING'}")
    if not client.live_ready:
        print("LIVE_BLOCKED: no INTERN_API_KEY; cannot produce LIVE tool-call evidence.")
        return 3

    messages = [
        {"role": "system", "content": "Use the provided function to answer."},
        {"role": "user", "content": "请计算 137 + 291，必须调用函数。"},
    ]
    turn1 = await client.request_chat(messages=messages, tools=TEST_TOOLS)
    print(f"round1: {turn1.api_mode.value} finish={turn1.finish_reason} "
          f"tool_calls={len(turn1.tool_calls)}")
    if turn1.api_mode.value != "LIVE_OK" or not turn1.tool_calls:
        print(f"error: {turn1.error or 'no tool_calls returned'}")
        return 1

    call = turn1.tool_calls[0]
    result_value = add_numbers(**call["arguments"])
    print(f"round1 call: {call['tool_name']}({call['arguments']}) -> {result_value}")

    messages.append({
        "role": "assistant", "content": turn1.content,
        "tool_calls": [{
            "id": call["call_id"], "type": "function",
            "function": {"name": call["tool_name"],
                         "arguments": json.dumps(call["arguments"])},
        }],
    })
    messages.append({
        "role": "tool", "tool_call_id": call["call_id"],
        "content": json.dumps({"result": result_value}),
    })
    turn2 = await client.request_chat(messages=messages, tools=TEST_TOOLS)
    print(f"round2: {turn2.api_mode.value} finish={turn2.finish_reason} "
          f"content={turn2.content[:120]}")

    evidence = {
        "gate": "live_tool_call_round_trip",
        "round1": turn1.model_dump(),
        "round2": turn2.model_dump(),
        "local_execution": {"tool": "add_numbers", "result": result_value},
        "registry_digest_preview": len(tool_schemas_for_api()),
    }
    out = Path("evidence/live_tool_call.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evidence -> {out}")
    return 0 if turn2.api_mode.value == "LIVE_OK" else 1


def main() -> int:
    try:
        return asyncio.run(main_async())
    except LiveBlocked:
        print("LIVE_BLOCKED")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
