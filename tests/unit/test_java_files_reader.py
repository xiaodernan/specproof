"""#494 — the shared Java-tree reader, pinned directly.

Three copies of this walk existed (``retrieve_repository_context`` read
``src/main/java``; ``run_static_checks`` read both ``src/main`` and
``src/test``). It is now one implementation, so its contract gets direct
tests: the key format, the two kinds, and the tolerance that keeps one bad
entry from losing the rest.
"""
from __future__ import annotations

from pathlib import Path

from agent.nodes._java_files import read_main_java_files, read_test_java_files


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_missing_tree_is_an_empty_result(tmp_path: Path) -> None:
    assert read_main_java_files(str(tmp_path)) == {}
    assert read_test_java_files(str(tmp_path)) == {}


def test_files_are_keyed_by_posix_relative_path(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/java/com/acme/Deep.java", "class Deep {}")
    _write(tmp_path, "src/main/java/Top.java", "class Top {}")

    files = read_main_java_files(str(tmp_path))
    # posix separators, relative to src/main/java — not absolute, not Windows-style.
    assert set(files) == {"com/acme/Deep.java", "Top.java"}
    assert files["Top.java"] == "class Top {}"


def test_main_and_test_trees_do_not_leak_into_each_other(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/java/Main.java", "main")
    _write(tmp_path, "src/test/java/MainTest.java", "test")

    assert set(read_main_java_files(str(tmp_path))) == {"Main.java"}
    assert set(read_test_java_files(str(tmp_path))) == {"MainTest.java"}


def test_only_java_files_are_read(tmp_path: Path) -> None:
    _write(tmp_path, "src/main/java/A.java", "a")
    _write(tmp_path, "src/main/java/notes.txt", "not java")

    assert set(read_main_java_files(str(tmp_path))) == {"A.java"}


def test_one_unreadable_entry_does_not_lose_the_rest(tmp_path: Path) -> None:
    # A directory named "*.java" makes read_text raise IsADirectoryError (an
    # OSError): the reader must skip it and still return its siblings.
    _write(tmp_path, "src/main/java/Good.java", "good")
    (tmp_path / "src/main/java/Broken.java").mkdir(parents=True)

    files = read_main_java_files(str(tmp_path))
    assert set(files) == {"Good.java"}
