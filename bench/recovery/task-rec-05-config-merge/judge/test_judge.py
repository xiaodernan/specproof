# mypy: ignore-errors
"""Hidden judge tests for task-rec-05: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import load_defaults, merge_overrides


def test_phase1_still_works() -> None:
    defaults = load_defaults()
    assert defaults["debug"] is False


def test_phase2_hidden_cases() -> None:
    defaults = load_defaults()
    merged = merge_overrides(defaults, {})
    assert merged == defaults and merged is not defaults
    merged = merge_overrides(defaults, {"port": None, "host": "x"})
    assert merged == {"host": "x", "port": 8000, "debug": False}


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "load_defaults applied" in line) == 1
    assert len(lines) == 1
