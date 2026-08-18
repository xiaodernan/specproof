# mypy: ignore-errors
"""Visible tests for task-19 (executed in the isolated fixture repo)."""

from svc import read_lines


def test_ascii_content(tmp_path) -> None:
    path = tmp_path / "plain.txt"
    path.write_text("a\nb\n", encoding="utf-8")
    assert read_lines(str(path)) == ["a", "b"]


def test_utf8_content(tmp_path) -> None:
    path = tmp_path / "cn.txt"
    path.write_text("第一行\n第二行\n", encoding="utf-8")
    assert read_lines(str(path)) == ["第一行", "第二行"]
