# mypy: ignore-errors
"""Visible tests for task-50 (executed in the isolated fixture repo)."""

from build import entrypoint_lines


def test_entrypoint_contract() -> None:
    lines = entrypoint_lines()
    assert lines[0] == "#!/bin/sh"
    assert lines[-1] == "exec python app.py"
