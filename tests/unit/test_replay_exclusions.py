"""Unit tests for the replay gate-denominator exclusions (W128).

scripts/bench_replay.py classifies three of the 28 enumerated capsules as
excluded (not verification findings) instead of counting them as
evidence_inconsistent:

- excluded_demo_seed: capsule.json declares demo:true — seed demo data
  written by scripts/seed_demo.py (capsule.json/REPLAY.md/reproduce.ps1
  only, no manifest.json by design);
- excluded_stale_artifact: the recorded manifest_digest equals the sha256
  of the pre-canonical pretty-printed manifest (json.dumps(indent=2,
  sort_keys=True), digest field excluded) while the canonical recompute
  differs — the zip predates the canonical digest rule.

Excluded capsules never enter the gate denominator:
success rate = verified / (enumerated - excluded), with both denominators
printed in the JSON totals and the markdown summary. All tests are
offline: synthetic zips, no Docker/git/Maven.
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

DEMO_SEED_REASON = (
    "demo seed capsule (scripts/seed_demo.py, 非验证发现胶囊) "
    "— excluded from the replay gate denominator"
)
STALE_ARTIFACT_REASON = (
    "pre-canonical digest era artifact (built before the canonical manifest rule) "
    "— excluded from the replay gate denominator"
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


def _unit(bench: Any, zip_path: Path, name: str) -> Any:
    return bench.CapsuleUnit(
        name=name,
        zip_path=zip_path,
        dir_path=None,
        store_records=(),
        sha256="",
        base_ref="base",
        head_ref="head-v1",
    )


def _manifest() -> dict[str, Any]:
    """A synthetic manifest (nested, so ordering matters for digests)."""
    return {
        "finding_id": "COURT-DIFF-01",
        "severity": "MAJOR",
        "confidence": 0.9,
        "created_at": "2026-08-17T00:00:00+00:00",
        "contract_id": "DIFF-01",
        "evidence_type": "base_pass_head_fail",
        "evidence_digest": "sha256:" + "e" * 64,
        "db_state_verdict": "",
        "blocker_check": {
            "blocker_conditions": {
                "1_approved_contract": True,
                "2_base_head_execution": True,
                "3_attribution_to_head": True,
                "4_db_behavior_evidence": True,
                "5_capsule_replayable": True,
                "6_confidence_090": True,
            },
            "all_blocker_conditions_met": True,
        },
    }


def _demo_capsule_zip(root: Path, name: str, demo_value: bool) -> Path:
    capsule_json = json.dumps(
        {
            "demo": demo_value,
            "job_id": "4ccc31dc-c945-5386-bcd2-997a1f9fa957",
            "contract_id": "AUTH-01",
            "severity": "BLOCKER",
            "note": "演示胶囊 — 由 scripts/seed_demo.py 生成, 未经过真实差分执行",
        },
        ensure_ascii=False,
    )
    return _write_zip(
        root,
        name,
        {"capsule.json": capsule_json, "REPLAY.md": "seed demo", "reproduce.ps1": ""},
    )


def _runtime_capsule_zip(bench: Any, root: Path, name: str) -> Path:
    """A canonical-digest runtime capsule that replays to REGRESSION CONFIRMED."""
    manifest = _manifest()
    digest = bench.canonical_manifest_digest(manifest)
    manifest["manifest_digest"] = "sha256:" + digest
    return _write_zip(
        root,
        name,
        {
            "manifest.json": json.dumps(manifest),
            "finding.json": json.dumps(
                {
                    "id": "RUN-01",
                    "contract_id": "DIFF-01",
                    "severity": "MAJOR",
                    "type": "differential_regression",
                    "description": "synthetic runtime capsule",
                    "evidence_type": "base_pass_head_fail",
                    "evidence_digest": "sha256:" + "e" * 64,
                    "status": "confirmed",
                }
            ),
            "fixtures/base-ref.txt": "base",
            "fixtures/head-ref.txt": "head-v1",
            "run.ps1": "param([string]$RepoDir)\n"
            "Write-Host '  Base test exit code: 0'\n"
            "Write-Host '  Head test exit code: 1'\n"
            "Write-Host '  >> REGRESSION CONFIRMED <<'\n",
        },
    )


# ── excluded_demo_seed ─────────────────────────────────────────────────────


def test_demo_true_capsule_is_excluded(bench: Any, tmp_path: Path) -> None:
    """Task (a): demo:true in capsule.json -> excluded_demo_seed + reason."""
    zip_path = _demo_capsule_zip(tmp_path, "capsule-4ccc31dc-AUTH-01", demo_value=True)
    unit = _unit(bench, zip_path, "capsule-4ccc31dc-AUTH-01")
    classified = bench.classify_exclusion(unit)
    assert classified is not None
    name, reason = classified
    assert name == "excluded_demo_seed"
    assert reason == DEMO_SEED_REASON
    # The verbatim reason constants are the single source of truth.
    assert bench.EXCLUDED_REASONS["excluded_demo_seed"] == DEMO_SEED_REASON


def test_demo_false_capsule_is_not_excluded(bench: Any, tmp_path: Path) -> None:
    """demo:false must not trigger the demo-seed exclusion."""
    zip_path = _demo_capsule_zip(tmp_path, "capsule-NOT-DEMO", demo_value=False)
    unit = _unit(bench, zip_path, "capsule-NOT-DEMO")
    assert bench.classify_exclusion(unit) is None


# ── excluded_stale_artifact ────────────────────────────────────────────────


def test_pretty_printed_digest_capsule_is_excluded(bench: Any, tmp_path: Path) -> None:
    """Task (b): recorded == pretty-printed digest and != canonical -> stale."""
    manifest = _manifest()
    pretty = bench.pretty_manifest_digest(manifest)
    canonical = bench.canonical_manifest_digest(manifest)
    assert pretty != canonical  # different serializations, different digests
    manifest["manifest_digest"] = "sha256:" + pretty
    zip_path = _write_zip(
        tmp_path, "capsule-COURT-DIFF-01", {"manifest.json": json.dumps(manifest)}
    )
    unit = _unit(bench, zip_path, "capsule-COURT-DIFF-01")
    classified = bench.classify_exclusion(unit)
    assert classified is not None
    name, reason = classified
    assert name == "excluded_stale_artifact"
    assert reason == STALE_ARTIFACT_REASON
    assert bench.EXCLUDED_REASONS["excluded_stale_artifact"] == STALE_ARTIFACT_REASON


def test_canonical_digest_capsule_is_not_excluded(
    bench: Any, tmp_path: Path,
) -> None:
    """Task (c): a canonical-digest capsule keeps its normal path (no regression)."""
    manifest = _manifest()
    digest = bench.canonical_manifest_digest(manifest)
    manifest["manifest_digest"] = "sha256:" + digest
    zip_path = _write_zip(
        tmp_path, "capsule-CANONICAL-01", {"manifest.json": json.dumps(manifest)}
    )
    unit = _unit(bench, zip_path, "capsule-CANONICAL-01")
    assert bench.classify_exclusion(unit) is None


def test_neither_digest_rule_capsule_is_not_excluded(
    bench: Any, tmp_path: Path,
) -> None:
    """A recorded digest matching neither rule stays in the normal buckets."""
    manifest = _manifest()
    manifest["manifest_digest"] = "sha256:" + "a" * 64
    zip_path = _write_zip(
        tmp_path, "capsule-TAMPER-01", {"manifest.json": json.dumps(manifest)}
    )
    unit = _unit(bench, zip_path, "capsule-TAMPER-01")
    assert bench.classify_exclusion(unit) is None


def test_missing_manifest_is_not_a_demo_exclusion(bench: Any, tmp_path: Path) -> None:
    """No capsule.json and no manifest -> not excluded (plain evidence gate)."""
    zip_path = _write_zip(
        tmp_path, "capsule-NOTHING-01", {"REPLAY.md": "nothing here"}
    )
    unit = _unit(bench, zip_path, "capsule-NOTHING-01")
    assert bench.classify_exclusion(unit) is None


# ── end-to-end summary math: both denominators ─────────────────────────────


def test_run_bench_exclusions_and_denominator_math(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    """Task (d): success rate = verified / (enumerated - excluded), both
    denominators printed in the JSON and the markdown."""
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    _demo_capsule_zip(capsules_dir, "capsule-DEMO-01", demo_value=True)
    stale_manifest = _manifest()
    stale_manifest["manifest_digest"] = "sha256:" + bench.pretty_manifest_digest(
        stale_manifest
    )
    _write_zip(
        capsules_dir,
        "capsule-STALE-01",
        {"manifest.json": json.dumps(stale_manifest)},
    )
    _runtime_capsule_zip(bench, capsules_dir, "capsule-RUN-01")

    fake_repo = tmp_path / "fake-repo"
    monkeypatch.setattr(
        bench,
        "prepare_temp_worktree",
        lambda repo_root, refs, work_root: {
            "repo": fake_repo,
            "mechanism": "test-stub",
            "refs": {"base": True, "head-v1": True},
            "error": "",
        },
    )

    def fake_extract(
        python: str, repo_root: Path, zip_path: Path, out_dir: Path,
    ) -> tuple[bool, str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            manifest_json = json.loads(archive.read("manifest.json"))
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest_json), encoding="utf-8",
        )
        (out_dir / "replay-report.json").write_text("{}", encoding="utf-8")
        return True, "stubbed extract ok"

    monkeypatch.setattr(bench, "extract_via_replay_cli", fake_extract)

    def fake_execute(extracted_dir: Path, repo: Path, timeout: float) -> Any:
        return bench.RunResult(
            exit_code=0,
            stdout=(
                "  Base test exit code: 0\n"
                "  Head test exit code: 1\n"
                "  >> REGRESSION CONFIRMED <<\n"
            ),
            stderr="", timed_out=False, error="",
        )

    monkeypatch.setattr(bench, "execute_run_script", fake_execute)
    args = bench.build_parser().parse_args(
        [
            "--capsules-dir", str(capsules_dir),
            "--repo", str(tmp_path),
            "--output-json", str(tmp_path / "r.json"),
            "--output-md", str(tmp_path / "r.md"),
        ]
    )
    results = bench.run_bench(args)
    totals = results["totals"]
    assert totals["enumerated"] == 3
    assert totals["excluded"] == 2
    assert totals["excluded_demo_seed"] == 1
    assert totals["excluded_stale_artifact"] == 1
    # The demo seed has no manifest.json, yet it is excluded before the
    # evidence gate: nothing counts as evidence_inconsistent.
    assert totals["evidence_inconsistent"] == 0
    assert totals["same_conclusion"] == 1
    assert totals["verified"] == 1
    assert totals["gate_denominator"] == 1
    assert totals["success_rate"] == 1.0
    assert totals["gate_replay_success_rate_095"] is True

    entries = {entry["unit"]: entry for entry in results["capsules"]}
    demo_entry = entries["capsule-DEMO-01"]
    assert demo_entry["outcome"] == "excluded"
    assert demo_entry["classification"] == "excluded_demo_seed"
    assert demo_entry["reason"] == DEMO_SEED_REASON
    assert demo_entry["evidence_problems"] == []
    stale_entry = entries["capsule-STALE-01"]
    assert stale_entry["outcome"] == "excluded"
    assert stale_entry["classification"] == "excluded_stale_artifact"
    assert stale_entry["reason"] == STALE_ARTIFACT_REASON
    assert stale_entry["evidence_problems"] == []
    run_entry = entries["capsule-RUN-01"]
    assert run_entry["outcome"] == "same_conclusion"
    assert run_entry["classification"] == "same_conclusion"

    md_text = Path(args.output_md).read_text(encoding="utf-8")
    assert "| capsules enumerated | 3 |" in md_text
    assert "| excluded capsules (NOT in the gate denominator) | 2 |" in md_text
    assert "| - excluded_demo_seed | 1 |" in md_text
    assert "| - excluded_stale_artifact | 1 |" in md_text
    assert "| gate denominator (enumerated − excluded) | 1 |" in md_text
    assert "**success rate (verified / (enumerated − excluded))**" in md_text
    assert "## Exclusion definitions (gate note, verbatim)" in md_text
    assert DEMO_SEED_REASON in md_text
    assert STALE_ARTIFACT_REASON in md_text
    assert "| capsule-DEMO-01 " in md_text
    assert "| excluded_demo_seed " in md_text

    written = json.loads(Path(args.output_json).read_text(encoding="utf-8"))
    written_totals = written["totals"]
    assert written_totals["enumerated"] == 3
    assert written_totals["excluded"] == 2
    assert written_totals["gate_denominator"] == 1
    assert written_totals["verified"] == 1
    assert written["exclusions"]["excluded_demo_seed"]["reason"] == DEMO_SEED_REASON
    assert written["exclusions"]["excluded_stale_artifact"]["reason"] == STALE_ARTIFACT_REASON
    for record in written["capsules"]:
        assert "classification" in record
