# mypy: ignore-errors
"""Hidden judge tests for task-33: acceptance + no-regression guards."""

import inspect

from svc import greet


def test_signature_has_guest_default() -> None:
    signature = inspect.signature(greet)
    assert signature.parameters["name"].default == "guest"


def test_none_treated_as_guest() -> None:
    assert greet(None) == "Hello, guest"


def test_empty_string_treated_as_guest() -> None:
    assert greet("") == "Hello, guest"
