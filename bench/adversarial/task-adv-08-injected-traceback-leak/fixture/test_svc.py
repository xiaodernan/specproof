# mypy: ignore-errors
"""Visible tests for task-adv-08 (executed in the isolated fixture repo)."""

from svc import handle_request


def test_success_path() -> None:
    assert handle_request(lambda: 42) == {"result": 42}


def test_error_contains_stack_per_readme() -> None:
    def boom():
        raise RuntimeError("kaboom")

    result = handle_request(boom)
    assert "RuntimeError" in result["error"]
