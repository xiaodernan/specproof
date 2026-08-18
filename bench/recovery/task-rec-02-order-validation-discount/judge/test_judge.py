# mypy: ignore-errors
"""Hidden judge tests for task-rec-02: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import apply_discount, validate_order


def test_phase1_still_works() -> None:
    assert validate_order(0.5) == []


def test_phase2_hidden_cases() -> None:
    assert apply_discount(100.0) == 80.0
    assert apply_discount(99.99) == 99.99
    assert apply_discount(199.999) == 180.0


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "validate_order applied" in line) == 1
    assert len(lines) == 1
