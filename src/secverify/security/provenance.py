"""Data provenance: every context segment carries a trust label and parent links.
Trust can never be upgraded: MODEL_DERIVED keeps all untrusted ancestors
(spec §3.3) - a summary of an injected log is still untrusted when it reaches
another tool's arguments."""
from __future__ import annotations

import hashlib
from typing import Iterable, Optional

from secverify.schemas import (
    ContentSegment,
    SourceType,
    TrustLabel,
    TRUST_BY_SOURCE,
)


class ProvenanceStore:
    def __init__(self) -> None:
        self._segments: dict[str, ContentSegment] = {}
        self._counter = 0

    def _next_id(self, run_id: str) -> str:
        self._counter += 1
        return f"seg_{run_id}_{self._counter:04d}"

    def add(
        self,
        run_id: str,
        source_type: SourceType,
        source_id: str,
        content: str,
        parent_ids: Optional[list[str]] = None,
        trust_label: Optional[TrustLabel] = None,
    ) -> ContentSegment:
        excerpt = content[:400]
        segment = ContentSegment(
            id=self._next_id(run_id),
            run_id=run_id,
            source_type=source_type,
            source_id=source_id,
            trust_label=trust_label or TRUST_BY_SOURCE[source_type],
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            content_excerpt=excerpt,
            parent_ids=list(parent_ids or []),
        )
        self._segments[segment.id] = segment
        return segment

    def derive(
        self,
        run_id: str,
        source_id: str,
        content: str,
        parent_ids: Iterable[str],
    ) -> ContentSegment:
        """Model-derived material: label is always MODEL_DERIVED and the FULL
        ancestor set is preserved (no laundering through summarisation)."""
        parents: set[str] = set()
        for pid in parent_ids:
            parents.add(pid)
            seg = self._segments.get(pid)
            if seg:
                parents.update(seg.parent_ids)
        return self.add(
            run_id,
            SourceType.MODEL_DERIVED_FROM_UNTRUSTED_LOG,
            source_id,
            content,
            parent_ids=sorted(parents),
            trust_label=TrustLabel.MODEL_DERIVED,
        )

    def get(self, segment_id: str) -> Optional[ContentSegment]:
        return self._segments.get(segment_id)

    def chain_of(self, segment_id: str) -> list[ContentSegment]:
        seg = self._segments.get(segment_id)
        if seg is None:
            return []
        out, stack = [], list(seg.parent_ids)
        seen: set[str] = set()
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            parent = self._segments.get(pid)
            if parent:
                out.append(parent)
                stack.extend(parent.parent_ids)
        return out

    def least_trusted_label(self, segment_ids: Iterable[str]) -> TrustLabel:
        """Effective trust of a set = the least trusted member (never upgraded)."""
        order = [
            TrustLabel.SYSTEM_POLICY,
            TrustLabel.USER_INSTRUCTION,
            TrustLabel.MODEL_DERIVED,
            TrustLabel.UNTRUSTED_TOOL_OUTPUT,
            TrustLabel.UNTRUSTED_LOG,
        ]
        labels = set()
        for sid in segment_ids:
            seg = self._segments.get(sid)
            if seg:
                labels.add(seg.trust_label)
                labels.update(s.trust_label for s in self.chain_of(sid))
        for label in order[::-1]:
            if label in labels:
                return label
        return TrustLabel.MODEL_DERIVED

    def segments_for_run(self, run_id: str) -> list[ContentSegment]:
        return [s for s in self._segments.values() if s.run_id == run_id]

    def reset(self) -> None:
        self._segments.clear()
        self._counter = 0
