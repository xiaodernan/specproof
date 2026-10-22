"""#208: the craft tool gate's refusal surface is counted.

Every status="denied" ToolResult is built by craft/tools.py::_denied() — the
single construction point shared by the approval gate, the workspace path
containment, the owned_paths range check, the command whitelist and the
pinned-plane toolchain refusal. #208 makes _denied() count each refusal by
code (tool_denials_<code>_total, code lowercased) and dispatch() count every
call (tool_calls_total) as the honest refusal-rate denominator.

The drift gate at the bottom censuses the source against DENIAL_CODES: a
denial site using a code outside the closed set (or a stale word in the set)
fails the census, so the vocabulary cannot drift from the sites that emit it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from craft.executor import Executor
from craft.schemas import Approval, ToolCall, ToolResult
from craft.tools import (
    CODE_APPROVAL_REQUIRED,
    CODE_COMMAND_NOT_ALLOWED,
    CODE_FILE_NOT_FOUND,
    CODE_PATH_ESCAPE,
    CODE_PATH_OUT_OF_RANGE,
    CODE_PLANE_TOOLCHAIN_MISSING,
    CODE_UNKNOWN_TOOL,
    DENIAL_CODES,
    ToolRegistry,
    ToolSpec,
    _fixed_cost,
)
from observability import metrics as metrics_module
from observability.metrics import render_text

_COUNTERS = sorted(f"tool_denials_{code.lower()}_total" for code in DENIAL_CODES)


def _registry(tmp_path: Path, **kwargs: Any) -> ToolRegistry:
    kwargs.setdefault("executor", Executor(tmp_path, mode="local"))
    return ToolRegistry(tmp_path, **kwargs)


def _call(registry: ToolRegistry, tool: str, arguments: dict[str, Any]) -> ToolResult:
    return registry.dispatch(registry.build_tool_call(tool, arguments))


def _counter(name: str) -> float:
    return metrics_module.snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in ["tool_calls_total", *_COUNTERS]}


def _assert_one_dispatch(before: dict[str, float], word: str | None) -> None:
    """Exactly one dispatch happened: calls +1, and the named denial word (or
    none, when word is None) moved by exactly 1 — every other word stays put."""
    deltas = {name: _counter(name) - start for name, start in before.items()}
    assert deltas["tool_calls_total"] == 1.0, deltas
    wanted = f"tool_denials_{word}_total" if word is not None else None
    for name in _COUNTERS:
        expected = 1.0 if name == wanted else 0.0
        assert deltas[name] == expected, (name, deltas)


# -- tool_calls_total: the honest denominator ----------------------------------


def test_ok_and_error_calls_count_only_calls(tmp_path: Path) -> None:
    """ok / error(status) dispatches count calls but no denial word: denied is
    a status of its own — error results (missing file, unknown tool) are not
    refusals and must not pollute the refusal family."""
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = _registry(tmp_path)

    before = _before()
    ok = _call(registry, "read_file", {"path": "f.txt"})
    assert ok.status == "ok"
    _assert_one_dispatch(before, None)

    before = _before()
    missing = _call(registry, "read_file", {"path": "gone.txt"})
    assert missing.status == "error"
    assert missing.summary.startswith(f"[{CODE_FILE_NOT_FOUND}]")
    _assert_one_dispatch(before, None)

    before = _before()
    unknown = registry.dispatch(
        ToolCall(tool="definitely_not_a_tool", version=1, call_id="c1")
    )
    assert unknown.status == "error"
    assert unknown.summary.startswith(f"[{CODE_UNKNOWN_TOOL}]")
    _assert_one_dispatch(before, None)


# -- one case per denial word ---------------------------------------------------


def test_approval_gate_counts_approval_required(tmp_path: Path) -> None:
    registry = _registry(
        tmp_path, approval_policy=lambda tool, _args: tool == "run_test"
    )
    before = _before()
    denied = _call(registry, "run_test", {"command": [sys.executable, "-c", "pass"]})
    assert denied.status == "denied"
    assert denied.summary.startswith(f"[{CODE_APPROVAL_REQUIRED}]")
    _assert_one_dispatch(before, "approval_required")

    # After the grant the same call passes the gate — calls still counted,
    # no denial word: the counter says "refused", not "attempted".
    registry.grant(Approval(action="run_test", state="approved"))
    before = _before()
    allowed = _call(registry, "run_test", {"command": [sys.executable, "-c", "pass"]})
    assert allowed.status == "ok"
    _assert_one_dispatch(before, None)


def test_path_escape_counts_path_escape(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    for arguments in (
        {"path": "../evil.txt", "old": "a", "new": "b"},
        {"path": str(tmp_path / "abs.txt"), "old": "a", "new": "b"},
    ):
        before = _before()
        result = _call(registry, "apply_patch", arguments)
        assert result.status == "denied", arguments
        assert result.summary.startswith(f"[{CODE_PATH_ESCAPE}]"), arguments
        _assert_one_dispatch(before, "path_escape")


def test_owned_paths_range_counts_path_out_of_range(tmp_path: Path) -> None:
    registry = _registry(tmp_path, owned_paths=["src/**"])
    before = _before()
    denied = _call(registry, "create_file", {"path": "other.txt", "content": "x\n"})
    assert denied.status == "denied"
    assert denied.summary.startswith(f"[{CODE_PATH_OUT_OF_RANGE}]")
    _assert_one_dispatch(before, "path_out_of_range")

    before = _before()
    allowed = _call(registry, "create_file", {"path": "src/a.txt", "content": "x\n"})
    assert allowed.status == "ok"
    _assert_one_dispatch(before, None)


def test_command_whitelist_counts_command_not_allowed(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = _before()
    result = _call(registry, "run_test", {"command": ["rm", "-rf", "/"]})
    assert result.status == "denied"
    assert result.summary.startswith(f"[{CODE_COMMAND_NOT_ALLOWED}]")
    _assert_one_dispatch(before, "command_not_allowed")


def test_pinned_plane_toolchain_counts_plane_toolchain_missing(tmp_path: Path) -> None:
    """cargo is whitelisted but has no container image: with the execution
    plane pinned to docker the executor refuses before any sandbox call.

    The example used to be ``gradle``; #366 gave gradle its own image
    (GRADLE_PROFILE), so a gradle command is routable now and the refusal
    it used to name is no longer reachable. ``cargo`` is still whitelisted
    and still has no image ⇒ it is the stem that exercises the refusal
    today. The refusal itself is unchanged: a whitelisted stem with no
    container image is refused on an isolated plane, not run in the wrong
    image."""
    registry = ToolRegistry(tmp_path, executor=Executor(tmp_path, mode="docker"))
    before = _before()
    result = _call(registry, "run_test", {"command": ["cargo", "test"]})
    assert result.status == "denied"
    assert result.summary.startswith(f"[{CODE_PLANE_TOOLCHAIN_MISSING}]")
    _assert_one_dispatch(before, "plane_toolchain_missing")


def test_dispatch_level_whitelist_catch_is_counted(tmp_path: Path) -> None:
    """The dispatch-level `except CommandNotAllowedError` branch is shadowed
    today by _run_command's own pre-check; witness it with a synthetic tool
    whose handler reaches Executor.run directly, so the branch still count
    its refusal instead of regressing silently."""
    registry = _registry(tmp_path)

    def handler(_args: dict[str, Any]) -> ToolResult:
        registry.executor.run(["rm", "-rf", "/"])
        raise AssertionError("unreachable: Executor.run refuses rm first")

    registry.register(
        ToolSpec("legacy_shell", 1, "controlled_exec", (), handler, _fixed_cost(1, 1))
    )
    before = _before()
    result = _call(registry, "legacy_shell", {})
    assert result.status == "denied"
    assert result.summary.startswith(f"[{CODE_COMMAND_NOT_ALLOWED}]")
    _assert_one_dispatch(before, "command_not_allowed")


# -- exposition -----------------------------------------------------------------


def test_render_text_exposes_the_refusal_family(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = _counter("tool_denials_command_not_allowed_total")
    result = _call(registry, "run_test", {"command": ["rm", "-rf", "/"]})
    assert result.status == "denied"
    after = _counter("tool_denials_command_not_allowed_total")
    assert after == before + 1.0

    text = render_text()
    assert "# TYPE specproof_tool_calls_total counter" in text
    name = "specproof_tool_denials_command_not_allowed_total"
    assert f"# TYPE {name} counter" in text
    value_line = re.search(rf"^{re.escape(name)} (\d+)$", text, re.M)
    assert value_line is not None, f"no value line for {name}"
    assert int(value_line.group(1)) == int(after)


# -- drift gate: vocabulary vs. the source census --------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONST = re.compile(r"^(CODE_[A-Z0-9_]+)\s*=\s*\"([A-Z_]+)\"", re.M)
_DENIED_SITE = re.compile(
    r"(?<!def )_denied\(\s*(?:\"([A-Z_]+)\"|(CODE_[A-Z0-9_]+))"
)
_TOOLPATH_RAISE = re.compile(
    r"raise ToolPathError\(\s*(?:\"([A-Z_]+)\"|(CODE_[A-Z0-9_]+))"
)


def test_denial_vocabulary_matches_the_source_census() -> None:
    """DENIAL_CODES must equal the codes the source can actually deny with:
    the literal/constant first arguments of every _denied() call site, plus
    the ToolPathError raise sites (their codes ride through
    _denied(exc.code, ...) into the family). Floors come from the same scan,
    so "0 found" cannot pass as agreement."""
    tools_text = (_REPO_ROOT / "craft" / "tools.py").read_text(encoding="utf-8")
    constants = dict(_CONST.findall(tools_text))
    assert len(constants) >= 14, (
        f"CODE_* constant table shrank or the scan broke: {sorted(constants)}"
    )

    sites: set[str] = set()
    denied_calls = 0
    toolpath_raises = 0
    for path in sorted((_REPO_ROOT / "craft").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for literal, const in _DENIED_SITE.findall(text):
            denied_calls += 1
            sites.add(literal or constants[const])
        for literal, const in _TOOLPATH_RAISE.findall(text):
            toolpath_raises += 1
            sites.add(literal or constants[const])
    assert denied_calls >= 4, f"_denied site scan read only {denied_calls} sites"
    assert toolpath_raises >= 3, (
        f"ToolPathError raise scan read only {toolpath_raises} sites"
    )

    assert sites == set(DENIAL_CODES), (
        "denial vocabulary drifted from the source census: "
        f"source-only={sorted(sites - set(DENIAL_CODES))} "
        f"vocabulary-only={sorted(set(DENIAL_CODES) - sites)} — a denial "
        "code must ride DENIAL_CODES to be counted"
    )


def test_lowercased_words_are_unique() -> None:
    """The family name is built from code.lower(); two codes collapsing onto
    one name would merge two refusal reasons into one series."""
    lowered = [code.lower() for code in DENIAL_CODES]
    assert len(set(lowered)) == len(lowered), sorted(lowered)
