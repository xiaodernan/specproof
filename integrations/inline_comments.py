"""Inline Finding comment construction (P5, spec section 6.2 GitHub output).

Turns confirmed findings + per-file diffs into GitHub pull-request review
comments anchored on lines that EXIST in the head file. Anchoring rules:

- The comment is anchored to the first CONTEXT line of the matching hunk,
  never to a removed line: a comment on a deleted line has no anchor in the
  PR's head commit and GitHub rejects it.
- A finding whose file has no usable hunk context is skipped, not guessed:
  publishing a comment at a fabricated line would violate the evidence
  policy ("no comment without evidence location").
- At most INLINE_MAX comments per review, deduplicated by (path, line),
  ordered by severity (BLOCKER > MAJOR > MINOR > rest), then confidence.

This module is pure: no network, no env — the GitHub client call lives in
integrations.github_checks.publish_inline_findings. (#182: the evidence
gate below counts refusals into the in-process metrics registry — still no
network, no env.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from observability.metrics import incr

INLINE_MAX = 8

#: §14 质量目标 "无证据严重评论 = 0" (#182): the severe levels the evidence
#: gate refuses to publish without an evidence kind — the band the BLOCKER
#: six-conditions policy guards at the court layer, mirrored here at the
#: comment boundary.
_SEVERE_LEVELS = frozenset({"BLOCKER", "MAJOR"})

#: Evidence-kind values that mean "no evidence": unset, or the module's own
#: rendering default for a missing kind (the _comment_body fallback).
_NO_EVIDENCE_KINDS = frozenset({"", "unknown", "?"})


def _lacks_evidence(finding: dict[str, Any]) -> bool:
    return (
        str(finding.get("evidence_type", "")).strip().lower()
        in _NO_EVIDENCE_KINDS
    )


_SEVERITY_RANK = {
    "BLOCKER": 0,
    "MAJOR": 1,
    "MINOR": 2,
    "NEEDS_CONFIRMATION": 3,
    "NONE": 4,
}

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class _Hunk:
    new_start: int
    minus_lines: list[str] = field(default_factory=list)
    body: list[str] = field(default_factory=list)

    def matching_minus(self, predicate: Any) -> bool:
        return any(predicate(line) for line in self.minus_lines)

    def anchor(self) -> int | None:
        """1-based line number (head file) of the first context line."""
        line_no = self.new_start
        for raw in self.body:
            if raw.startswith(" "):
                return line_no
            if not raw.startswith("-"):
                line_no += 1
        return None


def parse_hunks(diff_text: str) -> list[_Hunk]:
    """Parse unified diff text into hunks (tests use this directly)."""
    hunks: list[_Hunk] = []
    current: _Hunk | None = None
    for line in diff_text.splitlines():
        match = _HUNK_RE.match(line)
        if match:
            current = _Hunk(new_start=int(match.group(1)))
            hunks.append(current)
            continue
        if current is None:
            continue
        if line.startswith("-") and not line.startswith("---"):
            current.minus_lines.append(line[1:])
        if line.startswith((" ", "-", "+")):
            current.body.append(line)
    return hunks


def _minus_predicate(finding: dict[str, Any]) -> Any:
    """Return the hunk-minus matcher for a finding type, or None (any)."""
    ftype = finding.get("type", "")
    if ftype == "annotation_removed":
        return lambda line: line.lstrip().startswith("@")
    if ftype in ("guard_removed", "forbidden_token_guard_removal"):
        return lambda line: (
            "invalidateOldTokens" in line or "redisTemplate" in line
        )
    if ftype in (
        "duplicate_publish",
        "forbidden_duplicate_publish",
        "routing_key_changed",
        "event_once",
    ):
        return lambda line: "convertAndSend" in line or "publish" in line
    if ftype in ("validation_removed",):
        return lambda line: re.match(
            r"\s*@(NotBlank|NotNull|Size|Email|Valid)\b", line
        ) is not None
    return None


def locate_finding(
    finding: dict[str, Any], diff_by_file: dict[str, str]
) -> tuple[str, int] | None:
    """Map a finding to a (path, line) anchor in the head file, or None.

    Never fabricates: returns None when the path is absent from the diff or
    no hunk has a context line to anchor on.
    """
    path = finding.get("location") or finding.get("path") or ""
    if not path or path not in diff_by_file:
        return None
    hunks = parse_hunks(diff_by_file[path])
    if not hunks:
        return None
    predicate = _minus_predicate(finding)
    if predicate:
        candidates = [h for h in hunks if h.matching_minus(predicate)]
    else:
        candidates = [h for h in hunks if h.minus_lines]
    if not candidates:
        candidates = hunks
    for hunk in candidates:
        anchor = hunk.anchor()
        if anchor is not None:
            return path, anchor
    return None


def _comment_body(finding: dict[str, Any]) -> str:
    severity = finding.get("severity", "?")
    contract_id = finding.get("contract_id", "?")
    description = (finding.get("description") or "")[:240]
    evidence_type = finding.get("evidence_type", "unknown")
    confidence = finding.get("confidence", 0.0)
    confidence_text = f"{confidence:.2f}" if confidence else "n/a"
    return "\n".join([
        f"**[{severity}] {contract_id}** — {description}",
        "",
        f"Evidence: `{evidence_type}` (confidence {confidence_text}). "
        "Reproduce with `specproof replay` on the Bug Capsule attached to "
        "this verification job.",
    ])


def build_review_comments(
    findings: list[dict[str, Any]],
    diff_by_file: dict[str, str],
    max_comments: int = INLINE_MAX,
) -> list[dict[str, Any]]:
    """Build the review-comment payload list (path, line, side, body).

    Severity-ordered, location-deduplicated, capped at max_comments.
    Severe findings (BLOCKER/MAJOR) without an evidence kind are refused
    outright and counted — never published (#182, §6 无证据严重评论=0).
    Findings that cannot be anchored honestly are silently dropped here;
    callers can see the count difference against the input.
    """
    ranked = sorted(
        findings,
        key=lambda f: (
            _SEVERITY_RANK.get(str(f.get("severity", "")).upper(), 9),
            -float(f.get("confidence") or 0.0),
            str(f.get("id", "")),
        ),
    )
    comments: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for finding in ranked:
        # §6 "无证据严重评论=0" (#182): the evidence gate, made countable.
        # A BLOCKER/MAJOR comment with no evidence kind behind it must never
        # reach the PR — refusal IS the policy (same honesty family as the
        # anchoring skip below); the counter makes the refusal auditable and
        # the SLO is the counter staying at zero.
        if (
            str(finding.get("severity", "")).upper() in _SEVERE_LEVELS
            and _lacks_evidence(finding)
        ):
            incr("severe_comments_without_evidence_total")
            continue
        located = locate_finding(finding, diff_by_file)
        if located is None:
            continue
        path, line = located
        key = (path, line)
        if key in seen:
            continue
        seen.add(key)
        comments.append({
            "path": path,
            "line": line,
            "side": "RIGHT",
            "body": _comment_body(finding),
        })
        if len(comments) >= max_comments:
            break
    return comments
