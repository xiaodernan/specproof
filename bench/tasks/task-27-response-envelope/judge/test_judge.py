# mypy: ignore-errors
"""Hidden judge tests for task-27: acceptance + no-regression guards."""

from api import to_envelope


def test_nested_conversion() -> None:
    row = {"user_id": 1, "profile_data": {"full_name": "A", "age": 3}}
    assert to_envelope(row) == {"userId": 1, "profileData": {"fullName": "A", "age": 3}}


def test_keys_without_underscore_unchanged() -> None:
    assert to_envelope({"id": 9, "name": "x"}) == {"id": 9, "name": "x"}


def test_empty_dict() -> None:
    assert to_envelope({}) == {}
