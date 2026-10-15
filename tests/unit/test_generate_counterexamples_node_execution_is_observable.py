"""Generate-counterexamples node execution tests (#197) — honest counters
at the node boundary, written WITH the landing (not backfilled).

The LLM provider seam (``_get_provider``), the compile seam
(``_compile_test``), the differential runner seam
(``agent.nodes.run_differential._run_generated_test``) and the asyncio
handle are stubbed; the deterministic template construction, the review
stage and the record assembly run for real. One case per outcome word in
GENERATE_TEST_OUTCOMES:

- no_workspace: empty head workspace — the provider is never consulted
  (witness: the _get_provider stub would raise);
- template_unsupported: LLM unavailable AND a non-demo repo — the honest
  refusal with an empty path (witness: the template builder would raise);
- deterministic_template: the demo fallback test is written and its
  recorded head run rides the record (exit_code 0, no COMPILATION ERROR);
- llm_generated: a fake provider answers a schema-valid test whose
  compile succeeds (witness: exactly one chat call, and the written file
  is the LLM's code);

plus generate_counterexamples_runs_total on every path and a drift gate
binding the parity family's regex words to GENERATE_TEST_OUTCOMES and to
the source literals.
"""

from __future__ import annotations

import asyncio as real_asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent.nodes.generate_counterexamples as gen_module
from agent.nodes.generate_counterexamples import (
    GENERATE_TEST_OUTCOMES,
    generate_counterexamples_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("generate_counterexamples_runs_total",) + tuple(
    f"generate_counterexamples_outcomes_{word}_total"
    for word in sorted(GENERATE_TEST_OUTCOMES)
)

_LLM_CODE = (
    "import org.junit.jupiter.api.Test;\n"
    "class SpecProofGeneratedTest {\n"
    "    @Test\n"
    "    void t() { MockMvc mockMvc = null; }\n"
    "}\n"
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["generate_counterexamples_runs_total"] = 1.0
    for word in words:
        deltas[f"generate_counterexamples_outcomes_{word}_total"] = 1.0
    return deltas


def _state(workspace: str, **overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "head_workspace": workspace,
        "app_dir": "",
        "static_findings": [],
        "confirmed_findings": [],
        "contracts": [],
        "requirement_text": "unauthenticated email change must be rejected",
    }
    state.update(overrides)
    return state


class _FakeProvider:
    """Async provider double answering chat() with canned JUnit code."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = 0

    async def chat(
        self, messages: object = None, thinking: bool = False, timeout: float = 0.0
    ) -> object:  # noqa: ARG002
        self.calls += 1
        return SimpleNamespace(content=self.content)


def test_no_workspace_counts_no_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    def bomb_provider() -> None:
        raise AssertionError("no workspace must short-circuit before the provider")

    monkeypatch.setattr(gen_module, "_get_provider", bomb_provider)

    before = _before()
    out = generate_counterexamples_node(_state(""))  # type: ignore[arg-type]

    assert out["generated_tests_path"] == ""
    assert out["generation_record"]["errors"] == [
        "No head workspace - cannot generate tests"
    ]
    assert _deltas(before) == _only("no_workspace")


def test_template_unsupported_counts_refusal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def bomb_template(contracts: list[dict[str, Any]]) -> str:
        raise AssertionError("a non-demo repo must be refused before templating")

    monkeypatch.setattr(gen_module, "_build_deterministic_test", bomb_template)

    # use_llm=False -> no provider attempted; no pom.xml -> not the demo repo.
    before = _before()
    out = generate_counterexamples_node(  # type: ignore[arg-type]
        _state(str(tmp_path), use_llm=False)
    )

    assert out["generated_tests_path"] == ""
    errors = out["generation_record"]["errors"]
    assert any("only supports the demo repository" in e for e in errors)
    assert out["generation_record"]["compile_passed"] is False
    assert _deltas(before) == _only("template_unsupported")


def test_deterministic_template_records_its_head_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><groupId>com.specproof</groupId></project>", encoding="utf-8"
    )

    def fake_head_run(workspace: str, class_name: str) -> dict[str, Any]:
        return {
            "exit_code": 0,
            "test_counts": {"tests": 1, "failures": 0},
            "stdout": "BUILD SUCCESS",
            "stderr": "",
        }

    monkeypatch.setattr(
        "agent.nodes.run_differential._run_generated_test", fake_head_run
    )

    before = _before()
    out = generate_counterexamples_node(  # type: ignore[arg-type]
        _state(str(tmp_path), use_llm=False)
    )

    assert out["generated_tests_path"].endswith("SpecProofGeneratedTest.java")
    assert Path(out["generated_tests_path"]).is_file()
    record = out["generation_record"]
    assert record["source"] == "deterministic_template"
    assert record["compile_passed"] is True
    assert record["head_run"]["exit_code"] == 0
    assert record["head_run"]["compile_error"] is False
    assert "class SpecProofGeneratedTest" in Path(
        out["generated_tests_path"]
    ).read_text(encoding="utf-8")
    assert _deltas(before) == _only("deterministic_template")


def test_llm_generated_counts_llm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeProvider(_LLM_CODE)
    monkeypatch.setattr(gen_module, "_get_provider", lambda: fake)
    monkeypatch.setattr(gen_module, "_compile_test", lambda ws, tf: (0, ""))
    # Deterministic branch selection: report "not inside a running loop" so
    # the node runs the coroutine on the real asyncio runner. #265 replaced
    # `asyncio.get_event_loop().is_running()` with `_inside_running_loop()`,
    # because get_event_loop RAISES RuntimeError on the API's loop-less job
    # thread and that raise fell into the node's bare except. Stub the helper
    # itself — it is the seam — which also keeps this test independent of
    # whichever asyncio accessor the node uses to answer the question.
    monkeypatch.setattr(gen_module, "_inside_running_loop", lambda: False)
    monkeypatch.setattr(
        gen_module,
        "asyncio",
        SimpleNamespace(run=real_asyncio.run),
    )

    before = _before()
    out = generate_counterexamples_node(_state(str(tmp_path)))  # type: ignore[arg-type]

    record = out["generation_record"]
    assert record["source"] == "llm_generated"
    assert record["attempts"] == 1
    assert fake.calls == 1
    assert Path(out["generated_tests_path"]).read_text(
        encoding="utf-8"
    ) == _LLM_CODE
    assert _deltas(before) == _only("llm_generated")


def test_workspace_outside_the_temp_dir_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real checkout is refused — the leak that left demo/ polluted.

    ``prepare_head`` only ever hands the node a ``tempfile.mkdtemp`` tree, so
    any path outside the system temp dir means a caller bypassed it. Writing
    there plants ``SpecProofGeneratedTest.java`` in someone's repository,
    which is exactly what happened: it sat as the only stray path under
    ``demo/``, and no diff-based check could see it because it was untracked.
    """
    outside = Path(ROOT) / "demo" / "spring-backend"

    def bomb_provider() -> None:
        raise AssertionError("a refused workspace must never reach the provider")

    monkeypatch.setattr(gen_module, "_get_provider", bomb_provider)

    before = _before()
    out = generate_counterexamples_node(_state(str(outside)))  # type: ignore[arg-type]

    assert out["generated_tests_path"] == ""
    errors = out["generation_record"]["errors"]
    assert len(errors) == 1 and "not under the temp dir" in errors[0], errors
    # The write never happened: no generated test in the demo tree.
    assert not (outside / "src/test/java/com/specproof/demo/SpecProofGeneratedTest.java").exists()
    assert _deltas(before) == _only("workspace_not_tempdir")


def test_a_tempdir_workspace_is_still_accepted(tmp_path: Path) -> None:
    """The refusal must not refuse what prepare_head actually produces.

    Without this arm the guard could be green while refusing every real run:
    a check that only ever proves "outside is refused" says nothing about
    "inside still works".
    """
    assert gen_module.refuse_to_pollute_a_checkout(tmp_path) == ""
    assert gen_module.refuse_to_pollute_a_checkout(str(tmp_path)) == ""


def test_the_write_site_itself_is_guarded(tmp_path: Path) -> None:
    """Defense in depth: the coroutine refuses too, not only its caller.

    ``test_worker_cancel_points`` calls ``_generate_with_compile_loop``
    directly, so a guard placed only in the node would leave the write itself
    unprotected for every other caller.
    """
    from agent.nodes.generate_counterexamples import (
        _generate_with_compile_loop,
        refuse_to_pollute_a_checkout,
    )

    outside = str(Path(ROOT) / "demo" / "spring-backend")
    assert refuse_to_pollute_a_checkout(outside) != ""

    async def _go() -> Any:
        return await _generate_with_compile_loop(outside, [], [], "spec")

    result = real_asyncio.run(_go())
    assert result.compile_exit_code == -1
    assert "not under the temp dir" in result.compile_stderr
    assert result.code == ""


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (
        ROOT / "agent" / "nodes" / "generate_counterexamples.py"
    ).read_text(encoding="utf-8")
    literals = set(
        re.findall(
            r'incr\("generate_counterexamples_outcomes_([a-z0-9_]+)_total"\)',
            source,
        )
    )
    assert literals == set(GENERATE_TEST_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(GENERATE_TEST_OUTCOMES)}"
    )
    assert source.count('incr("generate_counterexamples_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["generate_counterexamples"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(GENERATE_TEST_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(GENERATE_TEST_OUTCOMES)}"
    )
