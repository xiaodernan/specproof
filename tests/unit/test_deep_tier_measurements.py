"""The DEEP budget must fit the work that was actually measured.

`storage/mysql.py` carries `DEPTH_EXECUTION_BUDGET_SECONDS` as the
expiry reaper's deadline: a job still working when the budget runs out
is killed. The numbers were estimates for a long time. The first real
measurement (2026-10-22, DEEP tier, one contract, 1450 s) is recorded
in `docs/eval/deep-tier-measurements.md`.

This test ties the record to the code: every measured duration must
fit inside its tier's budget. Lower the budget below something that
was already measured and this test goes red - which is the point: the
budget is a promise to the work, and a promise that was never measured
is a guess.

The reverse is NOT asserted: a measurement far below the budget does
not mean the budget should shrink (the budget is a ceiling, not a
target, and n=1 is not a distribution).
"""

from __future__ import annotations

import re
from pathlib import Path

from storage.mysql import DEPTH_EXECUTION_BUDGET_SECONDS

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "eval" / "deep-tier-measurements.md"

# | date | tier | case | contracts | seconds | verdict | findings | machine |
_ROW = re.compile(
    r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(FAST|DEEP|RELEASE)\s*\|"
    r"([^|]*)\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
    re.M,
)


def _rows() -> list[tuple[str, str, int, int]]:
    """(tier, case, contracts, seconds) for every recorded measurement."""
    text = DOC.read_text(encoding="utf-8")
    return [
        (m.group(1), m.group(2).strip(), int(m.group(3)), int(m.group(4)))
        for m in _ROW.finditer(text)
    ]


def test_the_measurement_record_exists() -> None:
    assert DOC.exists(), (
        f"{DOC} is missing - the DEEP budget is a guess without it"
    )
    rows = _rows()
    assert rows, (
        f"{DOC} has no measurement row (the table's header row is "
        f"expected, the rows look like: | 2026-10-22 | DEEP | case | 1 | 1450 | ... |)"
    )


def test_every_measurement_fits_its_tier_budget() -> None:
    for tier, case, _contracts, seconds in _rows():
        budget = DEPTH_EXECUTION_BUDGET_SECONDS[tier]
        assert seconds < budget, (
            f"{case} took {seconds}s at the {tier} tier, but the budget is "
            f"{budget}s - the expiry reaper would kill a job that was "
            f"still working. Either raise the budget or record why the "
            f"measurement is not representative."
        )


def test_the_record_states_how_thin_it_is() -> None:
    """A measurement record that hides its own sample size is a lie by
    omission: the doc must say how many samples it has."""
    text = DOC.read_text(encoding="utf-8")
    match = re.search(r"sample-count:\s*(\d+)", text)
    assert match, (
        f"{DOC} must state 'sample-count: N' so the reader cannot mistake "
        f"one measurement for a distribution"
    )
    assert int(match.group(1)) == len(_rows()), (
        f"{DOC} says sample-count: {match.group(1)} but the table has "
        f"{len(_rows())} rows - the count must follow the evidence"
    )
