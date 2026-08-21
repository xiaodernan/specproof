# mypy: ignore-errors
"""Hidden judge tests for task-rec-09: 恢复成功 + 幂等 (无重复副作用)."""

from datetime import datetime
from pathlib import Path

from svc import from_json_compatible, to_json_compatible


def test_phase1_still_works() -> None:
    assert to_json_compatible({"n": 1}) == {"n": 1}


def test_phase2_hidden_cases() -> None:
    assert from_json_compatible({"dt": "not-a-date"}) == {"dt": "not-a-date"}
    assert from_json_compatible({"dt": "2026-01-01T00:00:00", "n": 5}) == {
        "dt": datetime(2026, 1, 1, 0, 0, 0),
        "n": 5,
    }


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "to_json_compatible applied" in line) == 1
    assert len(lines) == 1
