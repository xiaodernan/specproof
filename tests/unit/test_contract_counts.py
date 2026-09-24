"""#64 — a count that was never taken must not render as zero.

Two renderers turn a persisted job summary into text an outside party quotes:
the GitHub Check Run output and the notification templates. Both used
``summary.get(key, 0)``, so the absence of statistics printed as
``Contracts: 0 total — 0 passed, 0 failed, 0 unverified.`` The failure path
made that concrete by passing literal zeros for numbers the pipeline never
reached.

The notify templates are not wired to any production sender yet (nothing
outside ``integrations/notify`` and its tests imports them); they are pinned
here so that when a sender is connected it cannot inherit the old lie.
"""
from __future__ import annotations

from typing import Any

from integrations.contract_counts import (
    COUNT_KEYS,
    NOT_COUNTED,
    count_sentence,
    counted,
)
from integrations.github_checks import check_summary_text
from integrations.notify.templates import blocks_for_summary, text_for_summary

FULL: dict[str, Any] = {
    "verdict": "BLOCKED",
    "contracts_total": 4,
    "matrix_passed": 3,
    "matrix_failed": 1,
    "matrix_unverified": 0,
    "findings": [],
}


def test_every_count_present_renders_the_tally() -> None:
    # Byte-for-byte the historical line: this change must not move the
    # wording of a job that really did count.
    assert (
        count_sentence(FULL)
        == "4 total — 3 passed, 1 failed, 0 unverified"
    )


def test_a_zero_that_was_measured_still_renders_as_zero() -> None:
    zeroed = dict(FULL, contracts_total=0, matrix_passed=0, matrix_failed=0)
    assert count_sentence(zeroed) == "0 total — 0 passed, 0 failed, 0 unverified"


def test_absent_counts_render_as_absence_not_as_zero() -> None:
    """The regression this batch fixes: a run that never counted anything."""
    text = check_summary_text("FAILED", {"verdict": "FAILED", "errors": ["boom"]})
    assert "not counted" in text
    assert "0 total" not in text
    assert NOT_COUNTED in count_sentence({"verdict": "FAILED"})
    assert counted({"verdict": "FAILED"}) is None


def test_partial_counts_are_not_presented_as_a_tally() -> None:
    """A total without its split would still be read as a complete tally."""
    assert counted({"contracts_total": 4}) is None
    assert count_sentence({"contracts_total": 4}) == NOT_COUNTED


def test_non_counts_are_not_counts() -> None:
    """True, "3" and -1 are not statistics; rendering them as numbers lies."""
    for value in (True, "3", -1, 1.5, None, {}, []):
        assert counted(dict(FULL, contracts_total=value)) is None, value
    # An integral float is still a count (JSON round-trips keep ints, but a
    # 4.0 must not be reported as "not counted" either).
    assert counted(dict(FULL, contracts_total=4.0)) is not None


def test_findings_absent_differs_from_findings_none() -> None:
    absent = check_summary_text("FAILED", {"verdict": "FAILED"})
    empty = check_summary_text("VERIFIED", dict(FULL, verdict="VERIFIED"))
    assert "not recorded for this run" in absent
    assert "**Findings:** none." in empty
    assert "none." not in absent


def test_errors_reach_the_check_run_text() -> None:
    text = check_summary_text(
        "FAILED", {"verdict": "FAILED", "errors": ["mvnw timed out", "git failed"]}
    )
    assert "**Errors:**" in text
    assert "- mvnw timed out" in text
    assert "- git failed" in text


def test_truncated_errors_say_how_many_were_left_out() -> None:
    errors = [f"e{i}" for i in range(5)]
    text = check_summary_text("FAILED", {"verdict": "FAILED", "errors": errors})
    assert "… 2 more" in text
    for shown in errors[:3]:
        assert shown in text


def test_notification_text_shares_the_count_semantics() -> None:
    assert (
        "Contracts: 4 total — 3 passed, 1 failed, 0 unverified."
        in text_for_summary("BLOCKED", FULL)
    )
    plain = text_for_summary("FAILED", {"verdict": "FAILED"})
    assert "Contracts: not counted" in plain
    assert "0 total" not in plain


def test_notification_blocks_never_show_a_half_tally() -> None:
    blocks = blocks_for_summary("job-1", "FAILED", {"verdict": "FAILED"})
    fields = blocks[1]["fields"]
    texts = [f["text"] for f in fields]
    assert "*Contracts:* not counted" in texts
    assert "*Matrix:* not counted" in texts
    assert not any(ch.isdigit() for ch in texts[2] + texts[3])
    counted_blocks = [
        f["text"] for f in blocks_for_summary("job-1", "BLOCKED", FULL)[1]["fields"]
    ]
    assert "*Contracts:* 4" in counted_blocks


def test_counted_keys_are_the_ones_the_summary_persists() -> None:
    """The renderer and the writer must agree on the field names."""
    import agent.worker as worker_module

    state = {
        "contracts": [{"id": "C-1"}],
        "matrix": {"passed": 1, "failed": 0, "unverified": 0, "rows": []},
        "confirmed_findings": [],
        "errors": [],
    }
    summary = worker_module._state_summary(state, "VERIFIED")
    assert set(COUNT_KEYS) <= set(summary)
    assert counted(summary) is not None
