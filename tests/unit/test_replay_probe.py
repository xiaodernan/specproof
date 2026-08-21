"""Unit tests for the tier-1b probe-evidence replay (W131).

scripts/bench_replay.py replays probe_differential capsules by re-running
the recorded fault-injection probe test (repo Maven wrapper, H2, local
mode — no Docker) at the recorded base/head refs and comparing the probe
recorder artifacts (target/specproof-probe.json) against the recorded
claim:

- same_conclusion when the replayed artifacts reproduce the recorded
  head-violation claim (note: "probe evidence replayed at head
  (fault-injection probe re-run, H2)");
- replay_failed with the real recorded-vs-actual comparison when they do
  not;
- replay_pending_probe_infra (a named pending class, never a failure)
  when the probe scaffolding genuinely requires Docker/testcontainers.

All tests are offline: synthetic capsules, the Maven runner is stubbed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bench_replay.py"

PROBE_REPLAYED_NOTE = (
    "probe evidence replayed at head (fault-injection probe re-run, H2)"
)


def _load_bench() -> Any:
    """Load scripts/bench_replay.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("bench_replay", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses look the module up in sys.modules.
    sys.modules["bench_replay"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bench() -> Any:
    return _load_bench()


def _write_zip(root: Path, name: str, members: dict[str, str]) -> Path:
    """Write a synthetic capsule zip with the given text members."""
    zip_path = root / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)
    return zip_path


def _unit(bench: Any, zip_path: Path, name: str, head_ref: str = "case-98-head") -> Any:
    return bench.CapsuleUnit(
        name=name,
        zip_path=zip_path,
        dir_path=None,
        store_records=(),
        sha256="",
        base_ref="base",
        head_ref=head_ref,
    )


def _probe_manifest(contract_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """A synthetic probe_differential manifest (canonical digest)."""
    manifest: dict[str, Any] = {
        "finding_id": f"COURT-{contract_id}-PROBE",
        "severity": "MAJOR",
        "confidence": 0.9,
        "created_at": "2026-08-19T00:00:00+00:00",
        "contract_id": contract_id,
        "evidence_type": "probe_differential",
        "evidence_digest": "sha256:" + "e" * 64,
        "db_state_verdict": "",
        "blocker_check": {
            "blocker_conditions": {
                "1_approved_contract": True,
                "2_base_head_execution": False,
                "3_attribution_to_head": False,
                "4_db_behavior_evidence": False,
                "5_capsule_replayable": False,
                "6_confidence_090": True,
            },
            "all_blocker_conditions_met": False,
        },
    }
    if extra:
        manifest.update(extra)
    return manifest


def _probe_finding(
    contract_id: str,
    description: str,
    diff_verdict: str = "REGRESSION",
) -> dict[str, Any]:
    """A synthetic probe_differential finding (real-capsule shape)."""
    return {
        "id": f"COURT-{contract_id}-PROBE",
        "contract_id": contract_id,
        "severity": "MAJOR",
        "type": "differential_regression",
        "description": description,
        "evidence_type": "probe_differential",
        "confidence": 0.9,
        "source": "differential",
        "status": "confirmed",
        "diff_verdict": diff_verdict,
        "db_state_verdict": "",
        "location": "",
        "evidence_digest": "sha256:" + "e" * 64,
        "diff_result_index": 1,
        "base_exit_code": 0,
        "head_exit_code": 0,
        "court_source": "rule_based",
    }


def _probe_capsule_zip(
    bench: Any,
    root: Path,
    name: str,
    contract_id: str,
    description: str,
    head_ref: str = "case-98-head",
    manifest_extra: dict[str, Any] | None = None,
) -> Path:
    """A synthetic probe_differential capsule (canonical-digest manifest)."""
    manifest = _probe_manifest(contract_id, manifest_extra)
    digest = bench.canonical_manifest_digest(manifest)
    manifest["manifest_digest"] = "sha256:" + digest
    finding = _probe_finding(contract_id, description)
    return _write_zip(
        root,
        name,
        {
            "manifest.json": json.dumps(manifest),
            "finding.json": json.dumps(finding),
            "fixtures/base-ref.txt": "base",
            "fixtures/head-ref.txt": head_ref,
        },
    )


def _artifact(
    publish_count: int, outcome: str, timestamps: list[str | None] | None = None,
) -> dict[str, Any]:
    """A valid probe recorder artifact (specproof-probe.json shape)."""
    payloads = [
        {
            "exchange": "specproof.demo.events",
            "routingKey": "event",
            "type": "EmailChangedEvent",
            "timestamp": timestamp,
            "failed": False,
        }
        for timestamp in (timestamps if timestamps is not None else [None] * publish_count)
    ]
    return {
        "probe_version": 1,
        "publish_count": publish_count,
        "outcome": outcome,
        "payloads": payloads,
    }


def _stub_worktree(bench: Any, monkeypatch: Any, probe_java: str) -> Path:
    """Stub the worktree helpers: checkout succeeds, the probe scaffold
    lives under src/test/java/com/specproof/demo/probe."""
    probe_dir = Path("src/test/java/com/specproof/demo/probe")
    monkeypatch.setattr(bench, "checkout_worktree_ref", lambda repo, ref: "")
    monkeypatch.setattr(bench, "_locate_probe_dir", lambda repo: probe_dir)
    monkeypatch.setattr(
        bench,
        "_probe_sources",
        lambda probe_dir_arg, repo: {
            "src/test/java/com/specproof/demo/probe/SpecProofProbeTest.java": probe_java,
        },
    )
    monkeypatch.setattr(bench, "_write_probe_sources", lambda repo, sources: None)
    return probe_dir


def _stub_run_sides(
    bench: Any, monkeypatch: Any, artifacts: list[dict[str, Any] | None],
) -> list[tuple[Path, str]]:
    """Stub _run_probe_side to return the given artifacts in order."""
    calls: list[tuple[Path, str]] = []
    remaining = iter(artifacts)

    def fake(repo: Path, method: str) -> Any:
        calls.append((repo, method))
        artifact = next(remaining)
        return artifact, {
            "exit_code": 0,
            "mode": "local",
            "stdout_tail": "",
            "stderr_tail": "",
            "error": "",
        }

    monkeypatch.setattr(bench, "_run_probe_side", fake)
    return calls


# ── recorded claim extraction ────────────────────────────────────────────


def test_recorded_probe_claim_derived_from_description(
    bench: Any, tmp_path: Path,
) -> None:
    """The real-capsule shape: the claim comes from the finding
    description ("head violates outcome (base profile met)")."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-COURT-EVENT_ONCE-01", "EVENT_ONCE-01",
        "probe artifact comparison: head violates outcome (base profile met)",
    )
    unit = _unit(bench, zip_path, "capsule-COURT-EVENT_ONCE-01")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None and finding is not None
    claim = bench.read_recorded_probe_claim(unit, manifest, finding)
    assert claim is not None
    assert claim["source"] == "finding description"
    assert claim["verdict"] == "REGRESSION"
    assert claim["violated_fields"] == ["outcome"]
    assert claim["test_method"] == "noopEmailChangePublish"


def test_recorded_probe_claim_order_event_publish_count(
    bench: Any, tmp_path: Path,
) -> None:
    """ORDER_EVENT-01 + publish_count maps to brokerFailureRetry."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-COURT-ORDER_EVENT-01", "ORDER_EVENT-01",
        "probe artifact comparison: head violates publish_count (base profile met)",
        head_ref="case-97-head",
    )
    unit = _unit(bench, zip_path, "capsule-COURT-ORDER_EVENT-01", head_ref="case-97-head")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None and finding is not None
    claim = bench.read_recorded_probe_claim(unit, manifest, finding)
    assert claim is not None
    assert claim["violated_fields"] == ["publish_count"]
    assert claim["test_method"] == "brokerFailureRetry"


def test_no_recorded_probe_claim_returns_none(bench: Any, tmp_path: Path) -> None:
    """Nothing recorded to compare against — the claim is not invented."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-NO-CLAIM", "EVENT_ONCE-01",
        "probe artifact comparison",
    )
    unit = _unit(bench, zip_path, "capsule-NO-CLAIM")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None
    assert bench.read_recorded_probe_claim(unit, manifest, finding) is None


# ── task (a): matching recorded-vs-actual → same_conclusion ───────────────


def test_probe_replay_reproduces_recorded_outcome_violation(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """Recorded head violates outcome; the replayed base/head artifacts
    differ on outcome exactly as recorded → same_conclusion."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-COURT-EVENT_ONCE-01", "EVENT_ONCE-01",
        "probe artifact comparison: head violates outcome (base profile met)",
    )
    unit = _unit(bench, zip_path, "capsule-COURT-EVENT_ONCE-01")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None and finding is not None
    probe_java = (
        "package com.specproof.demo.probe;\n"
        "public class SpecProofProbeTest {}\n"
    )
    _stub_worktree(bench, monkeypatch, probe_java)
    calls = _stub_run_sides(
        bench, monkeypatch, [_artifact(0, "success"), _artifact(0, "error")],
    )
    outcome = bench.run_probe_reverification(unit, manifest, finding, tmp_path)
    assert outcome.outcome == "same_conclusion"
    assert PROBE_REPLAYED_NOTE in outcome.reason
    assert "head violates outcome (base profile met)" in outcome.reason
    assert "outcome" in outcome.reason
    assert [call[1] for call in calls] == [
        "noopEmailChangePublish",
        "noopEmailChangePublish",
    ]


def test_explicit_probe_expectation_profile_is_compared(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """An explicitly recorded probe_expectation is compared profile by
    profile: base meets its profile, head violates → same_conclusion."""
    expectation = {
        "probe_version": 1,
        "test_method": "brokerFailureRetry",
        "contract_id": "ORDER_EVENT-01",
        "severity": "BLOCKER",
        "base": {"publish_count": 1},
        "head": {"publish_count": 1},
    }
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-ORDER-EXPLICIT", "ORDER_EVENT-01",
        "probe artifact comparison: head violates publish_count (base profile met)",
        head_ref="case-97-head",
        manifest_extra={"probe_expectation": expectation},
    )
    unit = _unit(bench, zip_path, "capsule-ORDER-EXPLICIT", head_ref="case-97-head")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None and finding is not None
    _stub_worktree(bench, monkeypatch, "package p;\npublic class SpecProofProbeTest {}\n")
    calls = _stub_run_sides(
        bench, monkeypatch, [_artifact(1, "error"), _artifact(2, "success")],
    )
    outcome = bench.run_probe_reverification(unit, manifest, finding, tmp_path)
    assert outcome.outcome == "same_conclusion"
    assert PROBE_REPLAYED_NOTE in outcome.reason
    assert "recorded probe_expectation" in outcome.reason
    assert [call[1] for call in calls] == ["brokerFailureRetry", "brokerFailureRetry"]


# ── task (b): mismatch → replay_failed with the real comparison ───────────


def test_probe_replay_mismatch_is_replay_failed(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """Recorded head violates outcome, but the replayed base and head
    artifacts agree on outcome → replay_failed with the real comparison."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-COURT-EVENT_ONCE-01", "EVENT_ONCE-01",
        "probe artifact comparison: head violates outcome (base profile met)",
    )
    unit = _unit(bench, zip_path, "capsule-COURT-EVENT_ONCE-01")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None and finding is not None
    _stub_worktree(bench, monkeypatch, "package p;\npublic class SpecProofProbeTest {}\n")
    _stub_run_sides(
        bench, monkeypatch, [_artifact(0, "success"), _artifact(0, "success")],
    )
    outcome = bench.run_probe_reverification(unit, manifest, finding, tmp_path)
    assert outcome.outcome == "replay_failed"
    assert "NOT reproduced" in outcome.reason
    assert "head violates outcome (base profile met)" in outcome.reason
    assert "outcome" in outcome.reason
    assert PROBE_REPLAYED_NOTE not in outcome.reason


def test_probe_replay_without_recorded_claim_is_replay_failed(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """No recorded expectation/fields → honest replay_failed, no run."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-NO-CLAIM", "EVENT_ONCE-01",
        "probe artifact comparison",
    )
    unit = _unit(bench, zip_path, "capsule-NO-CLAIM")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None
    monkeypatch.setattr(bench, "checkout_worktree_ref", lambda repo, ref: "")
    outcome = bench.run_probe_reverification(unit, manifest, finding, tmp_path)
    assert outcome.outcome == "replay_failed"
    assert "no recorded probe expectation" in outcome.reason


# ── task (c): pending-infra path ──────────────────────────────────────────


def test_probe_replay_pending_when_scaffolding_needs_docker(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """Probe scaffolding referencing testcontainers cannot be replayed by
    the local Maven wrapper path → replay_pending_probe_infra (a named
    pending class, never a failure)."""
    zip_path = _probe_capsule_zip(
        bench, tmp_path, "capsule-DOCKER-PROBE", "EVENT_ONCE-01",
        "probe artifact comparison: head violates outcome (base profile met)",
    )
    unit = _unit(bench, zip_path, "capsule-DOCKER-PROBE")
    manifest = bench.read_zip_json(zip_path, "manifest.json")
    finding = bench.read_zip_json(zip_path, "finding.json")
    assert manifest is not None and finding is not None
    probe_java = (
        "package com.specproof.demo.probe;\n"
        "import org.testcontainers.containers.RabbitMQContainer;\n"
        "public class SpecProofProbeTest {}\n"
    )
    _stub_worktree(bench, monkeypatch, probe_java)
    run_called = []

    def fail_if_run(repo: Path, method: str) -> Any:  # pragma: no cover - never called
        run_called.append(method)
        return None, {}

    monkeypatch.setattr(bench, "_run_probe_side", fail_if_run)
    outcome = bench.run_probe_reverification(unit, manifest, finding, tmp_path)
    assert outcome.outcome == "replay_pending_probe_infra"
    assert "testcontainers" in outcome.reason
    assert "pending, not a failure" in outcome.reason
    assert run_called == []


# ── routing through run_bench ─────────────────────────────────────────────


def test_run_bench_routes_probe_capsules_to_tier_1b(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """probe_differential capsules take the probe_replay branch of
    run_bench (tier 1b), not the static_reverify branch."""
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    _probe_capsule_zip(
        bench, capsules_dir, "capsule-COURT-EVENT_ONCE-01", "EVENT_ONCE-01",
        "probe artifact comparison: head violates outcome (base profile met)",
    )
    fake_repo = tmp_path / "fake-repo"
    monkeypatch.setattr(
        bench,
        "prepare_temp_worktree",
        lambda repo_root, refs, work_root: {
            "repo": fake_repo,
            "mechanism": "test-stub",
            "refs": {"base": True, "case-98-head": True},
            "error": "",
        },
    )

    def fake_extract(
        python: str, repo_root: Path, zip_path_arg: Path, out_dir: Path,
    ) -> tuple[bool, str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path_arg) as archive:
            manifest_json = json.loads(archive.read("manifest.json"))
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest_json), encoding="utf-8",
        )
        (out_dir / "replay-report.json").write_text("{}", encoding="utf-8")
        return True, "stubbed extract ok"

    monkeypatch.setattr(bench, "extract_via_replay_cli", fake_extract)

    def fake_probe_replay(unit: Any, manifest: Any, finding: Any, repo_dir: Path) -> Any:
        return bench.ReplayOutcome(
            "same_conclusion", PROBE_REPLAYED_NOTE + " — stubbed", None, None, None,
        )

    monkeypatch.setattr(bench, "run_probe_reverification", fake_probe_replay)
    args = bench.build_parser().parse_args(
        [
            "--capsules-dir", str(capsules_dir),
            "--repo", str(tmp_path),
            "--output-json", str(tmp_path / "r.json"),
            "--output-md", str(tmp_path / "r.md"),
        ]
    )
    results = bench.run_bench(args)
    entries = {entry["unit"]: entry for entry in results["capsules"]}
    entry = entries["capsule-COURT-EVENT_ONCE-01"]
    assert entry["outcome"] == "same_conclusion"
    assert entry["replay_mode"] == "probe_replay"
    assert entry["probe_replayed"] is True
    assert entry["static_verified"] is False
    assert results["totals"]["replay_pending_probe_infra"] == 0
    md_text = Path(args.output_md).read_text(encoding="utf-8")
    assert "| replay_pending_probe_infra | 0 |" in md_text
    assert "Tier 1b — probe-evidence replay" in md_text


# ── pure comparison function ──────────────────────────────────────────────


def test_evaluate_probe_replay_derived_and_compliant(bench: Any) -> None:
    """The pure evaluator: derived violation reproduced, derived
    mismatch, explicit profiles compliant."""
    claim = {
        "source": "finding description",
        "verdict": "REGRESSION",
        "violated_fields": ["outcome"],
        "expectation": None,
        "recorded_base": None,
        "recorded_head": None,
        "test_method": "noopEmailChangePublish",
    }
    base = _artifact(0, "success")
    head = _artifact(0, "error")
    assert bench.evaluate_probe_replay(claim, base, head) == ("REGRESSION", [])
    assert bench.evaluate_probe_replay(claim, base, base) == ("NON_REPRODUCIBLE", ["outcome"])
    assert bench.evaluate_probe_replay(claim, None, head) == ("NON_REPRODUCIBLE", [])
    compliant = dict(claim, verdict="COMPLIANT", violated_fields=[])
    expectation = {
        "base": {"publish_count": 1, "outcome": "error"},
        "head": {"publish_count": 1, "outcome": "success"},
        "test_method": "brokerFailureRetry",
    }
    explicit = {**compliant, "expectation": expectation}
    one = _artifact(1, "error")
    two = _artifact(1, "success")
    assert bench.evaluate_probe_replay(explicit, one, two) == ("COMPLIANT", [])
    assert bench.evaluate_probe_replay(explicit, two, two)[0] == "NON_REPRODUCIBLE"

