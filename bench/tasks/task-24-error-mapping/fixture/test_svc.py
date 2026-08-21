# mypy: ignore-errors
"""Visible tests for task-24 (executed in the isolated fixture repo)."""

from api import user_endpoint


def test_existing_user() -> None:
    store = {"u1": {"name": "alice"}}
    assert user_endpoint(store, "u1") == {"status": 200, "user": {"name": "alice"}}


def test_missing_user_maps_to_404() -> None:
    assert user_endpoint({}, "nope") == {"status": 404, "error": "not_found"}
