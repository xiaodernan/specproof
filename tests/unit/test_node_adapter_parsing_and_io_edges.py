"""Edges of the Node adapter that were silently broken until #457.

Each test here pins a defect that shipped to master, and each one fails in a way
that is invisible unless the specific shape is exercised:

1. ``os`` was used in four places (``os.walk`` / ``os.path.join``) without ever
   being imported, because a fifth call site worked around it with
   ``__import__("os")``. Any Node project with a ``build/``, ``reports/``,
   ``.nyc_output/`` or ``test-results/`` directory therefore raised ``NameError``
   while collecting evidence — i.e. on the projects that actually had reports.
2. The npm stdout pattern reported ``tests_run`` as *passed* instead of
   ``passed + failed + skipped``, so every run with a failure or a skip
   under-counted. The vitest pattern right below it had always been correct.
3. ``subprocess.run`` output was mutated in place on the ``CompletedProcess``
   object, and ``ExecutionResult.stdout`` (declared ``str``) received
   ``bytes | str`` depending on the branch.

The adapter's own module docstring says the goal is "统一的 RuntimeProfile、
ExecutionResult、EvidenceFragment" — these are the cases where it was not.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from craft.adapters.node_adapter import NodeAdapter, _as_text
from craft.adapters.protocol import ExecutionResult

_JUNIT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="suite" tests="5" failures="1" errors="1" skipped="2">
    <testcase name="a" />
    <testcase name="b" />
  </testsuite>
</testsuites>
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_junit_report_under_build_is_read_without_a_name_error(tmp_path: Path) -> None:
    """The `os` import bug: a project with `build/` used to raise NameError.

    `_parse_test_results` walks `build/`, `reports/` and `.nyc_output/` looking
    for JUnit XML. With `os` unimported, the walk itself blew up — so the
    adapter crashed exactly on projects that produced reports, and returned
    zeros on projects that did not. This asserts the walk happens.
    """
    _write(tmp_path / "build" / "junit.xml", _JUNIT_XML)

    run, passed, failed, skipped = NodeAdapter._parse_test_results(tmp_path, "", "")

    # tests=5, failures=1, errors=1, skipped=2 ⇒ passed = 5 - 2 - 2 = 1
    assert (run, passed, failed, skipped) == (5, 1, 2, 2)


def test_a_junit_report_under_test_results_is_read_without_a_name_error(
    tmp_path: Path,
) -> None:
    """Same bug, the other walk (`_collect_junit_reports` under `test-results/`)."""
    _write(tmp_path / "test-results" / "junit.xml", _JUNIT_XML)

    fragments = NodeAdapter._collect_junit_reports(
        tmp_path, ExecutionResult(exit_code=0, stdout="", stderr="", duration_ms=0)
    )

    assert [f.payload["type"] for f in fragments] == ["junit_xml"]
    assert "testsuite" in fragments[0].payload["content"]


def test_npm_stdout_counts_failures_and_skips_in_the_run_total(tmp_path: Path) -> None:
    """`tests_run` must be passed + failed + skipped, not just passed.

    The old extractor returned `int(group(1))` for the run total, so
    "3 passed, 1 failed, 2 skipped" was reported as 3 tests run instead of 6.
    """
    output = "Tests: 3 passed, 1 failed, 2 skipped"

    assert NodeAdapter._parse_stdout_results(output) == (6, 3, 1, 2)


def test_vitest_stdout_counts_failures_in_the_run_total(tmp_path: Path) -> None:
    """The vitest pattern was already correct; pin it so the two agree."""
    output = "5 tests passed, 2 failed"

    assert NodeAdapter._parse_stdout_results(output) == (7, 5, 2, 0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (b"hello", "hello"),
        ("hello", "hello"),
        (None, ""),
        (b"", ""),
    ],
)
def test_as_text_coerces_every_shape_subprocess_hands_back(
    value: bytes | str | None, expected: str
) -> None:
    """One coercion point for `bytes | str | None`.

    `subprocess.run` returns bytes or str depending on `text=`, and
    `ExecutionResult.stdout` is declared `str`; the adapter used to assign
    either one straight into the dataclass.
    """
    assert _as_text(value) == expected


def test_as_text_replaces_undecodable_bytes(tmp_path: Path) -> None:
    """A Windows console can emit bytes that are not UTF-8; that must not raise."""
    assert _as_text(b"\xff\xfe") == "\ufffd\ufffd"


def test_detect_rejects_an_unparseable_package_json(tmp_path: Path) -> None:
    """A broken `package.json` is not a Node project.

    Before #457 this branch was `except (json.JSONDecodeError, Exception)` —
    which is just `except Exception` — so every failure looked the same. It is
    now narrowed to the three shapes that mean "not a Node project", which
    keeps a genuinely broken probe visible instead of reported as "no adapter".
    """
    _write(tmp_path / "package.json", "{ this is not json")
    assert NodeAdapter.detect(tmp_path) is False


def test_detect_accepts_a_package_json_without_a_test_script(tmp_path: Path) -> None:
    """`vitest` / `node-test` goals need no npm script, so absence is not a veto."""
    _write(tmp_path / "package.json", json.dumps({"dependencies": {}}))
    assert NodeAdapter.detect(tmp_path) is True
