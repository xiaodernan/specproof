"""Learning from Rejections — first slice (计划书 §19.6).

Reviewer-rejected patches, SpecProof-blocked tasks and human manual fixes
are converted into sanitized rules and evaluation cases — never into
training data. Each record stores the rejection reason, the wrong
assumption behind the attempt and the path that actually fixed it.

Sanitization pipeline (pure, deterministic):

1. Secrets go through providers.redaction.redact_text — the repo's
   canonical redactor — so every secret pattern the host already knows
   is scrubbed the same way prompts are scrubbed.
2. Identifier-shaped tokens (PascalCase / camelCase / snake_case) are
   replaced with [IDENT]. Redaction placeholders are never touched.
   Over-stripping is intentional and fail-safe: it can only hide data.

Rule extraction aggregates records by (sanitized assumption, sanitized
fix path) and orders rules by hit count — first-slice clustering without
an LLM. Evaluation-case generation is a pure hook: it emits dict-shaped
cases a later pipeline can persist, so nothing here writes to disk.

Honest scope: identifier stripping is conservative regex, not scope
analysis; it over-strips code-shaped prose. That is documented behavior,
not a bug.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from providers.redaction import redact_text

_IDENT_PLACEHOLDER = "[IDENT]"

# Redaction and identifier placeholders are protected: stripping never
# rewrites the inside of a [REDACTED:...] or [IDENT] placeholder.
_PROTECTED_SPAN_RE: re.Pattern[str] = re.compile(
    r"\[(?:REDACTED:[^\]]*|IDENT)\]"
)

# Conservative identifier shapes combined in one alternation: snake_case,
# PascalCase, camelCase. A single re.sub pass is deliberate — replacements
# are never rescanned, so a fresh [IDENT] placeholder cannot be re-matched.
_IDENT_TOKEN_RE: re.Pattern[str] = re.compile(
    r"\b(?:[a-z][a-z0-9]*_[a-z0-9_]+|[A-Z][A-Za-z0-9]*|[a-z]+[A-Z][A-Za-z0-9]*)\b"
)


@dataclass(frozen=True)
class RejectionRecord:
    """One rejected attempt: why it failed, the wrong assumption, the fix.

    sanitized marks records produced by sanitize_record; raw records from
    review pipelines carry it as False.
    """

    reason: str
    wrong_assumption: str
    valid_fix_path: str
    sanitized: bool = False


@dataclass(frozen=True)
class RejectionRule:
    """An extracted pattern -> guidance rule over sanitized records."""

    pattern: str
    guidance: str
    hits: int


def _strip_tokens(text: str) -> str:
    return _IDENT_TOKEN_RE.sub(_IDENT_PLACEHOLDER, text)


def _strip_identifiers(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _PROTECTED_SPAN_RE.finditer(text):
        parts.append(_strip_tokens(text[cursor : match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(_strip_tokens(text[cursor:]))
    return "".join(parts)


def _normalize(text: str) -> str:
    return " ".join(text.split()).lower()


def sanitize_record(record: RejectionRecord) -> RejectionRecord:
    """Return the record with secrets and identifiers stripped.

    Idempotent: already-sanitized records pass through unchanged, so
    round-tripping a record through sanitization is always safe.
    """
    if record.sanitized:
        return record
    return RejectionRecord(
        reason=_strip_identifiers(redact_text(record.reason)[0]),
        wrong_assumption=_strip_identifiers(redact_text(record.wrong_assumption)[0]),
        valid_fix_path=_strip_identifiers(redact_text(record.valid_fix_path)[0]),
        sanitized=True,
    )


def extract_rules(records: Iterable[RejectionRecord]) -> list[RejectionRule]:
    """Extract pattern -> guidance rules, ordered by hit count desc.

    The pattern is the sanitized, normalized wrong assumption and the
    guidance the sanitized, normalized fix path; identical pairs
    aggregate their hit counts. Records with an empty assumption carry
    no reusable pattern and are skipped.
    """
    grouped: dict[tuple[str, str], int] = {}
    for record in records:
        sane = sanitize_record(record)
        pattern = _normalize(sane.wrong_assumption)
        if not pattern:
            continue
        guidance = _normalize(sane.valid_fix_path)
        key = (pattern, guidance)
        grouped[key] = grouped.get(key, 0) + 1
    rules = [
        RejectionRule(pattern=pattern, guidance=guidance, hits=hits)
        for (pattern, guidance), hits in grouped.items()
    ]
    return sorted(rules, key=lambda rule: (-rule.hits, rule.pattern, rule.guidance))


def _case_id(record: RejectionRecord) -> str:
    digest = hashlib.sha256(
        "|".join(
            (record.reason, record.wrong_assumption, record.valid_fix_path)
        ).encode("utf-8")
    ).hexdigest()
    return digest[:12]


def build_eval_case(record: RejectionRecord) -> dict[str, str]:
    """Evaluation-case hook: turn a sanitized rejection into a case dict.

    Pure by design — persistence and pipeline wiring are later slices;
    this function is the seam they will attach to.
    """
    sane = sanitize_record(record)
    return {
        "id": _case_id(sane),
        "scenario": sane.wrong_assumption,
        "rejection_reason": sane.reason,
        "expected_fix_path": sane.valid_fix_path,
        "source": "rejection_learning",
    }


def build_eval_cases(records: Iterable[RejectionRecord]) -> list[dict[str, str]]:
    """Evaluation-case hook over many records; empty scenarios are skipped."""
    cases = [build_eval_case(record) for record in records]
    return [case for case in cases if case["scenario"].strip()]


__all__ = [
    "RejectionRecord",
    "RejectionRule",
    "build_eval_case",
    "build_eval_cases",
    "extract_rules",
    "sanitize_record",
]
