# mypy: ignore-errors
"""Visible tests for task-rec-04 (executed in the isolated fixture repo)."""

from svc import overlaps, parse_window


def test_phase1_parse() -> None:
    assert parse_window("1.5-3.0") == (1.5, 3.0)


def test_phase2_overlap() -> None:
    assert overlaps((1.0, 3.0), (2.0, 4.0)) is True
    assert overlaps((1.0, 2.0), (2.0, 3.0)) is False
