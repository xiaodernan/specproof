"""Unit tests for the two-tier replay: static evidence re-verification.

These tests exercise the tier-2 static path added to scripts/bench_replay.py:
static-evidence capsules are re-verified at the recorded head commit (recorded
snippet paths + content, or deterministic checker re-derivation) instead of
being judged by a runtime Maven verdict they can never reproduce. All tests
are offline: no Docker, no git, no Maven.
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

ORDER_SERVICE_REL = "com/specproof/demo/service/OrderService.java"
ORDER_SERVICE_HEAD = (
    "package com.specproof.demo.service;\n"
    "public class OrderService {\n"
    "  public void placeOrder() {\n"
    "    rabbitTemplate.convertAndSend(\"orders\", event);\n"
    "    rabbitTemplate.convertAndSend(\"orders\", event);\n"
    "  }\n"
    "}\n"
)
ORDER_SERVICE_BASE = (
    "package com.specproof.demo.service;\n"
    "public class OrderService {\n"
    "  public void placeOrder() {\n"
    "    rabbitTemplate.convertAndSend(\"orders\", event);\n"
    "  }\n"
    "}\n"
)


def _load_bench() -> Any:
    """Load scripts/bench_replay.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("bench_replay", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bench_replay"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def bench() -> Any:
    return _load_bench()


def _make_static_capsule_zip(
    root: Path,
    name: str,
    *,
    finding: dict[str, Any],
    evidence_type: str = "java_source_diff",
    contract_id: str = "EVENT_ONCE-01",
    snippets: list[dict[str, str]] | None = None,
    with_finding: bool = True,
    with_manifest: bool = True,
    head_ref: str = "head-v1",
) -> Path:
    """A synthetic static-evidence capsule zip (manifest_digest per the canonical rule)."""
    bench_module = _load_bench()
    manifest: dict[str, Any] = {
        "finding_id": name.replace("capsule-", ""),
        "severity": "MAJOR",
        "confidence": 0.85,
        "contract_id": contract_id,
        "evidence_type": evidence_type,
        "evidence_digest": "sha256:" + "e" * 64,
        "blocker_check": {
            "blocker_conditions": {
                "1_approved_contract": True,
                "2_base_head_execution": False,
                "3_attribution_to_head": True,
                "4_db_behavior_evidence": False,
                "5_capsule_replayable": False,
                "6_confidence_090": False,
            },
            "all_blocker_conditions_met": False,
        },
    }
    digest = bench_module.canonical_manifest_digest(manifest)
    manifest["manifest_digest"] = "sha256:" + digest
    zip_path = root / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        if with_manifest:
            archive.writestr("manifest.json", json.dumps(manifest))
        if with_finding:
            archive.writestr("finding.json", json.dumps(finding))
        archive.writestr("fixtures/base-ref.txt", "base")
        archive.writestr("fixtures/head-ref.txt", head_ref)
        archive.writestr(
            "generated-tests/SpecProofGeneratedTest.java",
            "package com.specproof.demo;\n",
        )
        archive.writestr(
            "run.ps1",
            "param([string]$RepoDir = $env:SPECPROOF_REPO)\n"
            "Write-Host '  >> COMPLIANT <<'\n",
        )
        archive.writestr("run.sh", "#!/bin/bash\necho '>> COMPLIANT <<'\n")
        if snippets is not None:
            archive.writestr(
                "static-evidence.json",
                json.dumps({"snippets": snippets}),
            )
    return zip_path


def _finding(
    contract_id: str = "EVENT_ONCE-01",
    finding_type: str = "duplicate_publish",
    location: str = ORDER_SERVICE_REL,
) -> dict[str, Any]:
    return {
        "id": "SRC-EVENT_ONCE-DUPL",
        "contract_id": contract_id,
        "severity": "MAJOR",
        "type": finding_type,
        "description": (
            "Event publish count increased in "
            f"{ORDER_SERVICE_REL}: 1 -> 2"
        ),
        "evidence_type": "java_source_diff",
        "confidence": 0.85,
        "location": location,
        "source": "contract_checker",
        "status": "confirmed",
        "evidence_digest": "sha256:" + "e" * 64,
    }


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


def _head_snapshot(bench: Any, java: dict[str, str] | None = None) -> Any:
    return bench.WorktreeSnapshot(
        java=java if java is not None else {ORDER_SERVICE_REL: ORDER_SERVICE_HEAD},
        tests={},
        schema_sql="",
    )


def _base_snapshot(bench: Any) -> Any:
    return bench.WorktreeSnapshot(
        java={ORDER_SERVICE_REL: ORDER_SERVICE_BASE},
        tests={},
        schema_sql="",
    )


def _load_manifest(zip_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as archive:
        return json.loads(archive.read("manifest.json"))


# ── static evidence kind classification ────────────────────────────────────


@pytest.mark.parametrize(
    "evidence_type",
    [
        "java_source_diff",
        "openapi_endpoint",
        "constitution_check",
        "static_regex_analysis",
        "probe_differential",
        "mutation_check",
        "annotation_diff",
        "STATIC_ANALYSIS",
    ],
)
def test_static_evidence_kinds_are_static(bench: Any, evidence_type: str) -> None:
    assert bench.is_static_evidence_kind(evidence_type)


@pytest.mark.parametrize(
    "evidence_type",
    ["base_pass_head_fail", "differential_execution", "", "runtime"],
)
def test_runtime_evidence_kinds_are_not_static(bench: Any, evidence_type: str) -> None:
    assert not bench.is_static_evidence_kind(evidence_type)


def test_is_static_only_capsule_requires_no_runtime_claim(bench: Any) -> None:
    static_manifest = {
        "evidence_type": "java_source_diff",
        "blocker_check": {
            "blocker_conditions": {"2_base_head_execution": False},
            "all_blocker_conditions_met": False,
        },
    }
    assert bench.is_static_only_capsule(static_manifest)
    runtime_manifest = {
        "evidence_type": "java_source_diff",
        "blocker_check": {
            "blocker_conditions": {"2_base_head_execution": True},
            "all_blocker_conditions_met": False,
        },
    }
    assert not bench.is_static_only_capsule(runtime_manifest)


# ── tier-2: recorded snippet payloads at head ───────────────────────────────


def test_static_snippet_present_at_head_verifies(
    bench: Any, tmp_path: Path,
) -> None:
    """Task (a): the recorded snippet exists with the recorded content at head."""
    zip_path = _make_static_capsule_zip(
        tmp_path,
        "capsule-SNIPPET-OK",
        finding=_finding(),
        snippets=[{"path": ORDER_SERVICE_REL, "content": ORDER_SERVICE_HEAD}],
    )
    unit = _unit(bench, zip_path, "capsule-SNIPPET-OK")
    outcome = bench.classify_static_replay(
        unit,
        _load_manifest(zip_path),
        _finding(),
        None,
        _base_snapshot(bench),
        _head_snapshot(bench),
    )
    assert outcome.outcome == "same_conclusion"
    assert bench.STATIC_VERIFIED_NOTE in outcome.reason
    assert "head-v1" in outcome.reason


def test_static_snippet_gone_from_head_fails(
    bench: Any, tmp_path: Path,
) -> None:
    """Task (b): the recorded snippet is gone from head — replay_failed, real reason."""
    zip_path = _make_static_capsule_zip(
        tmp_path,
        "capsule-SNIPPET-GONE",
        finding=_finding(),
        snippets=[{"path": ORDER_SERVICE_REL, "content": ORDER_SERVICE_HEAD}],
    )
    unit = _unit(bench, zip_path, "capsule-SNIPPET-GONE")
    empty_head = _head_snapshot(bench, java={})
    outcome = bench.classify_static_replay(
        unit,
        _load_manifest(zip_path),
        _finding(),
        None,
        _base_snapshot(bench),
        empty_head,
    )
    assert outcome.outcome == "replay_failed"
    assert "gone from head" in outcome.reason
    assert ORDER_SERVICE_REL in outcome.reason


def test_static_snippet_content_changed_fails(
    bench: Any, tmp_path: Path,
) -> None:
    zip_path = _make_static_capsule_zip(
        tmp_path,
        "capsule-SNIPPET-CHANGED",
        finding=_finding(),
        snippets=[{"path": ORDER_SERVICE_REL, "content": ORDER_SERVICE_HEAD}],
    )
    unit = _unit(bench, zip_path, "capsule-SNIPPET-CHANGED")
    changed_head = _head_snapshot(bench, java={ORDER_SERVICE_REL: "rewritten\n"})
    outcome = bench.classify_static_replay(
        unit,
        _load_manifest(zip_path),
        _finding(),
        None,
        _base_snapshot(bench),
        changed_head,
    )
    assert outcome.outcome == "replay_failed"
    assert "no longer matches the recorded content" in outcome.reason


def test_static_finding_path_gone_without_snippet_payload(
    bench: Any, tmp_path: Path,
) -> None:
    """No snippet payload: the finding's recorded path must still exist at head."""
    zip_path = _make_static_capsule_zip(
        tmp_path,
        "capsule-PATH-GONE",
        finding=_finding(),
    )
    unit = _unit(bench, zip_path, "capsule-PATH-GONE")
    outcome = bench.classify_static_replay(
        unit,
        _load_manifest(zip_path),
        _finding(),
        None,
        _base_snapshot(bench),
        _head_snapshot(bench, java={}),
    )
    assert outcome.outcome == "replay_failed"
    assert "gone from head" in outcome.reason
    assert ORDER_SERVICE_REL in outcome.reason


# ── tier-2: deterministic checker re-derivation at head ─────────────────────


def test_static_checker_rederivation_verifies(
    bench: Any, tmp_path: Path,
) -> None:
    """No snippet payload: the recorded finding re-derives from the head tree."""
    zip_path = _make_static_capsule_zip(
        tmp_path,
        "capsule-CHECKER-OK",
        finding=_finding(),
    )
    unit = _unit(bench, zip_path, "capsule-CHECKER-OK")
    outcome = bench.classify_static_replay(
        unit,
        _load_manifest(zip_path),
        _finding(),
        None,
        _base_snapshot(bench),
        _head_snapshot(bench),
    )
    assert outcome.outcome == "same_conclusion"
    assert bench.STATIC_VERIFIED_NOTE in outcome.reason
    assert "EVENT_ONCE-01/duplicate_publish" in outcome.reason


def test_static_checker_no_longer_flags_fails(
    bench: Any, tmp_path: Path,
) -> None:
    """Head no longer violates the contract — recorded evidence does not re-verify."""
    zip_path = _make_static_capsule_zip(
        tmp_path,
        "capsule-CHECKER-FAIL",
        finding=_finding(),
    )
    unit = _unit(bench, zip_path, "capsule-CHECKER-FAIL")
    clean_head = _head_snapshot(bench, java={ORDER_SERVICE_REL: ORDER_SERVICE_BASE})
    outcome = bench.classify_static_replay(
        unit,
        _load_manifest(zip_path),
        _finding(),
        None,
        _base_snapshot(bench),
        clean_head,
    )
    assert outcome.outcome == "replay_failed"
    assert "no longer re-verifies" in outcome.reason


# ── tier 1 unchanged: runtime-evidence capsules ─────────────────────────────


def test_runtime_evidence_capsule_unchanged(bench: Any) -> None:
    """Task (c): runtime-evidence classification keeps its existing behavior."""
    run = bench.RunResult(
        exit_code=0,
        stdout=(
            "  Base test exit code: 0\n"
            "  Head test exit code: 1\n"
            "  >> REGRESSION CONFIRMED <<\n"
        ),
        stderr="",
        timed_out=False,
        error="",
    )
    outcome = bench.classify_replay(bench.VERDICT_CONFIRMED, run)
    assert outcome.outcome == "same_conclusion"
    assert outcome.verdict == "REGRESSION CONFIRMED"
    compliant = bench.RunResult(
        exit_code=0,
        stdout="  Base test exit code: 0\n  Head test exit code: 0\n  >> COMPLIANT <<\n",
        stderr="",
        timed_out=False,
        error="",
    )
    failed = bench.classify_replay(bench.VERDICT_CONFIRMED, compliant)
    assert failed.outcome == "replay_failed"
    assert failed.verdict == "COMPLIANT"


# ── end-to-end batch: static_verified count + two-tier gate note ────────────


def test_run_bench_two_tier_static_verified_counts(
    bench: Any, tmp_path: Path, monkeypatch: Any,
) -> None:
    capsules_dir = tmp_path / "capsules"
    capsules_dir.mkdir()
    _make_static_capsule_zip(
        capsules_dir,
        "capsule-STAT-01",
        finding=_finding(),
        snippets=[{"path": ORDER_SERVICE_REL, "content": ORDER_SERVICE_HEAD}],
    )
    runtime_zip = capsules_dir / "capsule-RUN-01.zip"
    manifest = {
        "finding_id": "RUN-01",
        "severity": "MAJOR",
        "confidence": 0.9,
        "contract_id": "AUTH-01",
        "evidence_type": "base_pass_head_fail",
        "evidence_digest": "sha256:" + "e" * 64,
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
    digest = bench.canonical_manifest_digest(manifest)
    manifest["manifest_digest"] = "sha256:" + digest
    with zipfile.ZipFile(runtime_zip, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(
            "finding.json",
            json.dumps({
                "id": "RUN-01",
                "contract_id": "AUTH-01",
                "severity": "MAJOR",
                "type": "differential_regression",
                "description": "synthetic runtime capsule",
                "evidence_type": "base_pass_head_fail",
                "evidence_digest": "sha256:" + "e" * 64,
                "status": "confirmed",
            }),
        )
        archive.writestr("fixtures/base-ref.txt", "base")
        archive.writestr("fixtures/head-ref.txt", "head-v1")
        archive.writestr(
            "run.ps1",
            "param([string]$RepoDir)\nWrite-Host '  >> REGRESSION CONFIRMED <<'\n",
        )

    fake_repo = tmp_path / "fake-repo"
    monkeypatch.setattr(
        bench, "prepare_temp_worktree",
        lambda repo_root, refs, work_root: {
            "repo": fake_repo, "mechanism": "test-stub",
            "refs": {"base": True, "head-v1": True}, "error": "",
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
    monkeypatch.setattr(bench, "checkout_worktree_ref", lambda repo, ref: "")
    monkeypatch.setattr(
        bench, "snapshot_worktree_sources",
        lambda repo: bench.WorktreeSnapshot(
            java={ORDER_SERVICE_REL: ORDER_SERVICE_HEAD}, tests={}, schema_sql="",
        ),
    )

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
    assert totals["same_conclusion"] == 2
    assert totals["static_verified"] == 1
    outcomes = {entry["unit"]: entry for entry in results["capsules"]}
    static_entry = outcomes["capsule-STAT-01"]
    assert static_entry["outcome"] == "same_conclusion"
    assert static_entry["replay_mode"] == "static_reverify"
    assert static_entry["static_verified"] is True
    assert bench.STATIC_VERIFIED_NOTE in static_entry["reason"]
    runtime_entry = outcomes["capsule-RUN-01"]
    assert runtime_entry["outcome"] == "same_conclusion"
    assert runtime_entry["replay_mode"] == "runtime"
    assert runtime_entry["static_verified"] is False
    assert runtime_entry["verdict"] == "REGRESSION CONFIRMED"
    md_text = Path(args.output_md).read_text(encoding="utf-8")
    assert "## Two-tier replay definition (gate note)" in md_text
    assert "static_verified (static evidence re-verified at head)" in md_text
    written = json.loads(Path(args.output_json).read_text(encoding="utf-8"))
    assert written["totals"]["static_verified"] == 1
    assert written["totals"]["same_conclusion"] == 2


def test_no_forbidden_markers_in_sources() -> None:
    """The bench script carries no TODO/pass/key-literal markers."""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for marker in ("TODO", "FIXME", "sk-"):
        assert marker not in source
    for line in source.splitlines():
        assert line.strip() != "pass"
