# mypy: ignore-errors
"""Hidden judge tests for task-50: acceptance + no-regression guards."""

from pathlib import Path

from build import entrypoint_lines


def test_script_fixed() -> None:
    text = Path("deploy/entrypoint.sh").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "#!/bin/sh"
    assert lines[-1] == "exec python app.py"


def test_build_and_file_agree() -> None:
    text = Path("deploy/entrypoint.sh").read_text(encoding="utf-8")
    assert text.splitlines() == entrypoint_lines()
