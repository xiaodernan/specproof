"""Reading a Maven-style Java source tree, keyed by posix relative path.

Three copies of this loop existed: ``retrieve_repository_context`` read
``src/main/java``, and ``run_static_checks`` read ``src/main/java`` **and**
``src/test/java`` with the same body. The walk, the OSError tolerance and the
key format are one decision, so they live here (#494).

The per-kind names are kept because callers and tests patch them by name
(``monkeypatch.setattr(module, "_read_java_files", ...)``), which still works
when the name is an imported alias.
"""
from __future__ import annotations

from pathlib import Path


def _read_tree(workspace: str, kind: str) -> dict[str, str]:
    """Every ``.java`` under ``src/<kind>/java``, keyed by posix relative path.

    A missing directory is an empty result, not an error: a workspace that has
    no such tree simply has no files of that kind. An unreadable file is
    skipped for the same reason — one bad encoding must not lose the rest.
    """
    root = Path(workspace) / "src" / kind / "java"
    files: dict[str, str] = {}
    if not root.exists():
        return files
    for path in root.rglob("*.java"):
        try:
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    return files


def read_main_java_files(workspace: str) -> dict[str, str]:
    """Read ``src/main/java``, keyed by posix relative path."""
    return _read_tree(workspace, "main")


def read_test_java_files(workspace: str) -> dict[str, str]:
    """Read ``src/test/java``, keyed by posix relative path."""
    return _read_tree(workspace, "test")


__all__ = ["read_main_java_files", "read_test_java_files"]
