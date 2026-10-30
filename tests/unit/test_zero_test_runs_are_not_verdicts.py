"""#532: a run that executed no tests must not become a verdict.

Measured before writing (pre-fix code): a DEEP sequence whose runs all exited
non-zero with no surefire summary classified ``stable`` — every repeat agreed
on a token derived from an exit code that no test produced — and a mutation
campaign whose every mutant failed to compile reported ``killed ==
mutants_total`` with ``mutation_score == 1.0``. A toolchain error and a
selector that matched nothing both produce exactly that shape, so the two
readers were manufacturing the strongest possible conclusions out of "nothing
was measured".

Ends pinned here, one per reader:

  1. ``verdict_stability.summarize`` projects a zero-test run as ``not_run``
     and the sequence as ``not_verified``. Counts are required evidence:
     a record without ``test_counts`` reads as zero executed, so deleting the
     key cannot buy back the old verdict, and environment contamination keeps
     its precedence over every classification.
  2. ``experiments.mutation.run_mutation_campaign`` requires the runner to
     report executed tests: only an executed run can kill or survive, a
     not-run mutant is counted in its own bucket, and the mutation score's
     denominator is the executed mutants (killed + survived).
  3. The DEEP node carries both through end to end: one run where every
     sandbox call is a compile failure (exit 1, no summary) reaches the
     artifact as ``not_verified`` stability and ``not_run`` mutants — and the
     mutated source is still restored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import agent.nodes.run_deep_experiments as deep
from agent.verdict_stability import summarize
from experiments.mutation import generate_mutants, run_mutation_campaign

SOURCE = """@Service
public class Svc {
    @Transactional
    public boolean ok(Long id) {
        if (id == null) {
            return false;
        }
        return id != null;
    }
}
"""


# ---------------------------------------------------------------------------
# 1. the stability reader
# ---------------------------------------------------------------------------


def test_a_zero_test_sequence_is_never_stable() -> None:
    summary = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 0}},
            {"exit_code": 0, "error": "", "test_counts": {"tests": 0}},
        ]
    )
    assert summary["verdicts"] == ["not_run", "not_run"]
    assert summary["classification"] == "not_verified"
    assert summary["runs_without_execution"] == 2


def test_missing_counts_are_not_trusted() -> None:
    """Dropping the key must not buy back the pre-#532 behaviour."""
    summary = summarize([{"exit_code": 0, "error": ""}] * 2)
    assert summary["verdicts"] == ["not_run", "not_run"]
    assert summary["classification"] == "not_verified"
    assert summary["runs_without_execution"] == 2


def test_malformed_counts_are_zero_not_a_verdict() -> None:
    # bool is an int subclass and a negative or string count is not evidence;
    # every malformed shape must read as "cannot be shown", not as trust.
    for counts in (
        {"tests": True},
        {"tests": "3"},
        {"tests": -2},
        {"tests": None},
        "3",
        None,
    ):
        summary = summarize(
            [{"exit_code": 0, "test_counts": counts}] * 2
        )
        assert summary["verdicts"] == ["not_run", "not_run"], counts
        assert summary["classification"] == "not_verified", counts


def test_one_executed_and_one_mute_run_is_not_verified() -> None:
    summary = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 3}},
            {"exit_code": 1, "error": "build failed", "test_counts": {"tests": 0}},
        ]
    )
    assert summary["verdicts"] == ["exit_0", "not_run"]
    assert summary["classification"] == "not_verified"
    assert summary["runs_without_execution"] == 1


def test_contamination_outranks_not_verified() -> None:
    summary = summarize(
        [{"exit_code": 0, "error": "", "test_counts": {"tests": 0}}] * 2,
        contaminated=True,
    )
    assert summary["classification"] == "contaminated"
    assert summary["verdicts"] == ["not_run", "not_run"]


def test_executed_runs_keep_the_existing_vocabulary() -> None:
    # Control: the fix must not swallow the healthy classifications.
    stable = summarize(
        [{"exit_code": 0, "error": "", "test_counts": {"tests": 2}}] * 2
    )
    assert stable["verdicts"] == ["exit_0", "exit_0"]
    assert stable["classification"] == "stable"
    assert stable["runs_without_execution"] == 0

    flaky = summarize(
        [
            {"exit_code": 0, "error": "", "test_counts": {"tests": 1}},
            {"exit_code": 1, "error": "boom", "test_counts": {"tests": 1}},
        ]
    )
    assert flaky["verdicts"] == ["exit_0", "exit_1"]
    assert flaky["classification"] == "flaky"


# ---------------------------------------------------------------------------
# 2. the mutation reader
# ---------------------------------------------------------------------------


def test_a_mutant_run_that_executed_no_tests_is_not_killed() -> None:
    """A compile failure exits non-zero; pre-#532 that booked every kill."""
    report = run_mutation_campaign(
        "Svc.java", SOURCE, lambda _content: (1, "compilation failed", 0)
    )
    assert report.mutants_total == len(generate_mutants(SOURCE))
    assert report.killed == 0
    assert report.survived == 0
    assert report.not_run == report.mutants_total

    payload = report.to_dict()
    assert payload["mutation_score"] == 0.0
    assert payload["not_run"] == report.mutants_total
    assert all(
        r["not_run"] and not r["killed"] and r["tests_executed"] == 0
        for r in payload["results"]
    )


def test_a_mute_passing_run_is_not_survived() -> None:
    """Exit 0 with no tests executed is not a spared mutant either."""
    report = run_mutation_campaign(
        "Svc.java", SOURCE, lambda _content: (0, "", 0)
    )
    assert report.killed == 0
    assert report.survived == 0
    assert report.not_run == report.mutants_total
    assert report.to_dict()["mutation_score"] == 0.0


def test_executed_mutants_still_kill_and_survive() -> None:
    def runner(content: str) -> tuple[int, str, int]:
        return (1 if "@Transactional" not in content else 0), "", 3

    report = run_mutation_campaign("Svc.java", SOURCE, runner)
    assert report.killed >= 1
    assert report.survived >= 1
    assert report.killed + report.survived == report.mutants_total
    assert report.not_run == 0
    assert report.to_dict()["mutation_score"] == round(
        report.killed / report.mutants_total, 3
    )


def test_the_mutation_score_counts_only_executed_mutants() -> None:
    """One executed kill + compile-failure mutants: score is 1/1, not 1/total."""
    def runner(content: str) -> tuple[int, str, int]:
        if "@Transactional" not in content:
            return 1, "", 3          # executed, failed on the mutant: killed
        return 1, "compilation failed", 0  # never measured: not_run

    report = run_mutation_campaign("Svc.java", SOURCE, runner)
    assert report.mutants_total > 1
    assert report.killed == 1
    assert report.survived == 0
    assert report.not_run == report.mutants_total - 1
    assert report.to_dict()["mutation_score"] == 1.0


# ---------------------------------------------------------------------------
# 3. the DEEP node carries both through
# ---------------------------------------------------------------------------


def _make_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pom.xml").write_text("<project/>", encoding="utf-8")
    java = root / "src" / "main" / "java" / "Svc.java"
    java.parent.mkdir(parents=True)
    java.write_text(SOURCE, encoding="utf-8")
    return root


def test_deep_records_a_compile_failure_as_not_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _make_repo(tmp_path / "repo")
    source_path = app / "src" / "main" / "java" / "Svc.java"
    original = source_path.read_text(encoding="utf-8")

    sandbox_calls: list[tuple[str, str]] = []

    def compile_failure(app_arg: str, tests_arg: str) -> dict[str, Any]:
        # Exit 1 with no surefire summary: a build error (or a selector that
        # matched nothing). Pre-#532 this manufactured a "stable" sequence
        # and a campaign with every mutant killed.
        sandbox_calls.append((app_arg, tests_arg))
        return {
            "exit_code": 1,
            "error": "compilation failed",
            "mode": "docker",
            "cache_note": "",
        }

    monkeypatch.setattr(deep, "_run_test_via_sandbox", compile_failure)
    monkeypatch.setattr(
        "experiments.state_snapshot.capture_full_stack", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        "experiments.state_snapshot.diff_states",
        lambda before, after: {"tables": {}},
    )
    monkeypatch.setattr("storage.mysql.MySQLStore", lambda: object())
    monkeypatch.setattr("storage.redis.RedisStore", lambda: object())
    monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", lambda: object())
    monkeypatch.setattr(
        "agent.nodes.run_differential._capture_db_snapshot",
        lambda workspace: {"rows": 1},
    )
    monkeypatch.setenv("SPECPROOF_DEEP_REPEATS", "2")

    out = deep.run_deep_experiments_node({  # type: ignore[arg-type]
        "depth": "DEEP",
        "head_workspace": str(app),
        "generated_tests_path": str(app / "SvcTest.java"),
        "output_dir": str(tmp_path / "reports"),
        "job_id": "",
    })

    results = out["deep_results"]
    assert results["state_delta"]["head_test_exit"] == 1
    assert results["state_delta"]["head_test_counts"] == {}

    stability = results["verdict_stability"]
    assert stability["classification"] == "not_verified"
    assert stability["verdicts"] == ["not_run", "not_run"]
    assert stability["runs_without_execution"] == 2

    mutants_total = len(generate_mutants(original, 10))
    assert mutants_total >= 1
    campaign = results["mutation"][0]
    assert campaign["killed"] == 0
    assert campaign["survived"] == 0
    assert campaign["not_run"] == mutants_total
    assert campaign["mutation_score"] == 0.0

    # The artifact a reader holds says the same thing.
    payload = json.loads(
        (tmp_path / "reports" / "deep-report.json").read_text(encoding="utf-8")
    )
    assert payload["verdict_stability"]["classification"] == "not_verified"
    assert payload["verdict_stability"]["verdicts"] == ["not_run", "not_run"]
    assert payload["mutation"][0]["not_run"] == mutants_total
    assert payload["state_delta"]["head_test_exit"] == 1

    # 1 head run + 2 stability repeats + one run per mutant.
    assert len(sandbox_calls) == 3 + mutants_total
    assert source_path.read_text(encoding="utf-8") == original, (
        "the mutation runner must restore the original source after every run"
    )
