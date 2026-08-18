# mypy: ignore-errors
"""Visible tests for task-rec-09 (executed in the isolated fixture repo)."""

from datetime import datetime

from svc import from_json_compatible, to_json_compatible


def test_phase1_encode() -> None:
    dt = datetime(2026, 8, 18, 12, 0, 0)
    assert to_json_compatible({"dt": dt}) == {"dt": "2026-08-18T12:00:00"}


def test_phase2_decode() -> None:
    result = from_json_compatible({"dt": "2026-08-18T12:00:00"})
    assert result == {"dt": datetime(2026, 8, 18, 12, 0, 0)}
