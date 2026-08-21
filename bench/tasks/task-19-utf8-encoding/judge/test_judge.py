# mypy: ignore-errors
"""Hidden judge tests for task-19: acceptance + no-regression guards."""

from svc import read_lines


def test_emoji_content(tmp_path) -> None:
    path = tmp_path / "emoji.txt"
    path.write_text("hi 🚀\nok\n", encoding="utf-8")
    assert read_lines(str(path)) == ["hi 🚀", "ok"]


def test_empty_file(tmp_path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert read_lines(str(path)) == []


def test_no_trailing_newline(tmp_path) -> None:
    path = tmp_path / "last.txt"
    path.write_text("one\ntwo", encoding="utf-8")
    assert read_lines(str(path)) == ["one", "two"]


def test_file_not_modified(tmp_path) -> None:
    path = tmp_path / "keep.txt"
    path.write_text("x\n", encoding="utf-8")
    before = path.read_bytes()
    read_lines(str(path))
    assert path.read_bytes() == before
