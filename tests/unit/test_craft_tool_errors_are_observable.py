"""#209: the craft tool gate's error surface is counted.

Every status="error" ToolResult is built by craft/tools.py::_error() — the
single construction point shared by dispatch's own gates (unknown tool /
version mismatch / invalid arguments), the handler exception funnel
(invalid arguments raised late / AST parse failure / stale context /
rejected edit / handler crash) and the read-side guards inside handlers
(missing file / missing directory / not a git repo). #209 makes _error()
count each failure by code (tool_errors_<code>_total, code lowercased).
tool_calls_total (#208) stays the honest denominator: every dispatch is
counted once at entry, so errors over calls is the failure rate — and the
two status families stay partitioned (error is never denied, denied is
never an error; the delta tables below witness both halves).

Honest boundary: external mcp.* tools are NOT visible here. Their error
dicts are built by providers/mcp_bridge.py and pass through
craft/mcp_wiring.py::handler straight into ToolResult(**...) — no _error()
call site exists on that path, so this family counts in-tree failures only
(the dashboard states the boundary; it never claims the whole product).

The drift gate at the bottom censuses ERROR_CODES against the source with
an AST walk: only Call nodes to _error can be sites (prose can neither
fake nor hide one), each call's first argument must be a literal or a
module-level CODE_* constant, and the floors come from the same walk — a
dynamic first argument lands in the failure message by location instead
of being silently skipped.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from craft.executor import Executor
from craft.schemas import ToolCall, ToolResult
from craft.tools import (
    CODE_AST_PARSE_FAILED,
    CODE_EDIT_REJECTED,
    CODE_EXECUTION_FAILED,
    CODE_FILE_NOT_FOUND,
    CODE_INVALID_ARGUMENTS,
    CODE_NOT_A_GIT_REPO,
    CODE_STALE_CONTEXT,
    CODE_UNKNOWN_TOOL,
    CODE_VERSION_MISMATCH,
    DENIAL_CODES,
    ERROR_CODES,
    ToolRegistry,
    ToolSpec,
    _fixed_cost,
)
from observability import metrics as metrics_module
from observability.metrics import render_text

_ERROR_COUNTERS = sorted(f"tool_errors_{code.lower()}_total" for code in ERROR_CODES)
_DENIAL_COUNTERS = sorted(f"tool_denials_{code.lower()}_total" for code in DENIAL_CODES)


def _registry(tmp_path: Path, **kwargs: Any) -> ToolRegistry:
    kwargs.setdefault("executor", Executor(tmp_path, mode="local"))
    return ToolRegistry(tmp_path, **kwargs)


def _call(registry: ToolRegistry, tool: str, arguments: dict[str, Any]) -> ToolResult:
    return registry.dispatch(registry.build_tool_call(tool, arguments))


def _counter(name: str) -> float:
    return metrics_module.snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {
        name: _counter(name)
        for name in ["tool_calls_total", *_ERROR_COUNTERS, *_DENIAL_COUNTERS]
    }


def _assert_one_dispatch(
    before: dict[str, float], word: str | None, *, denial_word: str | None = None
) -> None:
    """Exactly one dispatch happened: calls +1, the named error word (or
    none) moved by exactly 1, and the whole denial family stayed put (or
    moved by exactly one when denial_word is set). The table spans both
    families on purpose — the partition witness: any single dispatch ticks
    exactly one family, never both."""
    deltas = {name: _counter(name) - start for name, start in before.items()}
    assert deltas["tool_calls_total"] == 1.0, deltas
    wanted = f"tool_errors_{word}_total" if word is not None else None
    for name in _ERROR_COUNTERS:
        assert deltas[name] == (1.0 if name == wanted else 0.0), (name, deltas)
    wanted_denial = (
        f"tool_denials_{denial_word}_total" if denial_word is not None else None
    )
    for name in _DENIAL_COUNTERS:
        assert deltas[name] == (1.0 if name == wanted_denial else 0.0), (name, deltas)


# -- ok and denied dispatches never touch the error family ---------------------


def test_ok_and_denied_calls_do_not_touch_the_error_family(tmp_path: Path) -> None:
    """tool_calls_total counts every dispatch, but the error family counts
    only status="error": an ok call and a refused call each move calls by
    exactly 1 and the error family by 0. The refusal ticks its own denial
    word (witnessed here) — statuses partition, they do not stack."""
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = _registry(tmp_path)

    before = _before()
    ok = _call(registry, "read_file", {"path": "f.txt"})
    assert ok.status == "ok"
    _assert_one_dispatch(before, None)

    before = _before()
    denied = _call(registry, "run_test", {"command": ["rm", "-rf", "/"]})
    assert denied.status == "denied"
    _assert_one_dispatch(before, None, denial_word="command_not_allowed")


# -- one case per error word ----------------------------------------------------


def test_unknown_tool_counts_unknown_tool(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = _before()
    result = registry.dispatch(
        ToolCall(tool="definitely_not_a_tool", version=1, call_id="c1")
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_UNKNOWN_TOOL}]")
    _assert_one_dispatch(before, "unknown_tool")


def test_version_mismatch_counts_version_mismatch(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = _registry(tmp_path)
    before = _before()
    result = registry.dispatch(
        ToolCall(
            tool="read_file",
            version=999,
            call_id="c1",
            arguments={"path": "f.txt"},
        )
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_VERSION_MISMATCH}]")
    # The word lowercases the CODE VALUE (TOOL_VERSION_MISMATCH), not the
    # constant's short name — the family name carries the full code.
    _assert_one_dispatch(before, "tool_version_mismatch")


def test_validation_gate_counts_invalid_arguments(tmp_path: Path) -> None:
    """dispatch's own validation gate (missing required param) — the first
    of the two INVALID_ARGUMENTS sites; the tool never executes."""
    registry = _registry(tmp_path)
    before = _before()
    result = _call(registry, "read_file", {})
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    _assert_one_dispatch(before, "invalid_arguments")


def test_late_param_error_counts_invalid_arguments(tmp_path: Path) -> None:
    """A handler-raised ToolParamError (unknown ast_edit op) — the second
    INVALID_ARGUMENTS site, reached after the handler started; both sites
    must ride the same word."""
    (tmp_path / "f.py").write_text("a = 1\n", encoding="utf-8")
    registry = _registry(tmp_path)
    before = _before()
    result = _call(
        registry, "ast_edit", {"path": "f.py", "op": "bogus", "names": ["a", "b"]}
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    _assert_one_dispatch(before, "invalid_arguments")


def test_missing_file_counts_file_not_found(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = _before()
    result = _call(registry, "read_file", {"path": "gone.txt"})
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_FILE_NOT_FOUND}]")
    _assert_one_dispatch(before, "file_not_found")


def test_not_a_git_repo_counts_not_a_git_repo(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = _before()
    result = _call(registry, "git_status", {})
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_NOT_A_GIT_REPO}]")
    _assert_one_dispatch(before, "not_a_git_repo")


def test_stale_digest_counts_stale_context(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hello\n", encoding="utf-8")
    registry = _registry(tmp_path)
    before = _before()
    result = _call(
        registry,
        "apply_patch",
        {"path": "f.txt", "old": "hello", "new": "bye", "expected_digest": "0" * 64},
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_STALE_CONTEXT}]")
    _assert_one_dispatch(before, "stale_context")

    # The same edit without the stale digest applies — calls still counted,
    # no error word: the counter says "failed", not "attempted".
    before = _before()
    ok = _call(
        registry, "apply_patch", {"path": "f.txt", "old": "hello", "new": "bye"}
    )
    assert ok.status == "ok"
    _assert_one_dispatch(before, None)


def test_unmatched_old_counts_edit_rejected(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hello\n", encoding="utf-8")
    registry = _registry(tmp_path)
    before = _before()
    result = _call(
        registry, "apply_patch", {"path": "f.txt", "old": "NO_SUCH", "new": "x"}
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_EDIT_REJECTED}]")
    _assert_one_dispatch(before, "edit_rejected")


def test_unparsable_source_counts_ast_parse_failed(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    registry = _registry(tmp_path)
    before = _before()
    result = _call(
        registry,
        "ast_edit",
        {"path": "broken.py", "op": "rename_symbol", "names": ["a", "b"]},
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_AST_PARSE_FAILED}]")
    _assert_one_dispatch(before, "ast_parse_failed")


def test_handler_crash_counts_execution_failed(tmp_path: Path) -> None:
    """The catch-all funnel: a handler raising an unexpected exception
    reports EXECUTION_FAILED — the crash is visible as a word instead of
    escaping the gate."""
    registry = _registry(tmp_path)

    def handler(_args: dict[str, Any]) -> ToolResult:
        raise RuntimeError("boom")

    registry.register(
        ToolSpec("boom_tool", 1, "readonly", (), handler, _fixed_cost(1, 1))
    )
    before = _before()
    result = _call(registry, "boom_tool", {})
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_EXECUTION_FAILED}]")
    _assert_one_dispatch(before, "execution_failed")


# -- exposition -----------------------------------------------------------------


def test_render_text_exposes_the_error_family(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = _counter("tool_errors_file_not_found_total")
    result = _call(registry, "read_file", {"path": "gone.txt"})
    assert result.status == "error"
    after = _counter("tool_errors_file_not_found_total")
    assert after == before + 1.0

    text = render_text()
    assert "# TYPE specproof_tool_calls_total counter" in text
    name = "specproof_tool_errors_file_not_found_total"
    assert f"# TYPE {name} counter" in text
    value_line = re.search(rf"^{re.escape(name)} (\d+)$", text, re.M)
    assert value_line is not None, f"no value line for {name}"
    assert int(value_line.group(1)) == int(after)


# -- drift gate: vocabulary vs. the source census --------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _error_sites() -> tuple[set[str], int, list[str]]:
    """AST census of every `_error(...)` call in craft/**/*.py.

    Call nodes only — a mention in a docstring or comment can neither fake
    a site nor hide one. Returns (codes, site_count, dynamic_sites): each
    call's first argument either resolves through the module (a CODE_*
    constant) or is a string literal; anything else (f-string,
    concatenation, variable, keyword form) lands in dynamic_sites by
    location instead of being silently skipped."""
    import craft.tools as tools_module

    codes: set[str] = set()
    sites = 0
    dynamic: list[str] = []
    for path in sorted((_REPO_ROOT / "craft").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "_error":
                continue
            sites += 1
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                codes.add(first.value)
            elif isinstance(first, ast.Name):
                value = getattr(tools_module, first.id, None)
                if isinstance(value, str):
                    codes.add(value)
                else:
                    dynamic.append(
                        f"{path.relative_to(_REPO_ROOT).as_posix()}:{node.lineno} "
                        f"({first.id} unresolved)"
                    )
            else:
                dynamic.append(
                    f"{path.relative_to(_REPO_ROOT).as_posix()}:{node.lineno} "
                    "(non-literal first argument)"
                )
    return codes, sites, dynamic


def test_error_vocabulary_matches_the_source_census() -> None:
    """ERROR_CODES must equal the codes _error() can actually be called
    with: the AST census resolves every call's first argument (constant or
    literal) and unions them. Floors come from the same walk, so "0 found"
    cannot pass as agreement, and a dynamic first argument is named by
    location — the census cannot be silenced by rewriting a site."""
    codes, sites, dynamic = _error_sites()
    assert sites >= 10, f"_error call-site scan read only {sites} sites"
    assert not dynamic, (
        "every _error() call must pass a literal or a CODE_* constant so "
        f"the census can read it; dynamic first arguments at: {dynamic}"
    )
    assert codes == set(ERROR_CODES), (
        "error vocabulary drifted from the source census: "
        f"source-only={sorted(codes - set(ERROR_CODES))} "
        f"vocabulary-only={sorted(set(ERROR_CODES) - codes)} — an error "
        "code must ride ERROR_CODES to be counted"
    )


def test_error_and_denial_codes_are_disjoint() -> None:
    """A code riding both closed sets would put one failure into two
    families: errors and refusals share the tool_calls_total denominator
    and must partition the non-ok surface, so the vocabularies cannot
    overlap."""
    overlap = set(ERROR_CODES) & set(DENIAL_CODES)
    assert not overlap, f"codes ride both families: {sorted(overlap)}"


def test_lowercased_words_are_unique() -> None:
    """The family name is built from code.lower(); two codes collapsing
    onto one name would merge two failure reasons into one series."""
    lowered = [code.lower() for code in ERROR_CODES]
    assert len(set(lowered)) == len(lowered), sorted(lowered)
