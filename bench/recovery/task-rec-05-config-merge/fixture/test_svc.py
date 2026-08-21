# mypy: ignore-errors
"""Visible tests for task-rec-05 (executed in the isolated fixture repo)."""

from svc import load_defaults, merge_overrides


def test_phase1_defaults() -> None:
    assert load_defaults()["port"] == 8000


def test_phase2_merge() -> None:
    merged = merge_overrides(load_defaults(), {"host": "10.0.0.9", "debug": None})
    assert merged == {"host": "10.0.0.9", "port": 8000, "debug": False}
