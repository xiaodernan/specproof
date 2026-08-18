# mypy: ignore-errors
"""Hidden judge tests for task-rec-03: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import build_index, query_index


def test_phase1_still_works() -> None:
    index = build_index({"x": "hello world"})
    assert index["hello"] == {"x"}


def test_phase2_hidden_cases() -> None:
    index = build_index({"d1": "a"})
    assert query_index(index, "missing") == []
    assert query_index(index, "a") == ["d1"]


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "build_index applied" in line) == 1
    assert len(lines) == 1
