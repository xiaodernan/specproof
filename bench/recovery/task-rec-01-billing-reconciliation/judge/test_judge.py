# mypy: ignore-errors
"""Hidden judge tests for task-rec-01: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import parse_rows, summarize


def test_phase1_still_works() -> None:
    rows = parse_rows("id,amount\n7,1.5\n")
    assert rows == [{"id": "7", "amount": "1.5"}]


def test_phase2_hidden_cases() -> None:
    assert summarize([]) == {"total": 0.0, "count": 0}
    assert summarize([{"amount": "-5"}, {"amount": "2.5"}]) == {"total": -2.5, "count": 2}


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "parse_rows applied" in line) == 1
    assert len(lines) == 1
