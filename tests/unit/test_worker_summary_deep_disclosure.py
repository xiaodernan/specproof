"""The persisted job summary must disclose what the DEEP tier did.

`run_deep_experiments_node` writes `deep_results` / `deep_note` into the
pipeline state, but `_state_summary` never projected them, so DEEP evidence
existed only in the HTML report and deep-report.json — the dashboard's
summary channel stayed silent. These tests lock the projection:

- results ride along ONLY when the tier actually produced them (an empty
  dict must not masquerade as "DEEP ran and found nothing");
- `deep_note` is always present as an honest answer, including the absent
  case serialising as "" rather than the key disappearing.

Prediction (written before running): a FAST-tier state keeps its note and
gains no `deep_results` key; a DEEP state carries the dict verbatim,
including the verdict_stability classification token.
"""
from __future__ import annotations

from agent.worker import _state_summary


def _base_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "matrix": {},
        "contracts": [],
        "confirmed_findings": [],
        "errors": [],
    }
    state.update(overrides)
    return state


class TestDeepDisclosureInStateSummary:
    def test_fast_tier_keeps_its_honest_note_without_fabricating_results(self) -> None:
        summary = _state_summary(
            _base_state(deep_results={}, deep_note="DEEP tier not requested"),
            "VERIFIED",
        )
        assert "deep_results" not in summary
        assert summary["deep_note"] == "DEEP tier not requested"

    def test_results_ride_along_verbatim_when_the_tier_produced_them(self) -> None:
        deep = {
            "verdict_stability": {
                "repeat_count": 2,
                "verdicts": ["exit_0", "exit_0"],
                "classification": "stable",
                "runs": [{"exit_code": 0, "error": ""}, {"exit_code": 0, "error": ""}],
            },
            "job_id": "job-1",
            "deep_report_file": "deep-report-job-1.json",
            "deep_report_naming": "job-scoped",
        }
        summary = _state_summary(
            _base_state(
                deep_results=deep,
                deep_note="DEEP experiments completed: mutation campaigns=1, state delta captured",
            ),
            "VERIFIED",
        )
        assert summary["deep_results"] == deep
        assert summary["deep_results"]["verdict_stability"]["classification"] == "stable"
        assert summary["deep_note"].endswith("state delta captured")

    def test_an_empty_deep_results_dict_never_masquerades_as_a_run(self) -> None:
        # The node can also return {} (DEEP skipped: no head workspace); the
        # summary must then say nothing about results rather than carry a
        # shape a reader could mistake for "DEEP ran, nothing found".
        summary = _state_summary(
            _base_state(
                deep_results={},
                deep_note="DEEP skipped: no head workspace or generated test",
            ),
            "BLOCKED",
        )
        assert "deep_results" not in summary
        assert summary["deep_note"] == "DEEP skipped: no head workspace or generated test"

    def test_a_state_without_deep_keys_stays_serialisable_and_silent(self) -> None:
        import json

        summary = _state_summary(_base_state(), "VERIFIED")
        assert "deep_results" not in summary
        assert summary["deep_note"] == ""
        assert json.loads(json.dumps(summary, default=str))["verdict"] == "VERIFIED"
