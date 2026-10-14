"""#261/#267 — a bug capsule must state *why* a scaffold-wiped finding stands.

The capsule is the replayable reproduction artifact. Before #267 its
manifest.json (the restatable summary) surfaced severity / confidence /
db_state_verdict / blocker_check but NOT the in-flight evidence run_differential
captures (#250 #253/#254): db_state_detail / behavioral_evidence /
db_violation_evidence. So a case-17-style capsule — where the post-run H2 dump
reads DB_CONSISTENT because the scaffold rolled the committed duplicate back —
looked like "no mutation happened", while the head-side generated test's
head-only DB-state-violation assertion was the captured proof.

These tests lock that the manifest carries the in-flight evidence verbatim
(and the README explains it), and that a finding without evidence stays honest
(empty string / empty dict), never fabricating evidence.

Capture-only: this changes no verdict, only what the archive records.

Offline: create_capsule_node writes into a real tmp dir; the object-metadata
recorder is stubbed.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agent.nodes.create_capsule import create_capsule_node

_DB_VIOLATION = {
    "marker": "DB STATE VIOLATION",
    "head_observed": True,
    "base_observed": False,
    "head_only": True,
}
_BEHAVIORAL = {
    "captured": True,
    "head_test_failed": True,
    "db_effect_rolled_back": False,
    "failing_method": "changeEmail",
    "note": "Behavioral regression with captured DB mutation.",
}


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


def _state(tmp_path: Path, finding: dict[str, Any]) -> dict[str, Any]:
    tests = tmp_path / "SpecProofGeneratedTest.java"
    tests.write_text("class SpecProofGeneratedTest {}", encoding="utf-8")
    return {
        "confirmed_findings": [finding],
        "contracts": [{"id": "AUTH-01", "checker_type": "sql"}],
        "requirement_text": "Duplicate email changes must be rejected.",
        "generated_tests_path": str(tests),
        "base_ref": "base",
        "head_ref": "head-v1",
        "job_id": "job-300",
    }


def _inflight_finding(**overrides: object) -> dict[str, Any]:
    f = {
        "id": "F-AUTH-01",
        "contract_id": "AUTH-01",
        "severity": "BLOCKER",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "evidence_digest": "sha256:" + "a" * 64,
        "db_state_verdict": "DB_MUTATED_ON_UNAUTH",
        "description": "duplicate email change accepted and persisted",
        "db_state_detail": "Head persisted a duplicate email; base did not.",
        "db_violation_evidence": dict(_DB_VIOLATION),
        "behavioral_evidence": dict(_BEHAVIORAL),
    }
    f.update(overrides)
    return f


def _pack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finding: dict[str, Any]):
    monkeypatch.setattr(
        "storage.object_metadata.record_file_object_best_effort", _Recorder()
    )
    out = create_capsule_node(_state(tmp_path, finding))  # type: ignore[arg-type]
    zip_path = next(Path(p) for p in out["capsules"])
    with zipfile.ZipFile(zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        readme = zf.read("README.md").decode("utf-8")
    return manifest, readme


def test_manifest_carries_inflight_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, _ = _pack(tmp_path, monkeypatch, _inflight_finding())
    assert manifest["db_state_detail"] == "Head persisted a duplicate email; base did not."
    assert manifest["db_violation_evidence"] == _DB_VIOLATION
    assert manifest["behavioral_evidence"] == _BEHAVIORAL
    # The recorded digest is still well-formed over the manifest with the new keys.
    assert manifest["manifest_digest"].startswith("sha256:")


def test_readme_explains_head_only_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, readme = _pack(tmp_path, monkeypatch, _inflight_finding())
    assert "In-flight Evidence" in readme
    assert "DB STATE VIOLATION" in readme
    assert "head-only" in readme


def test_finding_without_evidence_stays_honest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, readme = _pack(tmp_path, monkeypatch, _inflight_finding(
        db_state_detail="", db_violation_evidence=None, behavioral_evidence=""
    ))
    assert manifest["db_state_detail"] == ""
    assert manifest["db_violation_evidence"] == {}
    assert manifest["behavioral_evidence"] == {}
    # No in-flight evidence was captured, so the README invents none.
    assert "In-flight Evidence" not in readme
