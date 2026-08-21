"""Notification templates for verification terminal events.

Maps the persisted job summary shape (agent.worker._state_summary: verdict,
contracts_total, matrix_passed/matrix_failed/matrix_unverified, findings,
capsules, report_path, retrieval_note, errors) onto a Notification for the
four terminal events VERIFIED / BLOCKED / FAILED / NEEDS_REVIEW.

The CLI spells the review verdict with spaces ("NEEDS REVIEW", "NEEDS REVIEW
(verification incomplete)"); normalize_verdict folds every spelling onto the
canonical NEEDS_REVIEW. Unknown verdicts raise ValueError — a template must
never fabricate a terminal event.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from integrations.notify.protocol import Notification

TERMINAL_VERDICTS: frozenset[str] = frozenset(
    {"VERIFIED", "BLOCKED", "FAILED", "NEEDS_REVIEW"}
)

_VERDICT_TITLES: dict[str, str] = {
    "VERIFIED": "SpecProof verification passed",
    "BLOCKED": "SpecProof verification blocked — human review required",
    "FAILED": "SpecProof verification failed",
    "NEEDS_REVIEW": "SpecProof verification needs review",
}

_MAX_FINDINGS_IN_TEXT = 10
_MAX_FINDINGS_IN_BLOCKS = 5


def normalize_verdict(verdict: str) -> str:
    """Fold every spelling of a terminal verdict onto its canonical name."""
    compact = " ".join(verdict.upper().split())
    if compact in TERMINAL_VERDICTS:
        return compact
    if compact.startswith("NEEDS REVIEW"):
        return "NEEDS_REVIEW"
    return compact


def _require_terminal(verdict: str) -> str:
    if verdict not in TERMINAL_VERDICTS:
        raise ValueError(
            f"unsupported terminal verdict {verdict!r}; expected one of "
            + ", ".join(sorted(TERMINAL_VERDICTS))
        )
    return verdict


def event_type_for_verdict(verdict: str) -> str:
    """Dotted event name for a terminal verdict (verification.<verdict>)."""
    return "verification." + _require_terminal(verdict).lower()


def title_for_verdict(verdict: str) -> str:
    """Human title for a terminal verdict."""
    return _VERDICT_TITLES[_require_terminal(verdict)]


def text_for_summary(verdict: str, summary: Mapping[str, Any]) -> str:
    """Plain-text rendering of the persisted job summary fields."""
    lines = [
        f"Verdict: {verdict}",
        (
            f"Contracts: {summary.get('contracts_total', 0)} total — "
            f"{summary.get('matrix_passed', 0)} passed, "
            f"{summary.get('matrix_failed', 0)} failed, "
            f"{summary.get('matrix_unverified', 0)} unverified."
        ),
    ]
    findings = summary.get("findings") or []
    for finding in findings[:_MAX_FINDINGS_IN_TEXT]:
        if not isinstance(finding, Mapping):
            continue
        lines.append(
            f"- [{finding.get('severity', '?')}] "
            f"{finding.get('contract_id', '?')}: "
            f"{str(finding.get('description') or '')[:200]}"
        )
    errors = summary.get("errors") or []
    if errors:
        lines.append(f"Errors: {len(errors)}")
    capsules = summary.get("capsules") or []
    if capsules:
        lines.append(f"Capsules: {len(capsules)}")
    report_path = str(summary.get("report_path") or "")
    if report_path:
        lines.append(f"Report: {report_path}")
    return "\n".join(lines)


def blocks_for_summary(
    job_id: str, verdict: str, summary: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Slack-block-style rendering: header, matrix fields, findings, context."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title_for_verdict(verdict)},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Job:* `{job_id}`"},
                {"type": "mrkdwn", "text": f"*Verdict:* {verdict}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Contracts:* {summary.get('contracts_total', 0)}",
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Matrix:* {summary.get('matrix_passed', 0)} passed / "
                        f"{summary.get('matrix_failed', 0)} failed / "
                        f"{summary.get('matrix_unverified', 0)} unverified"
                    ),
                },
            ],
        },
    ]
    findings = summary.get("findings") or []
    rendered: list[str] = []
    for finding in findings[:_MAX_FINDINGS_IN_BLOCKS]:
        if not isinstance(finding, Mapping):
            continue
        rendered.append(
            f"• [{finding.get('severity', '?')}] "
            f"{finding.get('contract_id', '?')}: "
            f"{str(finding.get('description') or '')[:120]}"
        )
    if rendered:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Findings:*\n" + "\n".join(rendered),
                },
            }
        )
    context: list[str] = []
    capsules = summary.get("capsules") or []
    if capsules:
        context.append(f"Capsules: {len(capsules)}")
    report_path = str(summary.get("report_path") or "")
    if report_path:
        context.append(f"Report: {report_path}")
    if context:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " | ".join(context)}],
            }
        )
    return blocks


def build_terminal_notification(
    job_id: str, summary: Mapping[str, Any]
) -> Notification:
    """Map a persisted job summary onto a terminal-event Notification."""
    verdict = normalize_verdict(str(summary.get("verdict", "")))
    _require_terminal(verdict)
    return Notification(
        event_type=event_type_for_verdict(verdict),
        title=title_for_verdict(verdict),
        text=text_for_summary(verdict, summary),
        blocks=tuple(blocks_for_summary(job_id, verdict, summary)),
        job_id=job_id,
    )
