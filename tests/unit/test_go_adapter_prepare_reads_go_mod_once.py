"""`GoAdapter.prepare` must survive a go.mod it cannot read — and say so.

Before #457 the method read `go.mod` **twice**: the first read sat inside a
``try/except Exception`` and the second did not. So a project whose go.mod was
present but unreadable (permissions, a directory of that name, bytes that are
not UTF-8) either fell back silently on the first read or raised on the second,
depending on which line got there first.

The fix is one read plus a recorded fact. The subtle half is the recording: a
go.mod that exists but cannot be read used to produce a profile that says
"Go 1.23" — indistinguishable from a project that genuinely declares 1.23. That
is the "skipped is not passed" failure this repo fences against elsewhere, so
``extra["go_mod_readable"]`` now carries the difference.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from craft.adapters.go_adapter import GoAdapter, _read_text_or_none
from craft.adapters.node_adapter import NodeAdapter

_DEFAULT_VERSION = "1.23"


def test_an_absent_go_mod_falls_back_to_the_default(tmp_path: Path) -> None:
    """No go.mod is a normal fact, not an error."""
    profile = GoAdapter.prepare(tmp_path)

    assert profile.language_version == _DEFAULT_VERSION
    assert profile.extra["has_go_mod"] is False
    assert profile.extra["go_mod_readable"] is False


def test_a_readable_go_mod_yields_its_declared_version(tmp_path: Path) -> None:
    """The happy path: the version comes out of the file."""
    (tmp_path / "go.mod").write_text("module example\ngo 1.21\n", encoding="utf-8")

    profile = GoAdapter.prepare(tmp_path)

    assert profile.language_version == "1.21"
    assert profile.extra["has_go_mod"] is True
    assert profile.extra["go_mod_readable"] is True


def test_a_go_mod_that_is_a_directory_does_not_raise(tmp_path: Path) -> None:
    """`exists()` is true, reading is impossible — the second-read crash.

    A directory named `go.mod` is the portable way to build "present but
    unreadable": on Windows `open()` raises `PermissionError`, elsewhere
    `IsADirectoryError`, and both are `OSError`.
    """
    (tmp_path / "go.mod").mkdir()

    profile = GoAdapter.prepare(tmp_path)

    assert profile.language_version == _DEFAULT_VERSION
    assert profile.extra["has_go_mod"] is True
    assert profile.extra["go_mod_readable"] is False


def test_a_go_mod_that_is_not_utf8_does_not_raise(tmp_path: Path) -> None:
    """A decode failure is "cannot read as text", not a reason to abort."""
    (tmp_path / "go.mod").write_bytes(b"\xff\xfe module example\ngo 1.21\n")

    profile = GoAdapter.prepare(tmp_path)

    assert profile.language_version == _DEFAULT_VERSION
    assert profile.extra["go_mod_readable"] is False


def test_cgo_detection_uses_the_same_single_read(tmp_path: Path) -> None:
    """The CGO flag must come from the same text, not a second read."""
    (tmp_path / "go.mod").write_text(
        "module example\ngo 1.21\n//go:cgo_enable\n", encoding="utf-8"
    )

    profile = GoAdapter.prepare(tmp_path)

    assert profile.extra["cgo_enabled"] is True
    assert profile.language_version == "1.21"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"module example\n", "module example\n"),
        (b"\xff\xfe", None),
        (b"", ""),
    ],
)
def test_read_text_or_none_distinguishes_empty_from_unreadable(
    tmp_path: Path, content: bytes, expected: str | None
) -> None:
    """Empty file → `""`; undecodable → `None`; they are different facts."""
    target = tmp_path / "f.txt"
    target.write_bytes(content)

    assert _read_text_or_none(target) == expected


def test_read_text_or_none_returns_none_for_a_missing_path(tmp_path: Path) -> None:
    assert _read_text_or_none(tmp_path / "nope.txt") is None


def test_a_non_utf8_package_json_is_not_a_node_project(tmp_path: Path) -> None:
    """Same gap on the Node side: `detect` must not raise on undecodable bytes.

    #457 narrowed the `except (json.JSONDecodeError, Exception)` (which was just
    `except Exception`) to the three shapes that mean "not a Node project". An
    undecodable package.json is one of them.
    """
    (tmp_path / "package.json").write_bytes(b"\xff\xfe{}")

    assert NodeAdapter.detect(tmp_path) is False
