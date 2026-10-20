"""Batch capsule replay runner tests (Phase 2, P2-2).

The classification is the whole point of this module: an operator reading
"replay failed" learns nothing. These tests pin the four failure classes
(environment / artifact / script / divergence) and the aggregate rules
that must not flatter the evidence:

- the success rate's denominator is the JUDGED count, not the batch size;
- an unjudged capsule is not a failed reproduction;
- a diverged verdict is not a reproduced one;
- one damaged capsule never aborts the batch.

No Docker, no network, no git: the replay seam is injected.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from evidence.batch_replay import (
    OUTCOME_ARTIFACT,
    OUTCOME_DIVERGED,
    OUTCOME_ENVIRONMENT,
    OUTCOME_REPRODUCED,
    OUTCOME_SCRIPT,
    UNJUDGED_OUTCOMES,
    BatchReplayRunner,
    discover_capsules,
    write_batch_record,
)


def _capsule(path: Path, *, severity: str = "MAJOR", finding_id: str = "F-1") -> Path:
    """A minimal but well-formed capsule: manifest.json + run.sh."""
    manifest = {
        "finding_id": finding_id,
        "severity": severity,
        "contract_id": "C-1",
        "manifest_digest": "sha256:deadbeef",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("run.sh", "#!/bin/bash\necho '>> REGRESSION CONFIRMED <<'\n")
    return path


def _replay_returning(payload: dict[str, Any]):
    """A replay_fn stub returning *payload* verbatim."""

    def replay_fn(work_dir: Path, repo: Path, timeout: int) -> dict[str, Any]:
        return dict(payload)

    return replay_fn


_REPLAYED = {
    "status": "replayed",
    "exit_code": 0,
    "stdout_tail": ">> REGRESSION CONFIRMED <<",
    "stderr_tail": "",
    "mode": "docker",
    "error": "",
    "verdict": "regression_confirmed",
}


# ── classification ──────────────────────────────────────────────────────────


class TestClassification:
    def test_matching_verdict_is_reproduced(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_REPRODUCED
        assert outcome.verdict == "regression_confirmed"
        assert outcome.baseline_verdict == "regression_confirmed"
        assert outcome.finding_id == "F-1"
        assert outcome.contract_id == "C-1"

    def test_diverged_verdict_is_not_reproduced(self, tmp_path: Path) -> None:
        """A different verdict family means the evidence is not stable."""
        capsule = _capsule(tmp_path / "c.zip")
        payload = dict(_REPLAYED)
        payload["verdict"] = "compliant"
        runner = BatchReplayRunner(replay_fn=_replay_returning(payload))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_DIVERGED
        assert outcome.outcome != OUTCOME_REPRODUCED
        assert "not stable" in outcome.detail

    def test_clone_failure_is_environment(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        payload = {
            "status": "clone_failed",
            "error": "git clone failed: not a repository",
        }
        runner = BatchReplayRunner(replay_fn=_replay_returning(payload))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_ENVIRONMENT
        assert outcome.verdict is None
        assert "not a repository" in outcome.detail

    def test_sandbox_error_is_environment(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        payload = {
            "status": "replayed",
            "exit_code": -1,
            "error": "docker daemon unreachable",
            "verdict": None,
        }
        runner = BatchReplayRunner(replay_fn=_replay_returning(payload))
        record = runner.run([capsule], tmp_path / "repo")
        assert record.outcomes[0].outcome == OUTCOME_ENVIRONMENT

    def test_timeout_is_environment_not_timeout_verdict(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        payload = {
            "status": "replayed",
            "exit_code": 124,
            "error": "sandbox execution timed out after 900s",
            "verdict": None,
        }
        runner = BatchReplayRunner(replay_fn=_replay_returning(payload))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_ENVIRONMENT
        assert outcome.verdict is None

    def test_markerless_output_is_script_failure(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        payload = {
            "status": "replayed",
            "exit_code": 0,
            "error": "",
            "verdict": None,
        }
        runner = BatchReplayRunner(replay_fn=_replay_returning(payload))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_SCRIPT
        assert "no verdict marker" in outcome.detail

    def test_nonzero_exit_without_verdict_is_script_failure(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        payload = {
            "status": "replayed",
            "exit_code": 1,
            "error": "",
            "verdict": None,
        }
        runner = BatchReplayRunner(replay_fn=_replay_returning(payload))
        record = runner.run([capsule], tmp_path / "repo")
        assert record.outcomes[0].outcome == OUTCOME_SCRIPT

    def test_manifest_without_severity_has_no_baseline(self, tmp_path: Path) -> None:
        """No baseline means "cannot compare" — never silently "reproduced"."""
        capsule = _capsule(tmp_path / "c.zip", severity="")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_SCRIPT
        assert outcome.baseline_verdict is None
        assert "no baseline" in outcome.detail

    def test_replay_exception_does_not_abort_the_batch(self, tmp_path: Path) -> None:
        """One exploding capsule must not take the population down with it."""
        good = _capsule(tmp_path / "good.zip", finding_id="F-good")
        bad = _capsule(tmp_path / "bad.zip", finding_id="F-bad")

        def replay_fn(work_dir: Path, repo: Path, timeout: int) -> dict[str, Any]:
            if "bad" in str(work_dir):
                raise RuntimeError("sandbox exploded")
            return dict(_REPLAYED)

        runner = BatchReplayRunner(replay_fn=replay_fn)
        record = runner.run([bad, good], tmp_path / "repo")
        assert len(record.outcomes) == 2
        assert record.outcomes[0].outcome == OUTCOME_ENVIRONMENT
        assert record.outcomes[1].outcome == OUTCOME_REPRODUCED


# ── artifact failures ──────────────────────────────────────────────────────


class TestArtifactFailures:
    def test_missing_capsule_is_artifact_failure(self, tmp_path: Path) -> None:
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([tmp_path / "nope.zip"], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_ARTIFACT
        assert "not found" in outcome.detail

    def test_non_zip_is_artifact_failure(self, tmp_path: Path) -> None:
        capsule = tmp_path / "c.tar"
        capsule.write_text("not a zip", encoding="utf-8")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        assert record.outcomes[0].outcome == OUTCOME_ARTIFACT

    def test_corrupt_zip_is_artifact_failure(self, tmp_path: Path) -> None:
        capsule = tmp_path / "c.zip"
        capsule.write_bytes(b"PK\x03\x04 not really a zip")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        assert record.outcomes[0].outcome == OUTCOME_ARTIFACT

    def test_capsule_without_manifest_is_artifact_failure(self, tmp_path: Path) -> None:
        capsule = tmp_path / "c.zip"
        with zipfile.ZipFile(capsule, "w") as archive:
            archive.writestr("run.sh", "#!/bin/bash\ntrue\n")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        outcome = record.outcomes[0]
        assert outcome.outcome == OUTCOME_ARTIFACT
        assert "manifest.json" in outcome.detail

    def test_unreadable_manifest_is_artifact_failure(self, tmp_path: Path) -> None:
        capsule = tmp_path / "c.zip"
        with zipfile.ZipFile(capsule, "w") as archive:
            archive.writestr("manifest.json", "{not json")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        assert record.outcomes[0].outcome == OUTCOME_ARTIFACT


# ── aggregates ──────────────────────────────────────────────────────────────


class TestAggregates:
    def test_success_rate_uses_the_judged_denominator(self, tmp_path: Path) -> None:
        """3 judged (2 reproduced, 1 diverged) + 1 environment failure.

        The rate is 2/3 — the environment failure was never judged and must
        not be counted as a failed reproduction.
        """
        capsules = [_capsule(tmp_path / f"c{i}.zip", finding_id=f"F-{i}") for i in range(4)]
        calls = {"n": 0}

        def replay_fn(work_dir: Path, repo: Path, timeout: int) -> dict[str, Any]:
            calls["n"] += 1
            if calls["n"] == 4:
                return {"status": "clone_failed", "error": "boom"}
            if calls["n"] == 3:
                payload = dict(_REPLAYED)
                payload["verdict"] = "compliant"
                return payload
            return dict(_REPLAYED)

        runner = BatchReplayRunner(replay_fn=replay_fn)
        record = runner.run(capsules, tmp_path / "repo")
        assert record.replayed_count() == 3
        assert record.unjudged_count() == 1
        assert record.success_rate() == pytest.approx(2 / 3)

    def test_success_rate_is_none_when_nothing_was_judged(self, tmp_path: Path) -> None:
        """0/1 because the sandbox was down is a lie — the rate is unknown."""
        capsule = _capsule(tmp_path / "c.zip")
        runner = BatchReplayRunner(
            replay_fn=_replay_returning({"status": "clone_failed", "error": "down"})
        )
        record = runner.run([capsule], tmp_path / "repo")
        assert record.replayed_count() == 0
        assert record.success_rate() is None

    def test_by_outcome_lists_every_key(self, tmp_path: Path) -> None:
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([], tmp_path / "repo")
        counts = record.by_outcome()
        assert counts[OUTCOME_REPRODUCED] == 0
        assert set(counts) >= set(UNJUDGED_OUTCOMES)

    def test_unjudged_outcomes_are_exactly_environment_and_artifact(self) -> None:
        assert {OUTCOME_ENVIRONMENT, OUTCOME_ARTIFACT} == UNJUDGED_OUTCOMES

    def test_record_serializes_to_json(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        payload = record.to_dict()
        assert payload["total"] == 1
        assert payload["judged"] == 1
        assert payload["unjudged"] == 0
        assert payload["success_rate"] == 1.0
        assert payload["by_outcome"][OUTCOME_REPRODUCED] == 1
        assert payload["finished_at"]

    def test_write_batch_record_writes_readable_json(self, tmp_path: Path) -> None:
        capsule = _capsule(tmp_path / "c.zip")
        runner = BatchReplayRunner(replay_fn=_replay_returning(_REPLAYED))
        record = runner.run([capsule], tmp_path / "repo")
        out = tmp_path / "out" / "batch-replay-report.json"
        written = write_batch_record(record, out)
        assert Path(written) == out
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded["total"] == 1
        assert loaded["outcomes"][0]["outcome"] == OUTCOME_REPRODUCED


# ── discovery ──────────────────────────────────────────────────────────────


def test_discover_capsules_finds_every_zip_in_deterministic_path_order(
    tmp_path: Path,
) -> None:
    """The order is the sorted PATH order, so a batch is reproducible.

    Sorting by full path (not by file name) is what makes the order stable
    across machines: two capsules in different directories keep their
    directory relationship instead of interleaving by name.
    """
    (tmp_path / "b").mkdir()
    second = _capsule(tmp_path / "b" / "second.zip")
    first = _capsule(tmp_path / "first.zip")
    (tmp_path / "notazip.txt").write_text("x", encoding="utf-8")
    found = discover_capsules(tmp_path)
    assert found == sorted([second, first])
    # Same input, same order — twice.
    assert discover_capsules(tmp_path) == found


def test_discover_capsules_on_missing_dir_is_empty(tmp_path: Path) -> None:
    assert discover_capsules(tmp_path / "nope") == []
