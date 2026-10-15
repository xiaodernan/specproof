"""The LLM counterexample path must actually run (#270).

§4.2 wants a counterexample that "really reproduces a regression". Two
independent defects kept that from even being reachable:

**A. The same coroutine, two different workspaces.**
   ``generate_counterexamples_node`` calls ``_generate_with_compile_loop``
   twice — once for the "inside a running event loop" arm and once for the
   plain ``asyncio.run`` arm — and the two calls disagreed on the first
   argument: ``head_workspace`` vs ``app_workspace``. ``_compile_test``
   resolves ``Path(workspace) / "pom.xml"``, so the ``head_workspace`` arm
   returns ``(-1, "No pom.xml found")`` whenever ``app_dir`` is set
   (``app_workspace = head_workspace / app_dir``). That reads as a compile
   failure, so a good LLM test is discarded and the run falls back to the
   demo-repo-only deterministic template — "No counterexample test produced"
   for anything else. Every other consumer in the function (``seed_head_build``,
   ``test_dir``, ``_is_demo_repo``, ``_run_generated_test``) uses
   ``app_workspace``.

**B. The branch selector crashed on the API's thread.**
   The node used ``asyncio.get_event_loop()``, which RAISES
   ``RuntimeError: There is no current event loop in thread ...`` on a thread
   with no current loop. ``api/agent_runtime.py`` starts every job with
   ``copy_context()`` + ``threading.Thread(target=context.run, ...)`` —
   copying contextvars installs no event loop — so on the API the raise fell
   into the node's bare ``except Exception`` and became
   ``source="deterministic_template"`` /
   ``"LLM generation failed: There is no current event loop ..."``. The LLM
   path never started at all.

These tests read the REAL source (AST) and call the REAL helpers, so either
regression shows up as a failure.
"""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
from pathlib import Path

import pytest

from agent.nodes.generate_counterexamples import (
    _compile_test,
    _inside_running_loop,
)

SRC = Path("agent/nodes/generate_counterexamples.py")


def _node() -> ast.FunctionDef:
    """The real generate_counterexamples_node, parsed from disk."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "generate_counterexamples_node":
            return n
    raise AssertionError("generate_counterexamples_node not found")


def _compile_calls() -> list[ast.Call]:
    return [
        n
        for n in ast.walk(_node())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_generate_with_compile_loop"
    ]


# ── A: both arms must compile the same workspace ──────────────────────────────
def test_both_compile_arms_pass_the_same_workspace() -> None:
    """AST over the real source — the two call sites must agree (#270 A)."""
    calls = _compile_calls()
    assert len(calls) == 2, f"expected 2 call sites, found {len(calls)}"

    first_args = set()
    for c in calls:
        assert c.args, "call has no positional args"
        arg = c.args[0]
        assert isinstance(arg, ast.Name), f"unexpected arg shape: {ast.dump(arg)}"
        first_args.add(arg.id)

    assert len(first_args) == 1, (
        "the two _generate_with_compile_loop arms pass different workspaces: "
        f"{sorted(first_args)} — _compile_test resolves "
        "Path(workspace)/'pom.xml', so one of them can never compile"
    )


def test_both_compile_arms_pass_app_workspace() -> None:
    """app_workspace is the one every other consumer uses (#270 A)."""
    passed = {c.args[0].id for c in _compile_calls()}
    assert passed == {"app_workspace"}, (
        f"compile arms pass {sorted(passed)}; the test file, pom.xml, "
        "seed_head_build, _is_demo_repo and _run_generated_test all live at "
        "app_workspace"
    )


def test_app_workspace_is_head_workspace_below_app_dir() -> None:
    """The documented relationship the workspace choice depends on (#270 A)."""
    assignments = [
        n
        for n in ast.walk(_node())
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app_workspace" for t in n.targets)
    ]
    assert assignments, "app_workspace is never assigned inside the node"
    expr = ast.unparse(assignments[0].value)
    assert "head_workspace" in expr and "app_dir" in expr, expr


# ── B: the branch selector must not raise on a loop-less thread ───────────────
def test_no_real_get_event_loop_call_remains() -> None:
    """AST: get_event_loop() is gone from the file (#270 B)."""
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    offenders = sorted(
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "get_event_loop"
    )
    assert offenders == [], (
        f"asyncio.get_event_loop() at line(s) {offenders} — it RAISES "
        "RuntimeError on a thread with no current loop, and the node's bare "
        "except turns that into 'LLM generation failed'"
    )


def test_node_branches_through_the_safe_helper() -> None:
    """The phase-1 branch goes through _inside_running_loop (#270 B)."""
    uses = [
        n
        for n in ast.walk(_node())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_inside_running_loop"
    ]
    assert uses, "generate_counterexamples_node does not call _inside_running_loop"


async def _ask_from_coro() -> bool:
    return _inside_running_loop()


def test_inside_running_loop_is_false_in_a_thread_without_a_loop() -> None:
    """THE API's context: copy_context() + bare thread (#270 B).

    The pre-fix expression raised here instead of answering.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(_inside_running_loop).result() is False


def test_inside_running_loop_is_true_from_a_coroutine() -> None:
    """The arm that must still be taken when a loop IS running (#270 B)."""
    assert asyncio.run(_ask_from_coro()) is True


def test_inside_running_loop_is_false_on_a_non_running_loop() -> None:
    """A loop that exists but is not running is not the running-loop arm."""

    def ask() -> bool:
        asyncio.set_event_loop(asyncio.new_event_loop())
        try:
            return _inside_running_loop()
        finally:
            asyncio.set_event_loop(None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(ask).result() is False


def test_inside_running_loop_never_raises() -> None:
    """No calling context may escape with an exception (#270 B)."""
    outcomes = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        outcomes.append(pool.submit(_inside_running_loop).result())
    outcomes.append(asyncio.run(_ask_from_coro()))
    outcomes.append(_inside_running_loop())
    assert all(isinstance(o, bool) for o in outcomes), outcomes


# ── A: why the workspace matters at all ───────────────────────────────────────
def test_compile_test_rejects_a_workspace_without_pom(tmp_path: Path) -> None:
    """_compile_test gates on Path(workspace)/'pom.xml' (#270 A).

    Passing head_workspace (the parent of app_dir) therefore guarantees
    (-1, "No pom.xml found") — a compile failure for a test that never ran.
    """
    parent = tmp_path / "head"
    app = parent / "services" / "api"
    app.mkdir(parents=True)
    (app / "pom.xml").write_text("<project/>", encoding="utf-8")

    assert not (parent / "pom.xml").exists(), "fixture: parent has no pom.xml"

    # parent == head_workspace with app_dir set: the pre-fix argument.
    assert _compile_test(str(parent), "SpecProofGeneratedTest.java") == (
        -1,
        "No pom.xml found",
    )


def test_compile_test_passes_the_pom_gate_when_pom_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The app workspace gets PAST the gate — head_workspace could not."""
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    import experiments.adapters as adapters

    class _NotImplementedError(Exception):
        pass

    def _deny(_snap: object) -> object:
        raise _NotImplementedError("past the pom gate")

    monkeypatch.setattr(adapters, "AdapterNotImplemented", _NotImplementedError)
    monkeypatch.setattr(adapters.registry, "get", _deny)

    code, stderr = _compile_test(str(tmp_path), "SpecProofGeneratedTest.java")
    assert "No pom.xml found" not in stderr, (
        "workspace has a pom.xml, so the pom gate must not be what stops us"
    )
    assert code == -1 and stderr == "past the pom gate"


def test_deterministic_fallback_is_demo_only() -> None:
    """The consequence of A/B: losing the LLM path is not recoverable.

    The template fallback is gated on com.specproof, so a non-demo repo that
    loses the LLM arm produces no counterexample at all.
    """
    from agent.nodes.generate_counterexamples import _is_demo_repo

    assert _is_demo_repo("/definitely/not/a/repo") is False

    src = SRC.read_text(encoding="utf-8")
    assert "_is_demo_repo(app_workspace)" in src, (
        "the demo-only gate moved — re-evaluate what losing the LLM path costs"
    )

