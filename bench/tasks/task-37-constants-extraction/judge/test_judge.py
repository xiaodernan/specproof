# mypy: ignore-errors
"""Hidden judge tests for task-37: acceptance + no-regression guards."""

import inspect

import svc
from constants import DEFAULT_TIMEOUT, MAX_RETRIES


def test_no_literal_definitions_in_svc() -> None:
    source = inspect.getsource(svc)
    assert "DEFAULT_TIMEOUT = 30" not in source
    assert "MAX_RETRIES = 3" not in source


def test_svc_uses_imported_constants() -> None:
    assert svc.timeout_limit() == DEFAULT_TIMEOUT * MAX_RETRIES
