# mypy: ignore-errors
"""Hidden judge tests for task-04: acceptance + no-regression guards."""

import inspect

import svc
from svc import format_amount


def test_dead_definition_really_removed() -> None:
    module_source = inspect.getsource(svc)
    assert module_source.count("def format_amount") == 1
    assert "// 100" not in module_source


def test_more_formatting_cases() -> None:
    assert format_amount(0) == "0.00"
    assert format_amount(199) == "1.99"
    assert format_amount(-150) == "-1.50"
