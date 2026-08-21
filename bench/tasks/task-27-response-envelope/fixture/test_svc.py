# mypy: ignore-errors
"""Visible tests for task-27 (executed in the isolated fixture repo)."""

from api import to_envelope


def test_flat_conversion() -> None:
    row = {"user_id": 1, "display_name": "A"}
    assert to_envelope(row) == {"userId": 1, "displayName": "A"}


def test_input_not_mutated() -> None:
    row = {"user_id": 1}
    to_envelope(row)
    assert row == {"user_id": 1}
