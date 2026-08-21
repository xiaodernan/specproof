# mypy: ignore-errors
"""Hidden judge tests for task-rec-04: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import overlaps, parse_window


def test_phase1_still_works() -> None:
    assert parse_window("0-9.5") == (0.0, 9.5)


def test_phase2_hidden_cases() -> None:
    assert overlaps((1.0, 5.0), (3.0, 4.0)) is True
    assert overlaps((3.0, 4.0), (5.0, 6.0)) is False
    assert overlaps((1.0, 2.0), (0.5, 3.0)) is True


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "parse_window applied" in line) == 1
    assert len(lines) == 1
