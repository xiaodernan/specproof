# mypy: ignore-errors
"""Visible tests for task-13 (executed in the isolated fixture repo)."""

from svc import parse_payload


def test_valid_payload_roundtrip() -> None:
    assert parse_payload('{"a": 1}') == {"a": 1}


def test_malformed_payload_returns_empty() -> None:
    assert parse_payload("{bad") == {}
