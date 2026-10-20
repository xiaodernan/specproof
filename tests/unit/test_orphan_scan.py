"""Object-chain integrity scan tests (Phase 2, P2-4).

The scan's whole value is that it tells an operator WHICH link broke. These
tests pin the three findings (dangling / orphan / digest mismatch), and
they pin the property that matters most: the scan is READ-ONLY. A scan
that deleted what it called an orphan would destroy evidence on the
strength of a heuristic.

No Docker, no network, no MySQL: the in-memory metadata store and tmp_path
files are enough.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evidence.orphan_scan import (
    KIND_DANGLING,
    KIND_DIGEST_MISMATCH,
    KIND_ORPHAN,
    scan_object_chain,
    write_scan_report,
)
from storage.object_metadata import (
    InMemoryObjectMetadataStore,
    new_metadata,
    payload_sha256_of_file,
)


def _record(
    store: InMemoryObjectMetadataStore,
    path: Path,
    *,
    kind: str = "capsule",
    job_id: str = "job-1",
) -> None:
    """Record *path* in the metadata store with its real payload digest."""
    store.record(
        new_metadata(
            kind,  # type: ignore[arg-type]
            {"payload_sha256": payload_sha256_of_file(path)},
            job_id=job_id,
            path_hint=str(path),
        )
    )


def _zip(path: Path, marker: str = "x") -> Path:
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"marker": marker}))
    return path


# ── the clean case ─────────────────────────────────────────────────────────


def test_clean_chain_has_no_findings(tmp_path: Path) -> None:
    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip")
    _record(store, capsule)
    report = scan_object_chain(store, tmp_path)
    assert report.is_clean()
    assert report.findings == []
    assert report.scanned_records == 1
    assert report.scanned_files == 1


# ── dangling reference ─────────────────────────────────────────────────────


def test_deleted_payload_is_a_dangling_reference(tmp_path: Path) -> None:
    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip")
    _record(store, capsule)
    capsule.unlink()
    report = scan_object_chain(store, tmp_path)
    kinds = {f.kind for f in report.findings}
    assert KIND_DANGLING in kinds
    dangling = next(f for f in report.findings if f.kind == KIND_DANGLING)
    assert dangling.path == str(capsule)
    assert dangling.job_id == "job-1"


# ── digest mismatch ────────────────────────────────────────────────────────


def test_modified_payload_is_a_digest_mismatch(tmp_path: Path) -> None:
    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip", marker="original")
    _record(store, capsule)
    # Same path, different bytes.
    _zip(capsule, marker="tampered")
    report = scan_object_chain(store, tmp_path)
    kinds = {f.kind for f in report.findings}
    assert KIND_DIGEST_MISMATCH in kinds
    mismatch = next(f for f in report.findings if f.kind == KIND_DIGEST_MISMATCH)
    assert "modified after it was recorded" in mismatch.detail


def test_untouched_payload_is_not_a_mismatch(tmp_path: Path) -> None:
    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip")
    _record(store, capsule)
    report = scan_object_chain(store, tmp_path)
    assert not [f for f in report.findings if f.kind == KIND_DIGEST_MISMATCH]


# ── orphans ────────────────────────────────────────────────────────────────


def test_unaccounted_payload_is_an_orphan(tmp_path: Path) -> None:
    store = InMemoryObjectMetadataStore()
    _zip(tmp_path / "recorded.zip")
    _record(store, tmp_path / "recorded.zip")
    _zip(tmp_path / "leftover.zip")
    report = scan_object_chain(store, tmp_path)
    orphans = [f for f in report.findings if f.kind == KIND_ORPHAN]
    assert len(orphans) == 1
    assert orphans[0].path.endswith("leftover.zip")
    assert "no metadata record accounts for" in orphans[0].detail


def test_relative_path_hint_does_not_produce_a_phantom_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative hint and an absolute path are the same file."""
    import os

    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip")
    store.record(
        new_metadata(
            "capsule",
            {"payload_sha256": payload_sha256_of_file(capsule)},
            job_id="job-1",
            path_hint="capsule.zip",
        )
    )
    monkeypatch.chdir(tmp_path)
    report = scan_object_chain(store, tmp_path)
    assert not [f for f in report.findings if f.kind == KIND_ORPHAN]
    assert os.getcwd() == str(tmp_path)


# ── the read-only guarantee ────────────────────────────────────────────────


def test_scan_deletes_nothing(tmp_path: Path) -> None:
    """The scan is a report, never a cleanup."""
    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip")
    _record(store, capsule)
    orphan = _zip(tmp_path / "leftover.zip")
    capsule.unlink()

    report = scan_object_chain(store, tmp_path)

    assert report.findings, "the scan must still find the problems"
    assert orphan.is_file(), "the scan must not delete an orphan"
    assert store.list(), "the scan must not delete metadata records"


# ── the report shape ───────────────────────────────────────────────────────


def test_report_serializes_to_json(tmp_path: Path) -> None:
    store = InMemoryObjectMetadataStore()
    capsule = _zip(tmp_path / "capsule.zip")
    _record(store, capsule)
    capsule.unlink()
    report = scan_object_chain(store, tmp_path)
    out = tmp_path / "out" / "scan.json"
    written = write_scan_report(report, out)
    assert Path(written) == out
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["by_kind"][KIND_DANGLING] == 1
    assert loaded["clean"] is False
    assert loaded["findings"]


def test_by_kind_lists_every_key(tmp_path: Path) -> None:
    report = scan_object_chain(InMemoryObjectMetadataStore(), tmp_path)
    counts = report.by_kind()
    assert counts[KIND_DANGLING] == 0
    assert counts[KIND_ORPHAN] == 0
    assert counts[KIND_DIGEST_MISMATCH] == 0


def test_empty_root_is_clean(tmp_path: Path) -> None:
    report = scan_object_chain(InMemoryObjectMetadataStore(), tmp_path / "nope")
    assert report.is_clean()
    assert report.scanned_files == 0
