"""Requirement LLM enrichment must survive a thread with no event loop (#271).

`agent/contracts/parser.py::parse_with_llm_fallback` had the same defect
class as #270, one file over:

    line 187  loop = asyncio.get_event_loop()      # RAISES on a loop-less thread
    line 203  except Exception -> result.warnings.append(
                  f"LLM requirement parse failed: {exc}")

`api/agent_runtime.py` starts every job with `copy_context()` +
`threading.Thread(target=context.run, ...)`, which copies contextvars but
installs no event loop — so on the API that raise always landed in the
handler and enrichment never started. `agent/nodes/compile_contracts.py`
had already solved this with `_running_loop()`; parser.py never got it.

**The bigger fact**: the wrapper is currently UNWIRED. `git grep` finds
`parse_with_llm_fallback` and `llm_enrich_requirements` only inside
parser.py itself — the pipeline's two real consumers
(`compile_contracts.py:621-624`, `cli/specproof/commands/contract.py:27,94`)
call `parse_requirements` directly. So this path never ran for ANY thread,
not just the API's. These tests fix the defect AND pin the unwired fact so
nobody assumes enrichment is happening.
"""

from __future__ import annotations

import ast
import asyncio
import concurrent.futures
import pathlib
import subprocess

from agent.contracts.parser import (
    _running_loop,
    parse_with_llm_fallback,
)

SRC = pathlib.Path("agent/contracts/parser.py")


def _fallback() -> ast.FunctionDef:
    tree = ast.parse(SRC.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == "parse_with_llm_fallback":
            return n
    raise AssertionError("parse_with_llm_fallback not found")


# ── the defect itself ─────────────────────────────────────────────────────────
def test_no_real_get_event_loop_call_remains() -> None:
    """AST: get_event_loop() is gone from parser.py (#271)."""
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
        "RuntimeError on a thread with no current loop, and this function's "
        "except Exception reports it as 'LLM requirement parse failed'"
    )


def test_fallback_branches_through_the_helper() -> None:
    """AST: the branch selector goes through _running_loop (#271)."""
    uses = [
        n
        for n in ast.walk(_fallback())
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_running_loop"
    ]
    assert uses, "parse_with_llm_fallback does not call _running_loop"


def test_running_loop_is_none_in_a_bare_thread() -> None:
    """THE API's context: copy_context() + bare thread (#271).

    The pre-fix expression raised here instead of answering.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(_running_loop).result() is None


def test_inside_running_loop_is_true_from_a_coroutine() -> None:
    """_running_loop() answers the loop that is live right now.

    asyncio.run() creates a loop, runs the coroutine to completion, then
    closes it. We therefore assert the boolean value _running_loop() reports
    while that loop was alive, rather than is_running() on the closed loop.
    """
    async def ask():
        return _running_loop() is not None

    assert asyncio.run(ask()) is True


def test_running_loop_never_raises() -> None:
    outcomes = [_running_loop()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        outcomes.append(pool.submit(_running_loop).result())
    assert all(o is None or hasattr(o, "is_running") for o in outcomes)


# ── end-to-end: enrichment must actually happen off the main thread ───────────
class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


_LLM_JSON = (
    '[{"id": "REQ-1", "statement": "Users must log in",'
    ' "acceptance_criteria": [{"id": "AC-1", "text": "login works"}]}]'
)


class _FakeProvider:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls = 0

    async def chat(self, messages, timeout):  # noqa: ANN001, ANN201
        self.calls += 1
        return _FakeResponse(self._content)


SPEC = "1. Authentication\nUsers must log in."


def test_enrichment_runs_on_a_thread_without_an_event_loop() -> None:
    """THE #271 test: the API's job thread must not lose enrichment.

    Before the fix, `get_event_loop()` raised here and the raise became
    `warnings=["LLM requirement parse failed: There is no current event
    loop in thread ..."]` with `llm_enriched` left False.
    """

    def call():
        provider = _FakeProvider(_LLM_JSON)
        return provider, parse_with_llm_fallback(SPEC, provider)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        provider, result = pool.submit(call).result()

    assert provider.calls == 1, (
        "the provider was never called — enrichment did not run on this thread"
    )
    assert result.llm_enriched is True
    assert not [w for w in result.warnings if "current event loop" in w], (
        f"stale loop failure leaked into warnings: {result.warnings}"
    )
    assert result.requirements and result.requirements[0].id == "REQ-1"


def test_enrichment_runs_on_the_main_thread_too() -> None:
    provider = _FakeProvider(_LLM_JSON)
    result = parse_with_llm_fallback(SPEC, provider)
    assert provider.calls == 1
    assert result.llm_enriched is True


def test_deterministic_result_is_never_discarded() -> None:
    """The documented degradation contract, unchanged by #271."""
    provider = _FakeProvider("this is not JSON at all")
    result = parse_with_llm_fallback(SPEC, provider)
    assert provider.calls == 1
    assert result.llm_enriched is False
    assert result.requirements, "deterministic parse must survive LLM failure"
    assert not [w for w in result.warnings if "current event loop" in w]


def test_no_provider_means_no_llm_and_no_warning() -> None:
    result = parse_with_llm_fallback(SPEC, None)
    assert result.llm_enriched is False
    assert result.requirements


# ── honest pin: the wrapper is currently unreachable ──────────────────────────
def test_llm_enrichment_wrapper_is_currently_unwired() -> None:
    """PIN: nothing outside parser.py calls the enrichment wrapper (#271).

    This is the more important half of the finding. Fixing the asyncio defect
    does NOT make enrichment run — the pipeline's real consumers call
    `parse_requirements` directly. If this test starts failing because you
    wired the wrapper in, that is progress: update docs/operations/
    PRODUCT_ROADMAP.md §43 to say enrichment is now reachable.
    """
    r = subprocess.run(
        ["git", "grep", "-n", "-E",
         "parse_with_llm_fallback|llm_enrich_requirements"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL,
    )
    hits = [line for line in (r.stdout or "").splitlines() if line.strip()]
    # The pin is about CALLERS. Two kinds of mention are not callers, and
    # both are excluded ON PURPOSE:
    #   - the DOCS: PRODUCT_ROADMAP.md §43 has to NAME the wrapper to
    #     document that it is unwired. A documentation of the defect is
    #     not a caller (#383) — and a pin that the documentation of its
    #     own defect breaks is a pin that gets silenced instead of
    #     honoured;
    #   - this file: the pin has to name the wrapper to pin it.
    external = [
        line for line in hits
        if not line.startswith("agent/contracts/parser.py:")
        and not line.startswith("docs/")
        and not line.startswith(
            "tests/unit/test_requirement_enrichment_survives_loopless_thread.py:"
        )
    ]
    assert external == [], (
        "the enrichment wrapper now HAS callers: "
        f"{external} — update roadmap §43 and remove this pin"
    )

