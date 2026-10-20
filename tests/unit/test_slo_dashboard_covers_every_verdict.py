"""The SLO dashboard must show every verdict the policy can produce.

A verdict that is counted but not displayed is invisible to the person
who reads the dashboard — and "invisible" is worse than "absent":
the panel next to it says "BLOCKED: 0", and a reader concludes that
nothing is wrong.

The policy can produce four words (VERIFIED / BLOCKED / NEEDS_REVIEW /
FAILED), and the worker emits `jobs_<verdict>_total` for whichever one
it got. The dashboard used to show two of them, so the NEEDS_REVIEW
bucket — the one that says "a human has to look" — was not on the
screen at all.

This file pins the coverage both ways: every word the policy can
produce has a panel, and the dashboard names no word the policy cannot
produce.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from evidence.verdict import VERDICT_VOCABULARY

REPO = Path(__file__).resolve().parents[2]
DASHBOARD = REPO / "infra" / "grafana" / "dashboards" / "specproof-slo.json"

#: The metric family the worker emits: jobs_<verdict>_total.
_VERDICT_PANEL_RE = re.compile(r"specproof_jobs_([a-z_]+)_total")


def _panel_expressions() -> dict[str, str]:
    """Every verdict-family expression the dashboard queries, by verdict."""
    raw = DASHBOARD.read_text(encoding="utf-8")
    data = json.loads(raw)  # the dashboard must be valid JSON at all
    found: dict[str, str] = {}
    for panel in data.get("panels", []):
        for target in panel.get("targets", []) or []:
            expr = str(target.get("expr") or "")
            for match in _VERDICT_PANEL_RE.finditer(expr):
                found[match.group(1)] = expr
    return found


class TestTheDashboardShowsEveryVerdict:
    def test_the_dashboard_is_valid_json(self) -> None:
        json.loads(DASHBOARD.read_text(encoding="utf-8"))

    def test_every_verdict_the_policy_can_produce_is_on_the_dashboard(self) -> None:
        shown = set(_panel_expressions())
        missing = {
            verdict.lower() for verdict in VERDICT_VOCABULARY
        } - shown
        assert not missing, (
            f"the SLO dashboard does not show {sorted(missing)} — a verdict "
            "that is counted but not displayed is invisible to the reader, "
            "and the panel beside it says '0', so they conclude nothing is "
            "wrong"
        )

    def test_the_dashboard_names_no_verdict_the_policy_cannot_produce(self) -> None:
        shown = set(_panel_expressions())
        extra = shown - {verdict.lower() for verdict in VERDICT_VOCABULARY}
        # `jobs_completed_total` is the family's own counter, not a verdict.
        extra.discard("completed")
        assert not extra, (
            f"the dashboard plots verdict-family counters for {sorted(extra)}, "
            "which the policy cannot produce — a panel that can only ever "
            "read zero"
        )

    def test_the_needs_review_bucket_is_named_in_the_panel_title(self) -> None:
        """The panel must SAY which bucket is which.

        A reader who sees four numbers with no labels cannot tell
        "blocked" from "needs review", and the two call for different
        people to act.
        """
        raw = DASHBOARD.read_text(encoding="utf-8")
        data = json.loads(raw)
        titled = [
            str(panel.get("title") or "")
            for panel in data.get("panels", [])
        ]
        assert any("NEEDS_REVIEW" in title for title in titled), titled


@pytest.mark.parametrize("verdict", sorted(VERDICT_VOCABULARY))
def test_each_verdict_has_its_own_expression(verdict: str) -> None:
    found = _panel_expressions()
    assert verdict.lower() in found, (
        f"{verdict} has no panel expression; the worker emits "
        f"jobs_{verdict.lower()}_total for it"
    )
