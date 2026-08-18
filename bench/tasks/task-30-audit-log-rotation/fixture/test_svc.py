# mypy: ignore-errors
"""Visible tests for task-30 (executed in the isolated fixture repo)."""

from api import log_event


def test_entries_accumulate(tmp_path) -> None:
    path = tmp_path / "audit.log"
    log_event(str(path), "first")
    log_event(str(path), "second")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["first", "second"]


def test_returns_logged() -> None:
    assert log_event("missing-dir/file.log", "x") == "logged"
