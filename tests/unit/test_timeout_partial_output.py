"""#126: a workload killed by the timeout must keep its output on BOTH planes.

Threat being closed: the sandbox keeps partial output when a command is
killed on timeout, but it read that output as "only `str` is usable".
`subprocess.run(text=True)` translates the pipes on the normal return path,
while the POSIX timeout path re-raises with the raw accumulated BYTES in
`exc.stdout` (Windows re-runs `communicate()` and gets `str`). Measured in a
Linux container on Python 3.12.14: `exc.stdout` type was `bytes`, so the
runner returned `truncated=False` with an empty stdout — a timed-out build
looked like a build that printed nothing.

These cases simulate the POSIX-shaped exception at the seam the failure came
from (the exception object the runner reads), so they are red on the old code
on Windows too, and green on Linux only once the read is fixed. The last case
is a census: the same one-line pattern existed in three places, and a gate
that only covers the two it happens to test is what let the third survive.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

import sandbox.runner as runner
from sandbox.runner import run_sandboxed

REPO_ROOT = Path(__file__).resolve().parents[2]

# Retention budget used by the flood case, mirrored into the assertions.
HEAD = 1000
TAIL = 2000


def _fake_run(stdout: object, stderr: object) -> object:
    """A `subprocess.run` stand-in that raises the given timeout payload.

    Records the argv it was called with, because a witness that never proves
    WHICH call it intercepted is indistinguishable from a no-op: an earlier
    helper subprocess in the same flow would otherwise produce a green run
    that measured the wrong thing.
    """
    calls: list[list[str]] = []

    def _run(argv: list[str], *args: object, **kwargs: object) -> object:
        calls.append(list(argv))
        exc = subprocess.TimeoutExpired(cmd=list(argv), timeout=3)
        exc.stdout = stdout  # type: ignore[attr-defined]
        exc.stderr = stderr  # type: ignore[attr-defined]
        raise exc

    _run.calls = calls  # type: ignore[attr-defined]
    return _run


def _fired_on(fake: object, fragment: str) -> bool:
    return any(fragment in " ".join(argv) for argv in fake.calls)  # type: ignore[attr-defined]


def test_a_posix_timeout_exception_carries_bytes_as_partial_output() -> None:
    """The documented CPython asymmetry this whole file rests on.

    Pinned here so the other cases cannot be dismissed as a fabricated
    payload: a real killed child on any OS gives us bytes or str, and the
    runner must handle whichever it is.
    """
    assert runner.timed_out_partial(b"PARTIAL") == "PARTIAL"
    assert runner.timed_out_partial("PARTIAL") == "PARTIAL"
    assert runner.timed_out_partial(None) == ""


def test_undecodable_bytes_become_replacement_text_not_a_crash() -> None:
    assert runner.timed_out_partial(b"\xff\xfe tail").startswith("\ufffd\ufffd")
    assert "tail" in runner.timed_out_partial(b"\xff tail")


def test_local_mode_keeps_a_bytes_shaped_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red on the old runner: the kill's evidence was dropped as 'not a str'."""
    fake = _fake_run(b"BUILD-LOG-LINE-1\nBUILD-LOG-LINE-2", b"boom")
    monkeypatch.setattr(runner.subprocess, "run", fake)
    result = run_sandboxed(
        ["python", "-c", "pass"], str(tmp_path), timeout=3, mode="local"
    )
    assert _fired_on(fake, "pass"), "the timeout simulation never fired on the workload"
    assert result.exit_code == -1
    assert "timed out" in result.error
    assert result.stdout == "BUILD-LOG-LINE-1\nBUILD-LOG-LINE-2"
    assert result.stderr == "boom"


def test_docker_mode_keeps_a_bytes_shaped_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production default mode lost the same evidence."""
    fake = _fake_run(b"mvn: tests running...\n", b"")
    monkeypatch.setattr(runner.subprocess, "run", fake)
    monkeypatch.setattr(runner, "_image_ready", lambda _image: True)
    monkeypatch.setattr(runner, "_ensure_writable_target", lambda _ws: "")
    result = run_sandboxed(["mvn", "-o", "test"], str(tmp_path), timeout=3, mode="docker")
    assert _fired_on(fake, "mvn"), "the timeout simulation never fired on the workload"
    assert result.mode == "docker"
    assert result.stdout == "mvn: tests running...\n"


def test_a_bytes_shaped_flood_is_still_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retention applies to the decoded partial stream, not only to `str`."""
    monkeypatch.setenv("SPECPROOF_SANDBOX_OUTPUT_HEAD", str(HEAD))
    monkeypatch.setenv("SPECPROOF_SANDBOX_OUTPUT_TAIL", str(TAIL))
    flood = b"HEAD" + b"F" * 50_000 + b"TAIL"
    fake = _fake_run(flood, b"")
    monkeypatch.setattr(runner.subprocess, "run", fake)
    result = run_sandboxed(
        ["python", "-u", "-c", "pass"], str(tmp_path), timeout=3, mode="local"
    )
    assert _fired_on(fake, "pass"), "the timeout simulation never fired on the workload"
    assert result.truncated is True
    assert result.truncated_chars == 50_000 + 8 - HEAD - TAIL
    assert result.stdout.startswith("HEAD")
    assert result.stdout.endswith("TAIL")
    assert "chars omitted" in result.stdout


def test_cjk_partial_output_survives_the_kill_as_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The runner decodes the killed child's bytes as UTF-8, not by locale."""
    fake = _fake_run("编译失败：找不到符号".encode(), b"")
    monkeypatch.setattr(runner.subprocess, "run", fake)
    result = run_sandboxed(
        ["python", "-c", "pass"], str(tmp_path), timeout=3, mode="local"
    )
    assert _fired_on(fake, "pass"), "the timeout simulation never fired on the workload"
    assert result.stdout == "编译失败：找不到符号"


def test_a_kill_before_any_output_stays_empty_not_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_run(None, None)
    monkeypatch.setattr(runner.subprocess, "run", fake)
    result = run_sandboxed(
        ["python", "-c", "pass"], str(tmp_path), timeout=3, mode="local"
    )
    assert _fired_on(fake, "pass"), "the timeout simulation never fired on the workload"
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.truncated is False


# -- census ------------------------------------------------------------------

_SKIP_DIRS = {"node_modules", "__pycache__", ".venv", ".venv312", ".git", ".pytest_cache",
              "dist", "build", "bench"}


def _product_python_files() -> list[Path]:
    """Every product/harness .py file, pruning the walk so it stays cheap."""
    files: list[Path] = []
    for root, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        rel = Path(root).relative_to(REPO_ROOT)
        if "tests" in rel.parts or "bench" in rel.parts:
            continue
        for name in filenames:
            if name.endswith(".py"):
                files.append(Path(root) / name)
    return sorted(files)


def _timeout_blocks() -> list[tuple[Path, int, str]]:
    """(file, line, source) for every `except TimeoutExpired` block in the product."""
    blocks: list[tuple[Path, int, str]] = []
    for path in _product_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or not _names_timeout(node.type):
                continue
            body_src = ast.get_source_segment(text, node) or ""
            blocks.append((path, node.lineno, body_src))
    return blocks


def _timeout_read_sites() -> list[tuple[Path, int]]:
    """Blocks that keep partial output but do not decode it."""
    return [
        (path, lineno)
        for path, lineno, body in _timeout_blocks()
        if (".stdout" in body or ".stderr" in body) and "timed_out_partial" not in body
    ]


def _names_timeout(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr == "TimeoutExpired"
    if isinstance(node, ast.Tuple):
        return any(_names_timeout(el) for el in node.elts)
    return False


def test_no_partial_output_reader_asks_the_running_os_for_a_type() -> None:
    """Every timeout handler that keeps partial output must decode it.

    The census is the point: the same `isinstance(exc.stdout, str)` line
    existed in the sandbox twice and in the SWE-bench harness once, and only
    the sandbox pair was reachable from a failing test.
    """
    sites = _timeout_read_sites()
    assert sites == [], [f"{p.relative_to(REPO_ROOT)}:{ln}" for p, ln in sites]


def test_the_census_actually_reads_the_files_it_claims_to_guard() -> None:
    """Floor for the case above, so 'no violations' cannot mean 'read nothing'."""
    names = {p.relative_to(REPO_ROOT).as_posix() for p in _product_python_files()}
    assert "sandbox/runner.py" in names
    assert "scripts/bench_swebench.py" in names
    readers = [(p, ln) for p, ln, body in _timeout_blocks()
               if ".stdout" in body or ".stderr" in body]
    assert len(readers) >= 3, (
        f"expected at least the three known partial-output readers, found "
        f"{[f'{p.relative_to(REPO_ROOT)}:{ln}' for p, ln in readers]}"
    )
