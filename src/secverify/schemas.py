"""Pydantic schemas and the canonical enum set from SECVERIFY_EXECUTION_SPEC.md §5.

All enums live here and nowhere else (spec §5.6): policy_action, execution_status,
api_mode, trust_label, source_type, plus run status from §8.3.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------- enums (§5.6)

class PolicyAction(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class ExecutionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    NOT_EXECUTED = "NOT_EXECUTED"
    WOULD_EXECUTE = "WOULD_EXECUTE"          # B0 unprotected baseline marker only
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    SIMULATED_ONLY = "SIMULATED_ONLY"        # decoy tools: never any real effect


class ApiMode(str, Enum):
    LIVE_OK = "LIVE_OK"
    LIVE_BLOCKED = "LIVE_BLOCKED"
    API_ERROR = "API_ERROR"
    DEMO_REPLAY = "DEMO_REPLAY"


class TrustLabel(str, Enum):
    SYSTEM_POLICY = "SYSTEM_POLICY"
    USER_INSTRUCTION = "USER_INSTRUCTION"
    UNTRUSTED_LOG = "UNTRUSTED_LOG"
    UNTRUSTED_TOOL_OUTPUT = "UNTRUSTED_TOOL_OUTPUT"
    MODEL_DERIVED = "MODEL_DERIVED"


class SourceType(str, Enum):
    DEMO_LOG = "demo_log"
    UNTRUSTED_TOOL_OUTPUT = "untrusted_tool_output"
    MODEL_DERIVED_FROM_UNTRUSTED_LOG = "model_derived_from_untrusted_log"
    USER_INSTRUCTION = "user_instruction"


TRUST_BY_SOURCE: dict[SourceType, TrustLabel] = {
    SourceType.DEMO_LOG: TrustLabel.UNTRUSTED_LOG,
    SourceType.UNTRUSTED_TOOL_OUTPUT: TrustLabel.UNTRUSTED_TOOL_OUTPUT,
    SourceType.MODEL_DERIVED_FROM_UNTRUSTED_LOG: TrustLabel.MODEL_DERIVED,
    SourceType.USER_INSTRUCTION: TrustLabel.USER_INSTRUCTION,
}


class RunStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    TOOL_PROPOSED = "TOOL_PROPOSED"
    POLICY_DENIED = "POLICY_DENIED"
    WAIT_APPROVAL = "WAIT_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    API_UNAVAILABLE = "API_UNAVAILABLE"


# ------------------------------------------------------------- tool arguments
# dataset_id is a server-assigned enum; run_id must be a flat token so it can
# never traverse paths. Numeric caps (limit<=max_rows_per_read) are enforced by
# the policy engine (R006), not by the schema: schema checks shape, policy
# checks budget (DECISIONS.md D002).

DatasetId = Literal["demo_alerts_v1", "demo_injected_v1", "demo_approval_v1"]
RunId = str  # validated via RUN_ID_PATTERN
RUN_ID_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$"


class ReadDemoAlertsArgs(BaseModel):
    dataset_id: DatasetId
    limit: int = Field(ge=1)


class SearchDemoAlertsArgs(BaseModel):
    dataset_id: DatasetId
    keyword: str = Field(min_length=1, max_length=200)
    limit: int = Field(ge=1)


class AggregateAlertsArgs(BaseModel):
    dataset_id: DatasetId
    group_by: Literal["severity", "category", "source_type"]


class GenerateLocalReportArgs(BaseModel):
    # run_id optional: the model cannot know the server-side run id; when
    # omitted, the gateway binds the report to the CURRENT run
    run_id: Optional[str] = Field(default=None, pattern=RUN_ID_PATTERN)


class ExportLocalReportArgs(BaseModel):
    run_id: Optional[str] = Field(default=None, pattern=RUN_ID_PATTERN)
    export_format: Literal["html", "json"]


class MockSendExternalArgs(BaseModel):
    destination_id: str = Field(min_length=1, max_length=64)
    payload_ref: str = Field(min_length=1, max_length=128)


class MockDeleteAllArgs(BaseModel):
    dataset_id: DatasetId


# ------------------------------------------------------------- core contracts

class ContentSegment(BaseModel):
    """One piece of context with its trust label and provenance (spec §3.3)."""
    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    source_type: SourceType
    source_id: str
    trust_label: TrustLabel
    sha256: str
    content_excerpt: str = Field(max_length=400)
    parent_ids: list[str] = Field(default_factory=list)
    captured_at: str = Field(default_factory=utc_now_iso)


class TaskSpec(BaseModel):
    """User-authorized task. allowed_tools is the intersection of server policy
    and user authorization - never authored by the LLM."""
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    user_goal: str = Field(min_length=1)
    actor_role: str = "demo_analyst"
    dataset_id: DatasetId = "demo_alerts_v1"
    allowed_tools: list[str]
    resource_scope: list[DatasetId]
    require_approval: list[str] = Field(default_factory=list)
    external_egress_allowed: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)


class ToolRequest(BaseModel):
    """The model may only PROPOSE calls; execution is decided by the policy engine."""
    run_id: str
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    source_segment_ids: list[str] = Field(default_factory=list)
    requested_by: str = "intern-s2"
    tool_schema_version: str = "1.0"


class PolicyDecision(BaseModel):
    decision_id: str
    run_id: str
    call_id: str
    action: PolicyAction
    rule_ids: list[str]
    reason: str
    approval_required: bool = False
    policy_version: str
    source_segment_ids: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Fact source for reports and evaluation (spec §5.4)."""
    event_id: str
    run_id: str
    utc_timestamp: str = Field(default_factory=utc_now_iso)
    event_type: str                      # model.request / model.tool_proposed / ...
    node: str = ""
    model_id: str = ""
    tool_call_id: str = ""
    proposed_tool: str = ""
    policy_action: str = ""
    rule_ids: list[str] = Field(default_factory=list)
    sanitized_args: str = ""
    source_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    execution_status: str = ""
    output_hash: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class ApprovalRecord(BaseModel):
    token: str
    run_id: str
    tool_name: str
    canonical_args_sha256: str
    policy_version: str
    created_at: float
    expires_at: float
    consumed: bool = False


class ModelTurnResult(BaseModel):
    """Redacted record of one Intern-S2 API round (spec §5.5)."""
    api_mode: ApiMode
    model_id: str = ""
    finish_reason: str = ""
    request_id: str = ""
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    error: str = ""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_of(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
