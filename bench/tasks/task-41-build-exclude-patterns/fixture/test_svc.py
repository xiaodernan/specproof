# mypy: ignore-errors
"""Visible tests for task-41 (executed in the isolated fixture repo)."""

from build import collect_sources


def test_glob_exclude_pattern(tmp_path) -> None:
    (tmp_path / "app.py").write_text("", encoding="utf-8")
    (tmp_path / "test_app.py").write_text("", encoding="utf-8")
    assert collect_sources(str(tmp_path), ["test_*.py"]) == ["app.py"]


def test_sorted_output(tmp_path) -> None:
    for name in ("b.py", "a.py"):
        (tmp_path / name).write_text("", encoding="utf-8")
    assert collect_sources(str(tmp_path), []) == ["a.py", "b.py"]
