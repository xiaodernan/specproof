"""Differential verification execution tests (#185, reconciled in #185b) —
honest counters at the run_differential node boundary.

The node's only execution seam (run_with_cancel_checks) is stubbed with
preset Base/Head/Probe results; everything else runs for real against tmp
workspaces (test injection, source scan, DB-snapshot degrade path, verdict
computation). Covers:

- the counter family: differential_runs_total / differential_errors_total /
  differential_outcomes_<word>_total (delta assertions — the registry is
  process-global);
- skip paths: not-prepared workspaces, no generated test, injection failure
  each increment outcomes_skipped;
- error path: a Base/Head result carrying a non-empty ``error`` increments
  differential_errors_total and NOT outcomes_ambiguous (#185b: the
  ambiguous bucket keeps its declared meaning base_fail + head_fail);
- per-outcome counting: regression/compliant/ambiguous/unexpected_fix
  verdicts each increment their own bucket;
- the outcome vocabulary tracks DIFF_OUTCOMES frozenset (drift gate).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent.nodes.run_differential import DIFF_OUTCOMES
from agent.preflight import LANGUAGE_JAVA
from observability.metrics import snapshot


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


# Shape mirrors _run_generated_test's return contract (the keys the node
# reads back: exit_code / stdout / stderr / test_counts / error).
_OK_RESULT: dict[str, Any] = {
    "exit_code": 0,
    "stdout": "",
    "stderr": "",
    "test_counts": {},
    "error": "",
}


def _stub_execution(
    monkeypatch: pytest.MonkeyPatch, results: dict[str, Any]
) -> list[str]:
    """Replace the node's execution seam with presets; return the call log."""
    calls: list[str] = []

    def fake(job_id: object, stage: str, fn: object, *args: object, **kwargs: object) -> Any:  # noqa: ARG001
        calls.append(stage)
        return results[stage]

    monkeypatch.setattr(
        "agent.nodes.run_differential.run_with_cancel_checks", fake
    )
    return calls


def _make_state(tmp_path: Path, generated: bool = True) -> dict[str, Any]:
    base_ws = tmp_path / "base"
    head_ws = tmp_path / "head"
    base_ws.mkdir()
    head_ws.mkdir()
    gen = tmp_path / "SpecProofGeneratedTest.java"
    if generated:
        gen.write_text("class SpecProofGeneratedTest {}\n", encoding="utf-8")
    return {
        # No repo_path: base_build_cache_dir() returns None, so the run uses
        # no build cache (the cache paths have their own witnesses).
        "repo_path": "",
        "app_dir": "",
        "base_workspace": str(base_ws),
        "head_workspace": str(head_ws),
        "generated_tests_path": str(gen) if generated else "",
        "contracts": [],
    }


# ── the counter family ─────────────────────────────────────────────────────


def test_run_differential_counts_total_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A full execution increments runs_total and its outcome bucket."""
    from agent.nodes.run_differential import run_differential_node

    before_runs = _counter("differential_runs_total")
    before_compliant = _counter("differential_outcomes_compliant_total")

    calls = _stub_execution(monkeypatch, {
        "maven_base": dict(_OK_RESULT),
        "maven_head": dict(_OK_RESULT),
        "maven_probe": [],
    })
    result = run_differential_node(_make_state(tmp_path))

    assert calls == ["maven_base", "maven_head", "maven_probe"], (
        "both sides plus the probe must go through the execution seam"
    )
    assert _counter("differential_runs_total") == before_runs + 1
    assert _counter("differential_outcomes_compliant_total") == before_compliant + 1
    assert any(r.get("verdict") == "COMPLIANT" for r in result["diff_results"])


# ── the external world, observed at TWO moments ─────────────────────────────


def test_the_external_world_is_captured_after_each_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The two snapshots must be taken BETWEEN the two runs.

    Base and Head are two directories that talk to the SAME services.
    The only thing a base/head comparison of the external world can be
    about is the difference between "after the Base run" and "after the
    Head run" — so the captures have to straddle the Head run. Two
    captures taken after both runs would compare the same instant with
    itself, and two taken before both would miss the Head run entirely.
    """
    from agent.nodes.run_differential import run_differential_node

    events: list[str] = []

    def fake_run(job_id: object, stage: str, fn: object, *args: object, **kwargs: object) -> Any:  # noqa: ARG001
        events.append(stage)
        if stage == "maven_base":
            return dict(_OK_RESULT)
        if stage == "maven_head":
            return dict(_OK_RESULT)
        return []

    monkeypatch.setattr(
        "agent.nodes.run_differential.run_with_cancel_checks", fake_run
    )

    snapshots: list[dict[str, Any]] = []

    def fake_capture(state: Any) -> dict[str, Any]:
        snapshots.append({"stage": events[-1] if events else "none"})
        return {"redis": {}, "objects": {}, "moment": len(snapshots)}

    monkeypatch.setattr(
        "agent.nodes.run_differential._capture_external_state", fake_capture
    )

    result = run_differential_node(_make_state(tmp_path))

    # THREE captures: the baseline (before the Base run), the Base
    # moment, and the Head moment. The baseline is what makes the reset
    # safe — it is the difference that says which keys the Base run
    # created.
    assert len(snapshots) == 3
    assert snapshots[0]["stage"] == "none", "the baseline is taken BEFORE the runs"
    assert snapshots[1]["stage"] == "maven_base"
    assert snapshots[2]["stage"] == "maven_head"
    # And the two that travel with the result are the Base and Head
    # moments — the collector compares THESE.
    assert result["external_state_base"]["moment"] == 2
    assert result["external_state_head"]["moment"] == 3


def test_an_unreachable_external_store_captures_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A store that cannot be reached yields an EMPTY capture.

    Empty means "we did not look" — it must never be filled in with an
    assumption, and it must never abort the differential run.
    """
    from agent.nodes.run_differential import run_differential_node

    _stub_execution(monkeypatch, {
        "maven_base": dict(_OK_RESULT),
        "maven_head": dict(_OK_RESULT),
        "maven_probe": [],
    })
    monkeypatch.setattr(
        "agent.nodes.run_differential._capture_external_state",
        lambda state: {"redis": {}, "objects": {}, "note": "no store reachable"},
    )

    result = run_differential_node(_make_state(tmp_path))

    assert result["external_state_base"] == {
        "redis": {}, "objects": {}, "note": "no store reachable",
    }
    # The run itself still produced its verdict.
    assert any(r.get("verdict") == "COMPLIANT" for r in result["diff_results"])


def test_the_external_world_is_reset_between_the_two_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The reset must straddle the Head run.

    Two captures taken after both runs compare the same instant with
    itself; a reset taken before the Base run would be undone by the
    Base run itself. The only placement that makes the two snapshots
    comparable is: capture → reset → Head run → capture.
    """
    from agent.nodes.run_differential import run_differential_node

    events: list[str] = []

    def fake_run(job_id: object, stage: str, fn: object, *args: object, **kwargs: object) -> Any:  # noqa: ARG001
        events.append(stage)
        if stage == "maven_base":
            return dict(_OK_RESULT)
        if stage == "maven_head":
            return dict(_OK_RESULT)
        return []

    monkeypatch.setattr(
        "agent.nodes.run_differential.run_with_cancel_checks", fake_run
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._capture_external_state",
        lambda state: {"redis": {}, "objects": {}, "moment": len(events)},
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._reset_external_state",
        lambda baseline, after_base: (
            events.append("reset"),
            {"reset": True, "keys_removed": 3},
        )[1],
    )

    result = run_differential_node(_make_state(tmp_path))

    # The reset happened after the Base run and before the Head run.
    assert result["external_reset"]["reset"] is True
    assert events.index("maven_base") < events.index("reset") < events.index(
        "maven_head"
    )
    # And it travels with the result, so the evidence can say the two
    # moments are comparable.
    assert result["external_reset"]["keys_removed"] == 3


def test_workspace_not_prepared_counts_skipped(tmp_path: Path) -> None:
    """Missing workspaces: the attempt is counted, skipped, and honest."""
    from agent.nodes.run_differential import run_differential_node

    before_runs = _counter("differential_runs_total")
    before_skipped = _counter("differential_outcomes_skipped_total")

    result = run_differential_node(
        {"base_workspace": "", "head_workspace": "", "app_dir": ""}
    )

    assert _counter("differential_runs_total") == before_runs + 1
    assert _counter("differential_outcomes_skipped_total") == before_skipped + 1
    assert any(
        r.get("verdict") == "NON_REPRODUCIBLE" for r in result["diff_results"]
    ), "the skip path must say why nothing ran"


def test_no_generated_test_counts_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """No generated test to run: runs+1, skipped+1, nothing executed."""
    from agent.nodes.run_differential import run_differential_node

    before_runs = _counter("differential_runs_total")
    before_skipped = _counter("differential_outcomes_skipped_total")

    # Pin the language to Java so the branch's multi-language fallback text
    # (which depends on the operator's env) cannot change the control flow.
    monkeypatch.setattr(
        "agent.nodes.run_differential.detect_language",
        lambda *a, **k: LANGUAGE_JAVA,
    )
    calls = _stub_execution(monkeypatch, {})  # nothing may execute

    result = run_differential_node(_make_state(tmp_path, generated=False))

    assert calls == [], "a skip path must not reach the execution seam"
    assert _counter("differential_runs_total") == before_runs + 1
    assert _counter("differential_outcomes_skipped_total") == before_skipped + 1
    assert any(
        r.get("verdict") == "NON_REPRODUCIBLE" for r in result["diff_results"]
    )


def test_injection_failure_counts_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Generated test cannot be injected: runs+1, skipped+1, nothing executed."""
    from agent.nodes.run_differential import run_differential_node

    before_runs = _counter("differential_runs_total")
    before_skipped = _counter("differential_outcomes_skipped_total")

    calls = _stub_execution(monkeypatch, {})  # nothing may execute
    state = _make_state(tmp_path)
    state["generated_tests_path"] = str(tmp_path / "Missing.java")

    result = run_differential_node(state)

    assert calls == [], "a skip path must not reach the execution seam"
    assert _counter("differential_runs_total") == before_runs + 1
    assert _counter("differential_outcomes_skipped_total") == before_skipped + 1
    assert any(
        r.get("verdict") == "NON_REPRODUCIBLE" for r in result["diff_results"]
    )


def test_execution_error_counts_errors_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A Base/Head error increments errors_total, never outcomes_ambiguous.

    (#185b): folding infra errors into the ambiguous bucket made a declared
    test-outcome word mean two different things; the error path now has its
    own counter and the ambiguous delta must stay exactly 0.
    """
    from agent.nodes.run_differential import run_differential_node

    before_runs = _counter("differential_runs_total")
    before_errors = _counter("differential_errors_total")
    before_ambiguous = _counter("differential_outcomes_ambiguous_total")

    _stub_execution(monkeypatch, {
        "maven_base": dict(_OK_RESULT),
        "maven_head": {**_OK_RESULT, "error": "simulated maven failure"},
        "maven_probe": [],
    })

    result = run_differential_node(_make_state(tmp_path))

    assert _counter("differential_runs_total") == before_runs + 1
    assert _counter("differential_errors_total") == before_errors + 1
    assert _counter("differential_outcomes_ambiguous_total") == before_ambiguous, (
        "infra errors must not be counted as ambiguous test outcomes"
    )
    assert any(
        "Maven execution error" in r.get("detail", "")
        for r in result["diff_results"]
    )


# ── per-outcome counting ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("base_exit", "head_exit", "word"),
    [
        (0, 1, "regression"),       # base_pass + head_fail
        (0, 0, "compliant"),        # base_pass + head_pass
        (1, 1, "ambiguous"),        # base_fail + head_fail
        (1, 0, "unexpected_fix"),   # base_fail + head_pass
    ],
)
def test_per_outcome_counting_loop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    base_exit: int,
    head_exit: int,
    word: str,
) -> None:
    """Each verdict pattern increments exactly its own outcome bucket."""
    from agent.nodes.run_differential import run_differential_node

    before_word = _counter(f"differential_outcomes_{word}_total")
    before_errors = _counter("differential_errors_total")

    _stub_execution(monkeypatch, {
        "maven_base": {**_OK_RESULT, "exit_code": base_exit},
        "maven_head": {**_OK_RESULT, "exit_code": head_exit},
        "maven_probe": [],
    })

    run_differential_node(_make_state(tmp_path))

    assert _counter(f"differential_outcomes_{word}_total") == before_word + 1
    assert _counter("differential_errors_total") == before_errors


# ── vocabulary drift gate ──────────────────────────────────────────────────


def test_diff_outcomes_vocabulary_matches_declaration() -> None:
    """The parity gate's regex words must equal DIFF_OUTCOMES frozenset."""
    import re

    from tests.unit.test_observability_metric_parity import (
        CONCATENATED_FAMILIES,
    )

    pattern, _doc = CONCATENATED_FAMILIES["diff_outcome"]
    # Extract the alternation group from the pattern
    match = re.search(r"\(([^)]+)\)", pattern.pattern)
    assert match is not None, "pattern must have an alternation group"
    pattern_words = set(match.group(1).split("|"))

    # DIFF_OUTCOMES contains lowercase tokens; the pattern uses them directly
    expected_words = {w.lower() for w in DIFF_OUTCOMES}

    assert pattern_words == expected_words, (
        f"parity gate regex words {sorted(pattern_words)} must match "
        f"DIFF_OUTCOMES declaration {sorted(expected_words)}"
    )
