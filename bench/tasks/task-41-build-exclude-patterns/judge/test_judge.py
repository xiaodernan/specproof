# mypy: ignore-errors
"""Hidden judge tests for task-41: acceptance + no-regression guards."""

from build import collect_sources


def test_hidden_and_non_py_skipped(tmp_path) -> None:
    (tmp_path / ".secret.py").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    (tmp_path / "main.py").write_text("", encoding="utf-8")
    assert collect_sources(str(tmp_path), []) == ["main.py"]


def test_multiple_patterns(tmp_path) -> None:
    (tmp_path / "keep.py").write_text("", encoding="utf-8")
    (tmp_path / "test_a.py").write_text("", encoding="utf-8")
    (tmp_path / "legacy_b.py").write_text("", encoding="utf-8")
    assert collect_sources(str(tmp_path), ["test_*.py", "legacy_*"]) == ["keep.py"]


def test_exact_name_still_works(tmp_path) -> None:
    (tmp_path / "one.py").write_text("", encoding="utf-8")
    (tmp_path / "two.py").write_text("", encoding="utf-8")
    assert collect_sources(str(tmp_path), ["two.py"]) == ["one.py"]
