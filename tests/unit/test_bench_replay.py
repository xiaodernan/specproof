"""Unit tests for scripts/bench_replay.py (synthetic capsules, no Docker).

These tests exercise the pure classification/enumeration/evidence logic and
one end-to-end batch run whose worktree preparation, replay CLI extraction
and run-script execution are stubbed — so the batch runner is verified
offline without Docker, git worktrees or Maven.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from storage.object_metadata import (
    InMemoryObjectMetadataStore,
    new_metadata,
    payload_sha256_of_file,
)

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bench_replay.py"


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


def _make_capsule_zip(
    root: Path,
    name: str,
    *,
    b2: bool,
    verdict: str,
    with_manifest: bool = True,
    manifest_overrides: dict[str, Any] | None = None,
    finding_evidence: str | None = None,
) -> Path:
    """A synthetic capsule zip whose manifest_digest follows create_capsule's rule."""
    bench_module = _load_bench()
    manifest: dict[str, Any] = {
        "finding_id": name.replace("capsule-", ""),
        "severity": "MAJOR",
        "confidence": 0.85,
        "contract_id": "AUTH-01",
        "evidence_type": "base_pass_head_fail" if b2 else "java_source_diff",
        "evidence_digest": "sha256:" + "e" * 64,
        "blocker_check": {
            "blocker_conditions": {
                "1_approved_contract": True,
                "2_base_head_execution": b2,
                "3_attribution_to_head": True,
                "4_db_behavior_evidence": False,
                "5_capsule_replayable": b2,
                "6_confidence_090": False,
            },
            "all_blocker_conditions_met": False,
        },
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    digest = bench_module.canonical_manifest_digest(manifest)
    manifest["manifest_digest"] = "sha256:" + digest
    finding = {
        "id": manifest["finding_id"],
        "contract_id": "AUTH-01",
        "severity": "MAJOR",
        "type": "synthetic_regression",
        "description": "synthetic capsule fixture (no Docker)",
        "evidence_type": manifest["evidence_type"],
        "evidence_digest": finding_evidence or manifest["evidence_digest"],
        "status": "confirmed",
    }
    run_ps1 = (
        "param([string]$RepoDir = $env:SPECPROOF_REPO)\n"
        "Write-Host '  Base test exit code: 0'\n"
        "Write-Host '  Head test exit code: 1'\n"
        f"Write-Host '  >> {verdict} <<'\n"
    )
    zip_path = root / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        if with_manifest:
            archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("finding.json", json.dumps(finding))
        archive.writestr("requirement.json", json.dumps({"text": "synthetic"}))
        archive.writestr("fixtures/base-ref.txt", "base")
        archive.writestr("fixtures/head-ref.txt", "head-v1")
        archive.writestr(
            "generated-tests/SpecProofGeneratedTest.java",
            "package com.specproof.demo;\n",
        )
        archive.writestr("run.ps1", run_ps1)
        archive.writestr("run.sh", "#!/bin/bash\necho '>> COMPLIANT <<'\n")
    return zip_path


def _unit(bench: Any, capsules_dir: Path, name: str) -> Any:
    units, _inventory = bench.enumerate_capsules(capsules_dir, None)
    for unit in units:
        if unit.name == name:
            return unit
    pytest.fail(f"unit {name} not enumerated")


def _run(bench: Any, stdout: str, exit_code: int = 0, **overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "exit_code": exit_code, "stdout": stdout, "stderr": "",
        "timed_out": False, "error": "",
    }
    fields.update(overrides)
    return bench.RunResult(**fields)


# ── evidence verification ──────────────────────────────────────────────────


def test_canonical_manifest_digest_matches_recorded(bench: Any, tmp_path: Path) -> None:
    zip_path = _make_capsule_zip(
        tmp_path, "capsule-TEST-01", b2=True, verdict="REGRESSION CONFIRMED"
    )
    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert bench.canonical_manifest_digest(manifest) == manifest["manifest_digest"][7:]
    unit = _unit(bench, tmp_path, "capsule-TEST-01")
    assert not bench.verify_evidence(unit).inconsistent


def test_tampered_manifest_digest_detected(bench: Any, tmp_path: Path) -> None:
    zip_path = _make_capsule_zip(
        tmp_path, "capsule-TAMPER", b2=True, verdict="REGRESSION CONFIRMED"
    )
    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    manifest["severity"] = "BLOCKER"  # tamper after recording
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("finding.json", json.dumps({"evidence_digest": "sha256:" + "e" * 64}))
    unit = _unit(bench, tmp_path, "capsule-TAMPER")
    problems = bench.verify_evidence(unit).problems
    assert any("manifest_digest mismatch" in problem for problem in problems)


def test_missing_manifest_detected(bench: Any, tmp_path: Path) -> None:
    _make_capsule_zip(
        tmp_path, "capsule-NOMANIFEST", b2=True, verdict="REGRESSION CONFIRMED",
        with_manifest=False,
    )
    unit = _unit(bench, tmp_path, "capsule-NOMANIFEST")
    problems = bench.verify_evidence(unit).problems
    assert any("manifest.json missing" in problem for problem in problems)


def test_evidence_digest_disagreement_detected(bench: Any, tmp_path: Path) -> None:
    _make_capsule_zip(
        tmp_path, "capsule-DIGESTMIX", b2=True, verdict="REGRESSION CONFIRMED",
        finding_evidence="sha256:" + "f" * 64,
    )
    unit = _unit(bench, tmp_path, "capsule-DIGESTMIX")
    problems = bench.verify_evidence(unit).problems
    assert any("evidence_digest disagreement" in problem for problem in problems)


def test_store_payload_digest_mismatch_detected(bench: Any, tmp_path: Path) -> None:
    zip_path = _make_capsule_zip(
        tmp_path, "capsule-STOREMIX", b2=True, verdict="REGRESSION CONFIRMED"
    )
    store = InMemoryObjectMetadataStore()
    store.record(
        new_metadata(
            "capsule",
            {"payload_sha256": "a" * 64},  # not the zip's real digest
            path_hint=str(zip_path),
        )
    )
    units, _inventory = bench.enumerate_capsules(tmp_path, store)
    matched = next(u for u in units if u.name == "capsule-STOREMIX")
    assert matched.store_records == ()


def test_store_digest_match_verifies(bench: Any, tmp_path: Path) -> None:
    zip_path = _make_capsule_zip(
        tmp_path, "capsule-STOREOK", b2=True, verdict="REGRESSION CONFIRMED"
    )
    store = InMemoryObjectMetadataStore()
    store.record(
        new_metadata(
            "capsule",
            {"payload_sha256": payload_sha256_of_file(zip_path)},
            path_hint=str(zip_path),
        )
    )
    units, _inventory = bench.enumerate_capsules(tmp_path, store)
    matched = next(u for u in units if u.name == "capsule-STOREOK")
    assert len(matched.store_records) == 1
    assert not bench.verify_evidence(matched).inconsistent


def test_dir_manifest_mismatch_detected(bench: Any, tmp_path: Path) -> None:
    _make_capsule_zip(tmp_path, "capsule-DIRMIX", b2=True, verdict="REGRESSION CONFIRMED")
    dir_path = tmp_path / "capsule-DIRMIX"
    dir_path.mkdir()
    (dir_path / "manifest.json").write_text(
        json.dumps({"finding_id": "DIRMIX", "severity": "BLOCKER"}), encoding="utf-8"
    )
    unit = _unit(bench, tmp_path, "capsule-DIRMIX")
    problems = bench.verify_evidence(unit).problems
    assert any("directory manifest differs" in problem for problem in problems)


def test_dir_only_unit_is_inconsistent(bench: Any, tmp_path: Path) -> None:
    dir_path = tmp_path / "capsule-DIRONLY"
    dir_path.mkdir()
    (dir_path / "manifest.json").write_text("{}", encoding="utf-8")
    units, _inventory = bench.enumerate_capsules(tmp_path, None)
    assert len(units) == 1
    problems = bench.verify_evidence(units[0]).problems
    assert any("no capsule .zip payload" in problem for problem in problems)


# ── enumeration + store inventory ──────────────────────────────────────────


def test_enumeration_joins_store_records_by_digest(bench: Any, tmp_path: Path) -> None:
    zip_path = _make_capsule_zip(
        tmp_path, "capsule-JOINED", b2=True, verdict="REGRESSION CONFIRMED"
    )
    store = InMemoryObjectMetadataStore()
    store.record(
        new_metadata(
            "capsule",
            {"payload_sha256": payload_sha256_of_file(zip_path)},
            path_hint=str(zip_path),
        )
    )
    units, inventory = bench.enumerate_capsules(tmp_path, store)
    unit = next(u for u in units if u.name == "capsule-JOINED")
    assert len(unit.store_records) == 1
    assert inventory["capsule_records_total"] == 1
    assert inventory["joined_to_zip_digests"] == 1
    assert inventory["this_repo_paths"] == 1


def test_store_inventory_counts_other_repo_and_orphan(bench: Any, tmp_path: Path) -> None:
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    _make_capsule_zip(capsules_dir, "capsule-INV", b2=True, verdict="REGRESSION CONFIRMED")
    other_zip = tmp_path / "elsewhere" / "capsule-X.zip"
    other_zip.parent.mkdir(parents=True)
    other_zip.write_bytes(b"other repo capsule")
    store = InMemoryObjectMetadataStore()
    store.record(
        new_metadata(
            "capsule", {"payload_sha256": "a" * 64},
            path_hint=str(other_zip),
        )
    )
    store.record(
        new_metadata(
            "capsule", {"payload_sha256": "b" * 64},
            path_hint=str(tmp_path / "gone.zip"),
        )
    )
    _units, inventory = bench.enumerate_capsules(capsules_dir, store)
    assert inventory["capsule_records_total"] == 2
    assert inventory["other_repo_paths"] == 1
    assert inventory["orphan_paths"] == 1


# ── verdict / exit-code parsing ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("  >> REGRESSION CONFIRMED <<", "REGRESSION CONFIRMED"),
        ("  >> UNEXPECTED FIX <<", "UNEXPECTED FIX"),
        ("  >> AMBIGUOUS <<", "AMBIGUOUS"),
        ("  >> COMPLIANT <<", "COMPLIANT"),
        ("no verdict here", None),
    ],
)
def test_parse_verdict(bench: Any, output: str, expected: str | None) -> None:
    assert bench.parse_verdict(output) == expected


def test_parse_exit_codes(bench: Any) -> None:
    output = "  Base test exit code: 0\n  Head test exit code: 1\n"
    assert bench.parse_exit_codes(output) == (0, 1)


# ── classification ─────────────────────────────────────────────────────────


def test_classify_confirmed_reproduces_runtime_claim(bench: Any) -> None:
    run = _run(
        bench,
        "  Base test exit code: 0\n  Head test exit code: 1\n  >> REGRESSION CONFIRMED <<",
    )
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "same_conclusion"
    assert outcome.verdict == "REGRESSION CONFIRMED"
    assert (outcome.base_exit, outcome.head_exit) == (0, 1)


def test_classify_compliant_contradicts_runtime_claim(bench: Any) -> None:
    run = _run(
        bench,
        "  Base test exit code: 0\n  Head test exit code: 0\n  >> COMPLIANT <<",
    )
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "replay_failed"
    assert "NOT reproduced" in outcome.reason
    assert outcome.verdict == "COMPLIANT"


def test_classify_confirmed_strengthens_static_claim(bench: Any) -> None:
    run = _run(
        bench,
        "  Base test exit code: 0\n  Head test exit code: 1\n  >> REGRESSION CONFIRMED <<",
    )
    outcome = bench.classify_replay(bench.NO_RUNTIME_CLAIM, run)
    assert outcome.outcome == "same_conclusion"
    assert "stronger evidence" in outcome.reason


def test_classify_compliant_does_not_reproduce_static_claim(bench: Any) -> None:
    run = _run(
        bench,
        "  Base test exit code: 0\n  Head test exit code: 0\n  >> COMPLIANT <<",
    )
    outcome = bench.classify_replay(bench.NO_RUNTIME_CLAIM, run)
    assert outcome.outcome == "replay_failed"


def test_classify_env_pattern_wins_over_ambiguous_verdict(bench: Any) -> None:
    run = _run(
        bench,
        "ERROR: Java not found\n  Base test exit code: 1\n  Head test exit code: 1\n"
        "  >> AMBIGUOUS <<",
    )
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "env_mismatch"
    assert "Java is not installed" in outcome.reason
    assert outcome.verdict == "AMBIGUOUS"


def test_classify_no_verdict_nonzero_exit(bench: Any) -> None:
    run = _run(bench, "some failure output", exit_code=1)
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "replay_failed"
    assert "exited 1 without a verdict" in outcome.reason


def test_classify_timeout(bench: Any) -> None:
    run = _run(bench, "", timed_out=True)
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "replay_failed"
    assert "timed out" in outcome.reason


def test_classify_executor_missing_is_env_mismatch(bench: Any) -> None:
    run = _run(bench, "", error="no pwsh/bash executor available for the capsule run script")
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "env_mismatch"
    assert "no pwsh/bash executor" in outcome.reason


# ── end-to-end batch run with stubbed execution (no Docker / git / Maven) ──


@pytest.fixture()
def bench_args(tmp_path: Path) -> argparse.Namespace:
    bench_module = _load_bench()
    return bench_module.build_parser().parse_args(
        [
            "--capsules-dir", str(tmp_path / "capsules"),
            "--repo", str(tmp_path / "repo"),
            "--output-json", str(tmp_path / "out" / "replay-results.json"),
            "--output-md", str(tmp_path / "out" / "replay-results.md"),
            "--timeout", "60",
        ]
    )


def _stub_worktree(repo: Path) -> dict[str, Any]:
    return {
        "repo": repo,
        "mechanism": "test-stub",
        "refs": {"base": True, "head-v1": True},
        "error": "",
    }


def test_run_bench_end_to_end_with_stubs(
    bench: Any, tmp_path: Path, monkeypatch: Any, bench_args: argparse.Namespace,
) -> None:
    capsules_dir = Path(bench_args.capsules_dir)
    capsules_dir.mkdir(parents=True)
    _make_capsule_zip(capsules_dir, "capsule-OK-01", b2=True, verdict="REGRESSION CONFIRMED")
    _make_capsule_zip(capsules_dir, "capsule-BAD-01", b2=True, verdict="COMPLIANT")

    fake_repo = tmp_path / "fake-repo"
    monkeypatch.setattr(
        bench, "prepare_temp_worktree",
        lambda repo_root, refs, work_root: _stub_worktree(fake_repo),
    )

    def fake_extract(
        python: str, repo_root: Path, zip_path: Path, out_dir: Path,
    ) -> tuple[bool, str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (out_dir / "replay-report.json").write_text("{}", encoding="utf-8")
        return True, "stubbed extract ok"

    monkeypatch.setattr(bench, "extract_via_replay_cli", fake_extract)

    def fake_execute(extracted_dir: Path, repo: Path, timeout: float) -> Any:
        verdict = "COMPLIANT" if extracted_dir.name == "capsule-BAD-01" else "REGRESSION CONFIRMED"
        head_exit = "0" if verdict == "COMPLIANT" else "1"
        stdout = (
            "  Base test exit code: 0\n"
            f"  Head test exit code: {head_exit}\n"
            f"  >> {verdict} <<\n"
        )
        return bench.RunResult(exit_code=0, stdout=stdout, stderr="", timed_out=False, error="")

    monkeypatch.setattr(bench, "execute_run_script", fake_execute)

    results = bench.run_bench(bench_args)
    totals = results["totals"]
    assert totals["enumerated"] == 2
    assert totals["same_conclusion"] == 1
    assert totals["replay_failed"] == 1
    assert totals["env_mismatch"] == 0
    assert totals["evidence_inconsistent"] == 0
    assert totals["success_rate"] == pytest.approx(0.5)
    assert totals["gate_replay_success_rate_095"] is False
    outcomes = {entry["unit"]: entry["outcome"] for entry in results["capsules"]}
    assert outcomes["capsule-OK-01"] == "same_conclusion"
    assert outcomes["capsule-BAD-01"] == "replay_failed"
    json_path = Path(bench_args.output_json)
    md_path = Path(bench_args.output_md)
    assert json_path.exists()
    assert md_path.exists()
    written = json.loads(json_path.read_text(encoding="utf-8"))
    assert written["totals"]["success_rate"] == pytest.approx(0.5)
    md_text = md_path.read_text(encoding="utf-8")
    assert "## Replay success rate" in md_text


def test_run_bench_limit_smoke_mode(bench: Any, tmp_path: Path, monkeypatch: Any) -> None:
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    _make_capsule_zip(capsules_dir, "capsule-A-01", b2=True, verdict="REGRESSION CONFIRMED")
    _make_capsule_zip(capsules_dir, "capsule-B-01", b2=True, verdict="REGRESSION CONFIRMED")
    seen: list[str] = []

    def fake_execute(extracted_dir: Path, repo: Path, timeout: float) -> Any:
        seen.append(extracted_dir.name)
        return bench.RunResult(
            exit_code=0,
            stdout="  Base test exit code: 0\n  Head test exit code: 1\n"
            "  >> REGRESSION CONFIRMED <<\n",
            stderr="", timed_out=False, error="",
        )

    def fake_extract(
        python: str, repo_root: Path, zip_path: Path, out_dir: Path,
    ) -> tuple[bool, str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return True, "stubbed extract ok"

    monkeypatch.setattr(
        bench, "prepare_temp_worktree",
        lambda r, refs, w: _stub_worktree(tmp_path / "repo"),
    )
    monkeypatch.setattr(bench, "extract_via_replay_cli", fake_extract)
    monkeypatch.setattr(bench, "execute_run_script", fake_execute)
    args = bench.build_parser().parse_args(
        [
            "--limit", "1",
            "--capsules-dir", str(capsules_dir),
            "--repo", str(tmp_path),
            "--output-json", str(tmp_path / "r.json"),
            "--output-md", str(tmp_path / "r.md"),
        ]
    )
    results = bench.run_bench(args)
    assert results["totals"]["enumerated"] == 1
    assert len(seen) == 1


def test_run_bench_missing_ref_is_env_mismatch(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    _make_capsule_zip(capsules_dir, "capsule-REF-01", b2=True, verdict="REGRESSION CONFIRMED")
    monkeypatch.setattr(
        bench, "prepare_temp_worktree",
        lambda r, refs, w: {
            "repo": tmp_path / "repo", "mechanism": "test-stub",
            "refs": {"base": True}, "error": "",
        },
    )
    monkeypatch.setattr(bench, "extract_via_replay_cli", lambda p, rr, zp, od: (True, "ok"))
    args = bench.build_parser().parse_args(
        [
            "--capsules-dir", str(capsules_dir),
            "--repo", str(tmp_path),
            "--output-json", str(tmp_path / "r.json"),
            "--output-md", str(tmp_path / "r.md"),
        ]
    )
    results = bench.run_bench(args)
    entry = results["capsules"][0]
    assert entry["outcome"] == "env_mismatch"
    assert "head-v1" in entry["reason"]


def test_no_forbidden_markers_in_sources() -> None:
    """The bench script and this test carry no TODO/pass/key-literal markers."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for marker in ("TODO", "FIXME", "sk-"):
        assert marker not in source
    for line in source.splitlines():
        assert line.strip() != "pass"
