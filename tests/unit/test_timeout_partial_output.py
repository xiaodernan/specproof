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
from collections.abc import Callable
from pathlib import Path
from typing import cast

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
    assert runner.child_output_text(b"PARTIAL") == "PARTIAL"
    assert runner.child_output_text("PARTIAL") == "PARTIAL"
    assert runner.child_output_text(None) == ""


def test_undecodable_bytes_become_replacement_text_not_a_crash() -> None:
    assert runner.child_output_text(b"\xff\xfe tail").startswith("\ufffd\ufffd")
    assert "tail" in runner.child_output_text(b"\xff tail")


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

#: The decoders the census below is willing to trust, by name.
#:
#: #126 hard-coded one spelling (`timed_out_partial`) into a substring search.
#: That broke both ways: it went red on three `craft/adapters/*` handlers that
#: *did* decode — through private `_as_text` copies, #513 — and it would have
#: gone green on a handler that merely mentioned the name in a comment. The list
#: is now a registry, and each entry is proven by
#: `test_every_registered_decoder_is_real_and_handles_all_three_shapes`.
DECODERS: set[str] = {"child_output_text"}


def _resolve_decoder(name: str) -> Callable[[object], str]:
    """Look a registered decoder up where the product keeps it."""
    decoder = getattr(runner, name, None)
    assert callable(decoder), (
        f"{name} is in DECODERS but sandbox.runner has no such function — "
        "the census would be trusting a name that does not exist"
    )
    return cast(Callable[[object], str], decoder)


#: Directories the census prunes; a walk over venvs or eval worktrees measures
#: the machine, not the repo.
_SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    ".venv",
    ".venv312",
    ".git",
    ".pytest_cache",
    ".scratch",
    "dist",
    "build",
    "bench",
}


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


def _timeout_blocks() -> list[tuple[Path, int, ast.ExceptHandler]]:
    """(file, line, handler AST) for every `except TimeoutExpired` in the product."""
    blocks: list[tuple[Path, int, ast.ExceptHandler]] = []
    for path in _product_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or not _names_timeout(node.type):
                continue
            blocks.append((path, node.lineno, node))
    return blocks


def _reads_of_the_exception(handler: ast.ExceptHandler) -> list[ast.Attribute]:
    """Every `exc.stdout` / `exc.stderr` read inside the handler body.

    Only reads of the object the handler bound count — `result.stdout` from an
    earlier call in the same block is a different object with a different shape.
    """
    if handler.name is None:
        return []
    return [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Attribute)
        and node.attr in {"stdout", "stderr"}
        and isinstance(node.value, ast.Name)
        and node.value.id == handler.name
    ]


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _wrapped_by_a_proven_decoder(read: ast.Attribute, parent: ast.AST | None) -> bool:
    """True when this read goes straight into one of the decoders this file tests."""
    if not isinstance(parent, ast.Call):
        return False
    if not any(read is arg for arg in parent.args):
        return False
    func = parent.func
    name = getattr(func, "attr", None) or getattr(func, "id", None)
    return name in DECODERS


def _timeout_read_sites() -> list[tuple[Path, int]]:
    """Reads of the killed child's output that no proven decoder covers.

    #126 matched the literal string `timed_out_partial` anywhere in the handler
    body. That is a spelling test, and it had two wrong sides: a handler could
    satisfy it by mentioning the name in a comment, and #499's queue read the
    three `craft/adapters/*` hits as raw reads when in fact each one decoded
    through a private `_as_text` copy (#513 measured this). The rule is now
    structural — the read must be an *argument* of a call to a decoder listed in
    `DECODERS`, and `DECODERS` is only as wide as the cases that prove each entry
    below.
    """
    sites: list[tuple[Path, int]] = []
    for path, _lineno, handler in _timeout_blocks():  # the read's own line is reported
        parents = _parents(handler)
        bad = [
            read
            for read in _reads_of_the_exception(handler)
            if not _wrapped_by_a_proven_decoder(read, parents.get(read))
        ]
        if bad:
            sites.append((path, bad[0].lineno))
    return sites


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
    readers = [(p, ln) for p, ln, handler in _timeout_blocks() if _reads_of_the_exception(handler)]
    assert len(readers) >= 3, (
        f"expected at least the three known partial-output readers, found "
        f"{[f'{p.relative_to(REPO_ROOT)}:{ln}' for p, ln in readers]}"
    )


@pytest.mark.parametrize("decoder_name", sorted(DECODERS))
def test_every_registered_decoder_is_real_and_handles_all_three_shapes(
    decoder_name: str,
) -> None:
    """The census trusts a name, so the name has to earn trust here.

    A gate that only checks spelling can be satisfied by a function that returns
    `""` for bytes — which is the very evidence loss the census exists to stop.
    Every entry in `DECODERS` must therefore exist in the product and coerce all
    three shapes `subprocess` hands back.
    """
    decoder = _resolve_decoder(decoder_name)
    assert decoder(b"PARTIAL") == "PARTIAL"
    assert decoder("PARTIAL") == "PARTIAL"
    assert decoder(None) == ""
    assert decoder(b"\xff\xfe tail").startswith("\ufffd\ufffd"), (
        f"{decoder_name} raises or drops bytes it cannot decode instead of "
        "replacing them — that is the locale failure the census is guarding"
    )
