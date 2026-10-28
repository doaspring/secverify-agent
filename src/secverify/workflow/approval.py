"""Human approval tokens (spec §6.3 / §8.2).

A token is created ONLY from a trusted UI action (Streamlit button -> graph
resume), binds run_id + sha256(canonical(tool_name, args)) + policy_version,
expires after approval_ttl_seconds and is single-use. A model claiming "the
user already approved" creates nothing - tokens can only be minted through
ApprovalStore.create(), which only the approval resume node calls after the
user pressed the button.
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from secverify.schemas import ApprovalRecord, ToolRequest, canonical_json, sha256_of


def canonical_call_sha256(tool_name: str, arguments: dict) -> str:
    return sha256_of({"tool_name": tool_name, "arguments": canonical_json(arguments)})


class ApprovalStore:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, ApprovalRecord] = {}

    def create(
        self, run_id: str, tool_name: str, arguments: dict, policy_version: str
    ) -> ApprovalRecord:
        now = time.time()
        record = ApprovalRecord(
            token=f"apr_{uuid.uuid4().hex[:12]}",
            run_id=run_id,
            tool_name=tool_name,
            canonical_args_sha256=canonical_call_sha256(tool_name, arguments),
            policy_version=policy_version,
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        self._records[record.token] = record
        return record

    def approval_matches(self, req: ToolRequest, policy_version: str) -> bool:
        """True only for an unconsumed, unexpired token bound to THIS exact call."""
        wanted = canonical_call_sha256(req.tool_name, req.arguments)
        now = time.time()
        for record in self._records.values():
            if (
                not record.consumed
                and record.run_id == req.run_id
                and record.tool_name == req.tool_name
                and record.canonical_args_sha256 == wanted
                and record.policy_version == policy_version
                and record.expires_at >= now
            ):
                return True
        return False

    def consume(self, req: ToolRequest, policy_version: str) -> Optional[ApprovalRecord]:
        """Consume the matching token (single use) - called by ToolGateway right
        before executing an approved call."""
        wanted = canonical_call_sha256(req.tool_name, req.arguments)
        now = time.time()
        for record in self._records.values():
            if (
                not record.consumed
                and record.run_id == req.run_id
                and record.tool_name == req.tool_name
                and record.canonical_args_sha256 == wanted
                and record.policy_version == policy_version
                and record.expires_at >= now
            ):
                self._records[record.token] = record.model_copy(update={"consumed": True})
                return self._records[record.token]
        return None

    def get(self, token: str) -> Optional[ApprovalRecord]:
        return self._records.get(token)

    def all_records(self) -> list[ApprovalRecord]:
        return list(self._records.values())
