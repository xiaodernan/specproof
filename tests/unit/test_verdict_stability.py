"""Unit tests for verdict stability classification (§14.1) + DEEP wiring."""

from __future__ import annotations

from typing import Any

from agent.verdict_stability import (
    classify_verdict_sequence,
    classify_with_env,
    summarize,
)


class TestClassifier:
    def test_empty_is_no_runs(self) -> None:
        assert classify_verdict_sequence([]) == "no_runs"

    def test_single_is_honest_single_run(self) -> None:
        assert classify_verdict_sequence(["REGRESSION"]) == "single_run"

    def test_identical_runs_are_stable(self) -> None:
        assert classify_verdict_sequence(["COMPLIANT", "COMPLIANT"]) == "stable"
        assert (
            classify_verdict_sequence(["REGRESSION"] * 3) == "stable"
        )

    def test_disagreeing_runs_are_flaky(self) -> None:
        assert classify_verdict_sequence(["COMPLIANT", "REGRESSION"]) == "flaky"

    def test_contamination_precedes_agreement(self) -> None:
        assert classify_with_env(["COMPLIANT", "COMPLIANT"], True) == "contaminated"
        assert classify_with_env(["COMPLIANT", "REGRESSION"], True) == "contaminated"
        assert classify_with_env([], False) == "no_runs"

    def test_summarize_schema(self) -> None:
        summary = summarize(
            [{"exit_code": 0, "error": ""}, {"exit_code": 0, "error": ""}],
        )
        assert summary["repeat_count"] == 2
        assert summary["verdicts"] == ["exit_0", "exit_0"]
        assert summary["classification"] == "stable"


class TestDeepStabilityWiring:
    """DEEP node attaches verdict_stability with the bounded repeat count."""

    def _state(self, tmp_path) -> dict[str, Any]:
        return {
            "depth": "DEEP",
            "head_workspace": str(tmp_path),
            "app_dir": "",
            "generated_tests_path": str(tmp_path / "T.java"),
            "output_dir": str(tmp_path / "reports"),
            "job_id": "",
        }

    def test_deep_node_records_stability(self, tmp_path, monkeypatch) -> None:
        import agent.nodes.run_deep_experiments as deep

        monkeypatch.setattr(deep, "_run_test_via_sandbox", lambda app, t: {
            "exit_code": 0, "error": "", "mode": "fake",
        })
        monkeypatch.setattr(
            deep, "_make_test_runner",
            lambda *a, **k: (lambda _c: (0, "")),
        )
        # Fake the full-stack storage captures (no live infra in unit tests).
        monkeypatch.setattr(
            "experiments.state_snapshot.capture_full_stack",
            lambda *a, **k: {"tables": {}, "queues": {}},
        )
        monkeypatch.setattr(
            "experiments.state_snapshot.diff_states",
            lambda b, a: {"changed": []},
        )
        monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "2")
        out = deep.run_deep_experiments_node(self._state(tmp_path))
        stability = out["deep_results"]["verdict_stability"]
        assert stability["repeat_count"] == 2
        assert stability["classification"] in ("stable", "flaky", "contaminated")

    def test_repeats_env_cap(self, monkeypatch) -> None:
        import agent.nodes.run_deep_experiments as deep

        monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "999")
        assert deep._env_int("SPECPROOF_DEEP_REPEATS", 2) == 10
        monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "not-a-number")
        assert deep._env_int("SPECPROOF_DEEP_REPEATS", 2) == 2
