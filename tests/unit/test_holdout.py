"""HoldoutRegistry unit tests — manifest loading, validation, partition, report.

No network and nothing outside tmp_path, except the real-manifest
cross-check, which only reads directory names under golden-cases/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.holdout import ACTIVE_HOLDOUT_STATUSES, HoldoutError, HoldoutRegistry


def _write_manifest(
    path: Path,
    cases: list[dict[str, str]],
    *,
    note: str = "retroactive partial isolation note",
    integration_note: str = "",
) -> None:
    payload: dict[str, Any] = {"cases": cases, "note": note}
    if integration_note:
        payload["integration_note"] = integration_note
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sample_cases() -> list[dict[str, str]]:
    return [
        {
            "case_id": "case-01-auth-bypass",
            "family": "authnz",
            "added_at": "2026-08-19",
            "status": "candidate",
        },
        {
            "case_id": "case-02-transactional-removal",
            "family": "transaction",
            "added_at": "2026-08-19",
            "status": "active",
        },
        {
            "case_id": "case-03-clean-pr",
            "family": "negative-control",
            "added_at": "2026-08-19",
            "status": "released",
        },
    ]


def test_load_roundtrip(tmp_path: Path) -> None:
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, _sample_cases(), integration_note="wiring notes")
    registry = HoldoutRegistry.load(manifest)
    assert [entry.case_id for entry in registry.cases()] == [
        "case-01-auth-bypass",
        "case-02-transactional-removal",
        "case-03-clean-pr",
    ]
    assert registry.note == "retroactive partial isolation note"
    assert registry.integration_note == "wiring notes"
    assert registry.manifest_path == str(manifest)


def test_is_holdout_status_semantics(tmp_path: Path) -> None:
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, _sample_cases())
    registry = HoldoutRegistry.load(manifest)
    assert registry.is_holdout("case-01-auth-bypass")  # candidate
    assert registry.is_holdout("case-02-transactional-removal")  # active
    assert not registry.is_holdout("case-03-clean-pr")  # released
    assert not registry.is_holdout("case-99-unseen")  # undeclared


def test_partition_preserves_input_order(tmp_path: Path) -> None:
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, _sample_cases())
    registry = HoldoutRegistry.load(manifest)
    ids = ["case-00-other", "case-01-auth-bypass", "case-03-clean-pr", "case-99-x"]
    partition = registry.partition(ids)
    assert partition.holdout == ["case-01-auth-bypass"]
    assert partition.training == ["case-00-other", "case-03-clean-pr", "case-99-x"]
    assert partition.holdout_count == 1
    assert partition.training_count == 3
    assert partition.to_dict() == {
        "holdout": ["case-01-auth-bypass"],
        "training": ["case-00-other", "case-03-clean-pr", "case-99-x"],
    }


def test_partition_all_holdout_and_none(tmp_path: Path) -> None:
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, _sample_cases())
    registry = HoldoutRegistry.load(manifest)
    all_holdout = registry.partition(
        ["case-01-auth-bypass", "case-02-transactional-removal"]
    )
    assert all_holdout.holdout == [
        "case-01-auth-bypass",
        "case-02-transactional-removal",
    ]
    assert all_holdout.training == []
    assert registry.partition([]).to_dict() == {"holdout": [], "training": []}


def test_report_is_deterministic_and_complete(tmp_path: Path) -> None:
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, _sample_cases())
    registry = HoldoutRegistry.load(manifest)
    first = registry.report()
    second = registry.report()
    assert first == second
    assert "total: 3 cases (active=1, candidate=1, released=1)" in first
    assert "authnz: case-01-auth-bypass" in first
    assert "note: retroactive partial isolation note" in first


def test_summary_counts(tmp_path: Path) -> None:
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, _sample_cases())
    registry = HoldoutRegistry.load(manifest)
    summary = registry.summary()
    assert summary["total"] == 3
    assert summary["holdout_total"] == 2
    assert summary["by_status"] == {"active": 1, "candidate": 1, "released": 1}
    assert summary["by_family"] == {
        "authnz": 1,
        "negative-control": 1,
        "transaction": 1,
    }


def test_load_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(HoldoutError, match="无法读取"):
        HoldoutRegistry.load(tmp_path / "missing.json")


def test_load_malformed_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "holdout-manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(HoldoutError, match="不是合法 JSON"):
        HoldoutRegistry.load(path)


def test_load_top_level_must_be_object(tmp_path: Path) -> None:
    path = tmp_path / "holdout-manifest.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(HoldoutError, match="顶层必须是对象"):
        HoldoutRegistry.load(path)


def test_load_missing_cases_list_raises(tmp_path: Path) -> None:
    path = tmp_path / "holdout-manifest.json"
    path.write_text(json.dumps({"note": "x"}), encoding="utf-8")
    with pytest.raises(HoldoutError, match="缺少 cases"):
        HoldoutRegistry.load(path)


def test_load_rejects_missing_fields(tmp_path: Path) -> None:
    cases: list[dict[str, str]] = [
        {"case_id": "case-01-auth-bypass", "family": "authnz", "added_at": "2026-08-19"}
    ]
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, cases)
    with pytest.raises(HoldoutError, match="缺少字符串字段"):
        HoldoutRegistry.load(manifest)


def test_load_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    cases = _sample_cases()
    cases.append(dict(cases[0]))
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, cases)
    with pytest.raises(HoldoutError, match="重复 case_id"):
        HoldoutRegistry.load(manifest)


def test_load_rejects_unknown_status(tmp_path: Path) -> None:
    cases = _sample_cases()
    cases[0] = {**cases[0], "status": "frozen"}
    manifest = tmp_path / "holdout-manifest.json"
    _write_manifest(manifest, cases)
    with pytest.raises(HoldoutError, match="status 非法"):
        HoldoutRegistry.load(manifest)


def test_default_manifest_marks_existing_golden_cases() -> None:
    registry = HoldoutRegistry.load()
    repo_root = Path(__file__).resolve().parents[2]
    golden_dir = repo_root / "golden-cases"
    entries = registry.cases()
    assert len(entries) == 10
    for entry in entries:
        assert (golden_dir / entry.case_id).is_dir(), (
            f"manifest 引用了不存在的 golden case: {entry.case_id}"
        )
    assert all(entry.status in ACTIVE_HOLDOUT_STATUSES for entry in entries)
    assert all(entry.family.strip() for entry in entries)
    assert "retroactive" in registry.note.lower()
    assert "partial" in registry.note.lower()
    assert registry.is_holdout("case-01-auth-bypass")
    assert not registry.is_holdout("case-99-nonexistent")
