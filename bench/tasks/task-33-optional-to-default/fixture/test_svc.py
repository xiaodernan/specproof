# mypy: ignore-errors
"""Visible tests for task-33 (executed in the isolated fixture repo)."""

from svc import greet


def test_named_greeting() -> None:
    assert greet("bob") == "Hello, bob"


def test_no_argument_defaults_to_guest() -> None:
    assert greet() == "Hello, guest"
