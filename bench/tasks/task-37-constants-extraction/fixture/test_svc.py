# mypy: ignore-errors
"""Visible tests for task-37 (executed in the isolated fixture repo)."""

from constants import DEFAULT_TIMEOUT, MAX_RETRIES
from svc import timeout_limit


def test_constants_module_exists() -> None:
    assert DEFAULT_TIMEOUT == 30
    assert MAX_RETRIES == 3


def test_timeout_limit_unchanged() -> None:
    assert timeout_limit() == 90
