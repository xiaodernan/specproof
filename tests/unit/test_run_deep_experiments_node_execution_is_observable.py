"""DEEP-tier node execution tests (#198) — honest counters at the node
boundary, written WITH the landing (not backfilled).

The campaign seam (run_mutation_campaign), the stack-capture seams
(capture_full_stack / diff_states / the three store constructors), the
stability summarizer, the DB snapshot reader and the sandbox runner are
stubbed at their import sources; the report naming, the mutation runner
swap/restore and the record assembly run for real. One case per outcome
word in RUN_DEEP_OUTCOMES:

- not_requested: depth != DEEP (or absent) — the healthy FAST default,
  nothing else touched;
- inputs_missing: DEEP requested but no head workspace / no generated
  test — the tier is silently empty (witness: nothing beyond the first
  guard runs);
- completed: the full campaign — the fake campaign INVOKES the swapped
  runner it is handed, proving the mutant swap is restored afterwards,
  and the head + repeat runs share the recorded cache note;

plus run_deep_experiments_runs_total on every path and a drift gate
binding the parity family's regex words to RUN_DEEP_OUTCOMES and to the
source literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent.nodes.run_deep_experiments as deep_module
from agent.nodes.run_deep_experiments import (
    RUN_DEEP_OUTCOMES,
    run_deep_experiments_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("run_deep_experiments_runs_total",) + tuple(
    f"run_deep_experiments_outcomes_{word}_total"
    for word in sorted(RUN_DEEP_OUTCOMES)
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
    deltas["run_deep_experiments_runs_total"] = 1.0
    for word in words:
        deltas[f"run_deep_experiments_outcomes_{word}_total"] = 1.0
    return deltas


def test_not_requested_counts_not_requested() -> None:
    before = _before()
    out = run_deep_experiments_node({})  # type: ignore[arg-type]

    assert out == {
        "deep_results": {},
        "deep_note": "DEEP tier not requested",
    }
    assert _deltas(before) == _only("not_requested")


def test_inputs_missing_counts_inputs_missing() -> None:
    before = _before()
    out = run_deep_experiments_node(  # type: ignore[arg-type]
        {"depth": "DEEP", "head_workspace": "", "generated_tests_path": ""}
    )

    assert out == {
        "deep_results": {},
        "deep_note": "DEEP skipped: no head workspace or generated test",
    }
    assert _deltas(before) == _only("inputs_missing")


def test_completed_runs_the_full_campaign(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SPECPROOF_DEEP_REPEATS", raising=False)

    app = tmp_path / "head"
    source_path = app / "src" / "main" / "java" / "Svc.java"
    source_path.parent.mkdir(parents=True)
    original_source = "class Svc { void send() {} }"
    source_path.write_text(original_source, encoding="utf-8")

    test_path = tmp_path / "SpecProofGeneratedTest.java"
    test_path.write_text("class SpecProofGeneratedTest {}", encoding="utf-8")

    monkeypatch.setattr(
        "agent.nodes.run_static_checks._read_java_files",
        lambda workspace: {"Svc.java": original_source},
    )

    campaign_calls: list[tuple[str, int]] = []
    runner_results: list[tuple[int, str, int]] = []

    def fake_campaign(rel_path, content, runner, max_mutants=10):
        campaign_calls.append((rel_path, max_mutants))
        # Exercise the swap/restore contract: the runner must put the
        # mutant in place, run the sandbox, and restore the original.
        runner_results.append(runner("class Svc { /* mutant */ }"))
        return SimpleNamespace(to_dict=lambda: {"file": rel_path})

    monkeypatch.setattr("experiments.mutation.run_mutation_campaign", fake_campaign)

    monkeypatch.setattr(
        "experiments.state_snapshot.capture_full_stack", lambda *a, **k: {}
    )
    monkeypatch.setattr(
        "experiments.state_snapshot.diff_states", lambda before, after: {"tables": {}}
    )
    monkeypatch.setattr("storage.mysql.MySQLStore", lambda: object())
    monkeypatch.setattr("storage.redis.RedisStore", lambda: object())
    monkeypatch.setattr("storage.rabbitmq.RabbitMQClient", lambda: object())
    monkeypatch.setattr(
        "agent.verdict_stability.summarize",
        lambda runs, contaminated: {"stability": "stable", "runs": len(runs)},
    )
    monkeypatch.setattr(
        "agent.nodes.run_differential._capture_db_snapshot",
        lambda workspace: {"rows": 1},
    )

    sandbox_calls: list[tuple[str, str]] = []

    def fake_sandbox(app_arg: str, tests_arg: str) -> dict[str, Any]:
        sandbox_calls.append((app_arg, tests_arg))
        return {
            "exit_code": 0,
            "error": "",
            "mode": "local",
            "cache_note": "cache mode=volume verified",
        }

    monkeypatch.setattr(deep_module, "_run_test_via_sandbox", fake_sandbox)

    before = _before()
    out = run_deep_experiments_node({  # type: ignore[arg-type]
        "depth": "DEEP",
        "head_workspace": str(app),
        "generated_tests_path": str(test_path),
        "output_dir": str(tmp_path / "reports"),
        "job_id": "abcdef01-2345-6789-abcd-ef0123456789",
    })

    # Mutation campaign: one changed source, ten-mutant budget, and the
    # runner it was handed actually swapped and restored the file.
    assert campaign_calls == [("Svc.java", 10)]
    assert runner_results == [(0, "", 0)]
    assert source_path.read_text(encoding="utf-8") == original_source, (
        "the mutation runner must restore the original source after the run"
    )

    # 1 mutation-runner call (the fake campaign invoked the runner) +
    # head run + default 2 stability repeats, all sharing the cache note.
    assert len(sandbox_calls) == 4
    results = out["deep_results"]
    assert results["state_delta"]["head_test_exit"] == 0
    assert results["verdict_stability"] == {"stability": "stable", "runs": 2}
    assert results["cache_integrity"] == "cache mode=volume verified"

    # The artifact is written under the job-scoped name.
    assert results["deep_report_file"] == "deep-report-abcdef01.json"
    report = tmp_path / "reports" / "deep-report-abcdef01.json"
    assert report.is_file()
    assert out["deep_note"].startswith("DEEP experiments completed")
    assert _deltas(before) == _only("completed")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (
        ROOT / "agent" / "nodes" / "run_deep_experiments.py"
    ).read_text(encoding="utf-8")
    literals = set(
        re.findall(
            r'incr\("run_deep_experiments_outcomes_([a-z0-9_]+)_total"\)',
            source,
        )
    )
    assert literals == set(RUN_DEEP_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(RUN_DEEP_OUTCOMES)}"
    )
    assert source.count('incr("run_deep_experiments_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["run_deep_experiments"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(RUN_DEEP_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(RUN_DEEP_OUTCOMES)}"
    )
