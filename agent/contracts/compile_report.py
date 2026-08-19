"""§14.1 — Compile report for the compile_contracts node.

When the candidate set comes back small, the report must explain why: the
requirement was not expressed (rule coverage), the LLM pass was off or
unavailable (degrade_reasons), or candidates were rejected by the schema
check (rejected + schema_errors). The report is a plain-data projection of
one compilation run: it serializes losslessly (to_dict/from_dict), rides the
LangGraph state channel as a dict, and merges across the per-pass reports of
one run (merge_reports).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CompileReport",
    "RejectedCandidate",
    "merge_reports",
    "requirement_digest",
]


def requirement_digest(text: str) -> str:
    """Stable SHA-256 digest of the requirement text (full hexdigest).

    Identifies the spec the report was compiled from without carrying the
    spec itself into logs or lineage — the same convention as
    ContractRecord.content_key. Deterministic across runs and hosts.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RejectedCandidate:
    """One candidate the compiler considered but did not accept."""

    reason: str
    candidate_summary: str

    def to_dict(self) -> dict[str, str]:
        return {"reason": self.reason, "candidate_summary": self.candidate_summary}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RejectedCandidate:
        return cls(
            reason=str(data.get("reason") or ""),
            candidate_summary=str(data.get("candidate_summary") or ""),
        )


@dataclass(frozen=True)
class CompileReport:
    """Full audit of one compile_contracts run (§14.1).

    candidate_count counts every candidate CONSIDERED (rule-based and
    LLM); accepted_count counts the candidates that end up in the final
    contract list; rejected lists the considered-but-dropped candidates
    with the reason; schema_errors and degrade_reasons explain failures
    that would otherwise silently swallow themselves.
    """

    parser_rule_version: str
    llm_used: bool
    candidate_count: int
    accepted_count: int
    rejected: list[RejectedCandidate] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    degrade_reasons: list[str] = field(default_factory=list)
    requirement_digest: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready projection (the shape stored in state/checkpoints)."""
        return {
            "parser_rule_version": self.parser_rule_version,
            "llm_used": self.llm_used,
            "candidate_count": self.candidate_count,
            "accepted_count": self.accepted_count,
            "rejected": [r.to_dict() for r in self.rejected],
            "schema_errors": list(self.schema_errors),
            "degrade_reasons": list(self.degrade_reasons),
            "requirement_digest": self.requirement_digest,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CompileReport:
        """Rebuild a report from a stored projection; missing keys degrade
        to defaults so older checkpoints stay loadable."""
        rejected: list[RejectedCandidate] = []
        for item in data.get("rejected") or []:
            if isinstance(item, Mapping):
                rejected.append(RejectedCandidate.from_dict(item))
            else:
                rejected.append(
                    RejectedCandidate(
                        reason="malformed_rejected_entry",
                        candidate_summary=str(item)[:200],
                    )
                )
        return cls(
            parser_rule_version=str(data.get("parser_rule_version") or ""),
            llm_used=bool(data.get("llm_used") or False),
            candidate_count=int(data.get("candidate_count") or 0),
            accepted_count=int(data.get("accepted_count") or 0),
            rejected=rejected,
            schema_errors=[str(e) for e in (data.get("schema_errors") or [])],
            degrade_reasons=[str(d) for d in (data.get("degrade_reasons") or [])],
            requirement_digest=str(data.get("requirement_digest") or ""),
            duration_ms=int(data.get("duration_ms") or 0),
        )


def merge_reports(reports: Iterable[CompileReport]) -> CompileReport:
    """Merge per-pass reports into one run-level report.

    Counts and durations add; rejected candidates, schema errors and
    degrade reasons concatenate in order; llm_used is OR-ed (any pass
    that used the LLM marks the run); parser_rule_version and
    requirement_digest come from the first report that declares them
    (every pass of one run shares the same values).
    """
    items = list(reports)
    if not items:
        raise ValueError("merge_reports requires at least one report")
    return CompileReport(
        parser_rule_version=next(
            (r.parser_rule_version for r in items if r.parser_rule_version), ""
        ),
        llm_used=any(r.llm_used for r in items),
        candidate_count=sum(r.candidate_count for r in items),
        accepted_count=sum(r.accepted_count for r in items),
        rejected=[rc for r in items for rc in r.rejected],
        schema_errors=[e for r in items for e in r.schema_errors],
        degrade_reasons=[d for r in items for d in r.degrade_reasons],
        requirement_digest=next(
            (r.requirement_digest for r in items if r.requirement_digest), ""
        ),
        duration_ms=sum(r.duration_ms for r in items),
    )
