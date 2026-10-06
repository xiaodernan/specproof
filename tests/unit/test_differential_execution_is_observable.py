"""Differential verification execution tests (#185) — honest counters at the
run_differential node boundary.

No real git repos, no Maven: the node's internal helpers are monkeypatched at
the agent.nodes.run_differential seam. Covers:

- the counter family: runs / skipped / errors / outcomes_<word>
  (delta assertions — the registry is process-global);
- skip paths: non-demo repo and no-test-generation both increment skipped;
- error path: exception during diff increments errors;
- per-outcome counting: regression/compliant/ambiguous/unexpected_fix/skipped
  verdicts each increment their own bucket;
- the outcome vocabulary tracks DIFF_OUTCOMES frozenset (drift gate).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.nodes.run_differential import DIFF_OUTCOMES
from observability.metrics import snapshot


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


# ── the counter family ─────────────────────────────────────────────────────


def test_run_differential_counts_total_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Every call to run_differential increments runs_total."""
    from agent.nodes.run_differential import run_differential

    before = _counter("differential_runs_total")

    # Stub all internal helpers to return empty results immediately
    def fake_diff(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    def fake_contract(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(
        "agent.nodes.run_differential._run_single_diff", fake_diff
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._run_contract_check", fake_contract
    )

    state = {
        "repo_path": str(tmp_path),
        "base_branch": "main",
        "head_branch": "feature",
        "requirements": "# test",
    }
    run_differential(state)

    after = _counter("differential_runs_total")
    assert after == before + 1, "runs_total must increment by exactly 1"


def test_skip_non_demo_repo_increments_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Non-demo repo detection increments skipped_total."""
    from agent.nodes.run_differential import run_differential

    before = _counter("differential_skipped_total")

    def fake_is_demo(*args, **kwargs):  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(
        "agent.nodes.run_differential._is_demo_repo", fake_is_demo
    )

    state = {
        "repo_path": str(tmp_path),
        "base_branch": "main",
        "head_branch": "feature",
        "requirements": "# test",
    }
    result = run_differential(state)

    after = _counter("differential_skipped_total")
    assert after == before + 1, "skipped_total must increment for non-demo repo"
    assert result.get("diff_results") == [], "skip path returns empty results"


def test_no_test_generation_increments_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """When no tests can be generated, skipped_total increments."""
    from agent.nodes.run_differential import run_differential

    before = _counter("differential_skipped_total")

    def fake_is_demo(*args, **kwargs):  # type: ignore[no-untyped-def]
        return True

    def fake_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None  # No tests generated

    monkeypatch.setattr(
        "agent.nodes.run_differential._is_demo_repo", fake_is_demo
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._generate_counterexamples",
        fake_generate,
    )

    state = {
        "repo_path": str(tmp_path),
        "base_branch": "main",
        "head_branch": "feature",
        "requirements": "# test",
    }
    result = run_differential(state)

    after = _counter("differential_skipped_total")
    assert after == before + 1, "skipped_total must increment when no tests generated"
    assert result.get("diff_results") == [], "skip path returns empty results"


def test_exception_during_diff_increments_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """An exception during differential run increments errors_total."""
    from agent.nodes.run_differential import run_differential

    before = _counter("differential_errors_total")

    def fake_is_demo(*args, **kwargs):  # type: ignore[no-untyped-def]
        return True

    def fake_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {"test_class": "TestExample"}

    def fake_diff(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "agent.nodes.run_differential._is_demo_repo", fake_is_demo
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._generate_counterexamples",
        fake_generate,
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._run_single_diff", fake_diff
    )

    state = {
        "repo_path": str(tmp_path),
        "base_branch": "main",
        "head_branch": "feature",
        "requirements": "# test",
    }

    with pytest.raises(RuntimeError, match="simulated failure"):
        run_differential(state)

    after = _counter("differential_errors_total")
    assert after == before + 1, "errors_total must increment on exception"


def test_per_outcome_counting_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Each diff result's verdict increments its corresponding outcome bucket."""
    from agent.nodes.run_differential import run_differential

    before_regression = _counter("differential_outcomes_regression_total")
    before_compliant = _counter("differential_outcomes_compliant_total")
    before_ambiguous = _counter("differential_outcomes_ambiguous_total")
    before_unexpected = _counter("differential_outcomes_unexpected_fix_total")

    def fake_is_demo(*args, **kwargs):  # type: ignore[no-untyped-def]
        return True

    def fake_generate(*args, **kwargs):  # type: ignore[no-untyped-def]
        return {"test_class": "TestExample"}

    def fake_diff(*args, **kwargs):  # type: ignore[no-untyped-def]
        return [
            {"verdict": "REGRESSION", "contract_id": "AUTH-01"},
            {"verdict": "COMPLIANT", "contract_id": "AUTH-02"},
            {"verdict": "AMBIGUOUS", "contract_id": "AUTH-03"},
            {"verdict": "UNEXPECTED_FIX", "contract_id": "AUTH-04"},
        ]

    def fake_contract(*args, **kwargs):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(
        "agent.nodes.run_differential._is_demo_repo", fake_is_demo
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._generate_counterexamples",
        fake_generate,
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._run_single_diff", fake_diff
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._run_contract_check", fake_contract
    )

    state = {
        "repo_path": str(tmp_path),
        "base_branch": "main",
        "head_branch": "feature",
        "requirements": "# test",
    }
    run_differential(state)

    after_regression = _counter("differential_outcomes_regression_total")
    after_compliant = _counter("differential_outcomes_compliant_total")
    after_ambiguous = _counter("differential_outcomes_ambiguous_total")
    after_unexpected = _counter("differential_outcomes_unexpected_fix_total")

    assert after_regression == before_regression + 1
    assert after_compliant == before_compliant + 1
    assert after_ambiguous == before_ambiguous + 1
    assert after_unexpected == before_unexpected + 1


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
