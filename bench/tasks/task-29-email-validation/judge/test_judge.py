# mypy: ignore-errors
"""Hidden judge tests for task-29: acceptance + no-regression guards."""

from api import validate_email


def test_plus_tag_passes() -> None:
    assert validate_email("user+tag@example.com") == []


def test_subdomain_passes() -> None:
    assert validate_email("a@mail.example.co.uk") == []


def test_empty_string_rejected() -> None:
    assert validate_email("") != []


def test_double_at_rejected() -> None:
    assert validate_email("a@@b.c") != []
