# mypy: ignore-errors
"""Hidden judge tests for task-rec-07: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import collect_metrics, render_report


def test_phase1_still_works() -> None:
    assert collect_metrics([]) == {}


def test_phase2_hidden_cases() -> None:
    assert render_report({}) == ""
    assert render_report({"a": 1}) == "a=1\n"


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "collect_metrics applied" in line) == 1
    assert len(lines) == 1
