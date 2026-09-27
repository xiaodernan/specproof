r"""#111 - what the shipped MCP tool reads out of a child must be the child's bytes.

`mcp/tools.py::_run_cli` is how the shipped MCP server runs `specproof verify`
and parses its stdout; the server is a product entry point (`specproof mcp
serve`, docs/operations/EXPERIENCE_GUIDE.md:58) and whatever it reads is what an
MCP client is told. It asked for `text=True` without naming a codec, so the
parent decoded with the *machine's* preference while the child encoded according
to whatever `PYTHONIOENCODING` it inherited. The two ends disagreed, and the
disagreement was not a crash: it produced a plausible
string. Measured on this host (parent preference cp936) before the fix:

    PYTHONIOENCODING=None      stdout='VERDICT: PASS 中文路径 D:/面试项目/x.py'   (match)
    PYTHONIOENCODING='utf-8'   stdout='VERDICT: PASS 涓... D:/闈㈣瘯椤圭洰/x.py'  (MISMATCH)
    PYTHONIOENCODING='gbk'     stdout='VERDICT: PASS 中文路径 D:/面试项目/x.py'   (match)

The red row is the case an MCP host gets when it starts the server with
PYTHONIOENCODING=utf-8 (the value docs/operations/DRILLS.md FIX-16 records as the
house setting for CJK output - note that line cites RUNBOOK.md, which today
contains no such instruction; the correction is logged with #111). The garble is
not cosmetic, because the parser keeps whole tails: `^VERDICT:\s+(.+)$` becomes
summary["verdict"] and `^HTML Report:\s+(.+)$` becomes summary["html_report"], so
a client comparing the verdict string, or opening the report path, is handed a
confidently wrong value - from a product that installs under a CJK directory
(D:\面试项目).

Why three rows and not one: pinning only one end is a coin flip. On this host a
parent-only pin (`encoding=utf-8`, no child env) turns the None/gbk rows red, a
child-only pin turns all three red, and no pin reds the utf-8 row - so the table
catches every half-fix, which is what makes it worth running. The declaration
gates below then keep the invariant true on machines whose locale preference
already agrees with the payload.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from mcp.tools import _run_cli, parse_verify_stdout

EXPECTED_VERDICT_LINE = "VERDICT: PASS 中文路径 D:/面试项目/x.py"
EXPECTED_REPORT_LINE = "HTML Report: D:/面试项目/report.html"
EXPECTED = f"{EXPECTED_VERDICT_LINE}\n{EXPECTED_REPORT_LINE}"
EXPECTED_PARSED_VERDICT = "PASS 中文路径 D:/面试项目/x.py"
CHILD = (
    "import sys; "
    f"sys.stdout.write({EXPECTED_VERDICT_LINE!r} + chr(10) + {EXPECTED_REPORT_LINE!r}); "
    "sys.stdout.flush()"
)

REPO = Path(__file__).resolve().parents[2]
TOOLS_SOURCE = REPO / "mcp" / "tools.py"

# Packages a shipped entry point (API app, CLI, MCP server) loads at run time.
# Measured 2026-09-28 by walking the import closure of api/app.py,
# cli/specproof/main.py and mcp/server.py and keeping the repo-root packages
# that are not operator tooling: mcp was missing from PINNED_SCOPES (#92 swept
# the other lanes and never named this one), and contracts/observability are
# loaded but had never been declared.
SHIPPED_RUNTIME_LANES = ("api", "cli", "mcp", "contracts", "observability")


@pytest.mark.parametrize("child_env", [None, "utf-8", "gbk"])
def test_the_childs_environment_must_not_decide_what_the_agent_reads(
    monkeypatch: pytest.MonkeyPatch, child_env: str | None
) -> None:
    if child_env is None:
        monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    else:
        monkeypatch.setenv("PYTHONIOENCODING", child_env)
    proc = _run_cli([sys.executable, "-c", CHILD], timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == EXPECTED, (
        f"inherited PYTHONIOENCODING={child_env!r} changed what the server reads: "
        f"{proc.stdout!r} - both ends of the codec must be pinned by _run_cli"
    )
    assert "\ufffd" not in proc.stdout, (
        "the reader swallowed bytes it could not decode: " + repr(proc.stdout)
    )
    summary = parse_verify_stdout(proc.stdout)
    assert summary["verdict"] == EXPECTED_PARSED_VERDICT, (
        f"the verdict string an MCP client is asked to compare against got: "
        f"{summary['verdict']!r}"
    )
    assert summary["html_report"] == "D:/面试项目/report.html", (
        "the report path handed to the client must be openable: "
        f"{summary['html_report']!r}"
    )


def _spawn_capturing_bytes(child_env: str) -> bytes:
    """Out-of-band capture: bytes only, so this file stays outside the ratchet."""
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        capture_output=True,
        timeout=120,
        check=False,
        env={"PYTHONIOENCODING": child_env},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@pytest.mark.parametrize("child_env", ["utf-8", "gbk"])
def test_the_two_codecs_really_do_disagree_on_this_payload(child_env: str) -> None:
    """Mechanism, not superstition: one child, read both ways.

    If some future payload decodes identically under both codecs, the table
    above proves nothing and this test says so first.
    """
    raw = _spawn_capturing_bytes(child_env)
    lines = EXPECTED.splitlines()
    assert (raw.decode("utf-8", errors="replace").splitlines() == lines) is not (
        raw.decode("cp936", errors="replace").splitlines() == lines
    ), (
        f"a child emitting {child_env} reads back the same under utf-8 and cp936, "
        "so this payload cannot detect a half-pinned reader"
    )


def _run_cli_node() -> ast.FunctionDef:
    tree = ast.parse(TOOLS_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_run_cli":
            return node
    raise AssertionError("_run_cli disappeared from mcp/tools.py")


def _string_constant(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _child_env_codec(fn: ast.FunctionDef) -> str | None:
    """The codec _run_cli tells its child to emit, read from the source."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if _string_constant(key) == "PYTHONIOENCODING":
                    return _string_constant(value)
        if isinstance(node, ast.keyword) and node.arg == "PYTHONIOENCODING":
            return _string_constant(node.value)
    return None


def _run_cli_call() -> ast.Call:
    calls = [
        node
        for node in ast.walk(_run_cli_node())
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", "") in {"run", "Popen"}
        and getattr(getattr(node.func, "value", None), "id", "") == "subprocess"
    ]
    assert len(calls) == 1, f"_run_cli should hold exactly one child call, found {len(calls)}"
    return calls[0]


def test_run_cli_pins_both_ends_of_the_codec_and_they_agree() -> None:
    """Machine-independent half: on a UTF-8 host the table above cannot see a
    one-sided pin, so the declaration is read from the shipped source instead.
    """
    call = _run_cli_call()
    keywords = {k.arg: k.value for k in call.keywords if k.arg}
    assert {"capture_output", "text"} <= set(keywords), (
        "_run_cli is a capturing text call; if that changed this gate is stale"
    )
    parent = _string_constant(keywords.get("encoding"))
    assert parent is not None, (
        "subprocess.run(text=True) without encoding= decodes with the OS locale, "
        "so what the agent reads depends on the machine, not on the child"
    )
    assert "env" in keywords, (
        "_run_cli must hand the child an env it controls; inheriting PYTHONIOENCODING "
        "leaves the child's encoder up to whoever started the server"
    )
    child = _child_env_codec(_run_cli_node())
    assert child is not None, "the child must be told which codec to emit"
    assert parent == child, (
        f"the parent decodes {parent!r} while the child is told to emit {child!r}; "
        "two pinned ends only help if they name the same codec"
    )


def test_shipped_runtime_lanes_are_pinned_not_graded_as_debt() -> None:
    """#92's sweep missed mcp/, and an unpinned capture there counted as debt.

    A lane the product loads must fail outright when it decodes a child with the
    locale; the debt ceiling is only for operator tooling and tests.
    """
    from tests.unit.test_subprocess_text_encoding import PINNED_SCOPES

    for lane in SHIPPED_RUNTIME_LANES:
        assert (REPO / lane).is_dir(), f"{lane}/ is not in the repo anymore"
        assert lane in PINNED_SCOPES, (
            f"{lane}/ is loaded by a shipped entry point but is not in "
            "PINNED_SCOPES, so a locale-decoded child there would only spend "
            "debt budget instead of failing the gate"
        )
