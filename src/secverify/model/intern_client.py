"""Intern-S2 client (spec §7).

- Official chat completions endpoint, non-stream, thinking_mode on.
- Records model_id / finish_reason / request_id / tool_calls into a redacted
  ModelTurnResult; the API key never appears in any log or artifact.
- Without INTERN_API_KEY every call raises LiveBlocked and callers must label
  their artifacts LIVE_BLOCKED - replay/scripted output is never LIVE evidence.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from secverify.config import settings
from secverify.schemas import ApiMode, ModelTurnResult, sha256_of


class LiveBlocked(Exception):
    """Raised when LIVE mode is requested but no API key is configured."""


class InternClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        self.api_key = (api_key if api_key is not None else settings.intern_api_key).strip()
        self.api_url = (api_url or settings.intern_api_url).strip()
        self.model = model or settings.intern_model
        self.timeout = timeout_seconds or settings.intern_timeout_seconds
        self.last_mode: ApiMode = ApiMode.LIVE_BLOCKED

    @property
    def live_ready(self) -> bool:
        return bool(self.api_key)

    async def request_chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
        thinking_mode: bool = True,
    ) -> ModelTurnResult:
        if not self.live_ready:
            self.last_mode = ApiMode.LIVE_BLOCKED
            raise LiveBlocked("INTERN_API_KEY missing -> LIVE_BLOCKED")
        if stream:
            raise ValueError("tool calling requires stream=false per official docs")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "thinking_mode": bool(thinking_mode),
        }
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as client:
                resp = await client.post(self.api_url, json=payload)
        except httpx.HTTPError as exc:
            self.last_mode = ApiMode.API_ERROR
            return ModelTurnResult(
                api_mode=ApiMode.API_ERROR, model_id=self.model,
                latency_ms=(time.perf_counter() - started) * 1000,
                error=f"{type(exc).__name__}: {exc}",
            )

        latency = (time.perf_counter() - started) * 1000
        if resp.status_code != 200:
            self.last_mode = ApiMode.API_ERROR
            return ModelTurnResult(
                api_mode=ApiMode.API_ERROR, model_id=self.model,
                latency_ms=latency,
                error=f"HTTP {resp.status_code}: {resp.text[:300]}",
            )

        try:
            data = resp.json()
            choice = data["choices"][0]
            message = choice.get("message", {})
            tool_calls = [
                {
                    "call_id": tc.get("id", ""),
                    "tool_name": (tc.get("function") or {}).get("name", ""),
                    "arguments": json.loads((tc.get("function") or {}).get("arguments") or "{}"),
                }
                for tc in message.get("tool_calls", []) or []
            ]
            self.last_mode = ApiMode.LIVE_OK
            return ModelTurnResult(
                api_mode=ApiMode.LIVE_OK,
                model_id=data.get("model", self.model),
                finish_reason=choice.get("finish_reason", ""),
                request_id=data.get("request_id", "") or data.get("id", ""),
                content=message.get("content", "") or "",
                tool_calls=tool_calls,
                usage=data.get("usage", {}) or {},
                latency_ms=latency,
            )
        except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            self.last_mode = ApiMode.API_ERROR
            return ModelTurnResult(
                api_mode=ApiMode.API_ERROR, model_id=self.model, latency_ms=latency,
                error=f"unparseable response: {type(exc).__name__}: {exc}",
            )

    # ---------------------------------------------------------------- sync UI
    def request_chat_sync(self, *args: Any, **kwargs: Any) -> ModelTurnResult:
        return asyncio.run(self.request_chat(*args, **kwargs))

    @staticmethod
    def write_evidence(result: ModelTurnResult, path: Path) -> None:
        """Redacted evidence file for LIVE tool-call gates (spec §7.2)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
