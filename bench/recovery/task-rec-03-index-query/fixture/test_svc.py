# mypy: ignore-errors
"""Visible tests for task-rec-03 (executed in the isolated fixture repo)."""

from svc import build_index, query_index


def test_phase1_build() -> None:
    index = build_index({"d1": "a b", "d2": "b c"})
    assert index["b"] == {"d1", "d2"}


def test_phase2_query() -> None:
    index = build_index({"d1": "a b", "d2": "b c"})
    assert sorted(query_index(index, "b")) == ["d1", "d2"]
