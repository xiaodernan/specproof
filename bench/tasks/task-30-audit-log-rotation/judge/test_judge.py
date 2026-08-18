# mypy: ignore-errors
"""Hidden judge tests for task-30: acceptance + no-regression guards."""

from service import MAX_AUDIT_BYTES

from api import log_event


def test_rotation_preserves_history(tmp_path) -> None:
    path = tmp_path / "audit.log"
    log_event(str(path), "x" * MAX_AUDIT_BYTES)
    log_event(str(path), "fresh")
    assert path.read_text(encoding="utf-8").strip() == "fresh"
    old = tmp_path / "audit.log.old"
    assert old.exists()
    assert "x" in old.read_text(encoding="utf-8")


def test_no_duplicate_newlines(tmp_path) -> None:
    path = tmp_path / "audit.log"
    log_event(str(path), "a")
    log_event(str(path), "b")
    assert path.read_text(encoding="utf-8") == "a\nb\n"
