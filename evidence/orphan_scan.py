"""Object-chain integrity scan: orphans, dangling refs, digest mismatch (P2-4).

The evidence chain is only worth what its weakest link is worth. A
certificate that names a capsule which no longer exists, a capsule file
nobody can account for, a payload whose bytes changed after it was
recorded — each of those quietly breaks a promise the UI and the CLI make
("download the evidence", "replay the capsule", "the digest is the
artifact").

This module finds those three conditions and reports them. It NEVER
deletes anything on its own: a scan produces a report, and removal is an
explicit, separately-confirmed action. A scan that silently deleted
"orphans" would destroy evidence on the strength of a heuristic — the
exact failure mode this project exists to avoid.

The three findings:

``dangling``
    A metadata record points at a payload path that no longer exists.
    The chain says "here is the evidence" and the evidence is gone.

``orphan``
    A payload file exists that no metadata record accounts for. It may be
    a leftover from a crashed run — or it may be evidence whose metadata
    was never written. The scan cannot tell which, and says so.

``digest_mismatch``
    A payload exists at the recorded path but its bytes no longer hash to
    the recorded digest. The artifact was modified after it was recorded
    — the chain is broken even though the file is still there.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from storage.object_metadata import (
    ObjectMetadata,
    ObjectMetadataStore,
    normalize_payload_digest,
    payload_sha256_of_file,
)

#: Finding kinds — closed vocabulary.
KIND_DANGLING = "dangling"
KIND_ORPHAN = "orphan"
KIND_DIGEST_MISMATCH = "digest_mismatch"

FINDING_KINDS: tuple[str, ...] = (KIND_DANGLING, KIND_ORPHAN, KIND_DIGEST_MISMATCH)

#: The file suffixes a capsule/certificate artifact is written with. A scan
#: only considers these — walking every file under a reports directory
#: would report the reports directory itself as orphaned.
ARTIFACT_SUFFIXES: tuple[str, ...] = (".zip", ".json")


@dataclass(frozen=True)
class ObjectFinding:
    """One integrity problem found in the object chain."""

    kind: str
    object_id: str
    path: str
    detail: str
    job_id: str = ""
    object_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "object_id": self.object_id,
            "path": self.path,
            "detail": self.detail,
            "job_id": self.job_id,
            "object_kind": self.object_kind,
        }


@dataclass
class ObjectScanReport:
    """The full scan result."""

    findings: list[ObjectFinding] = field(default_factory=list)
    scanned_records: int = 0
    scanned_files: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str = ""

    def by_kind(self) -> dict[str, int]:
        counts = dict.fromkeys(FINDING_KINDS, 0)
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return counts

    def is_clean(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "started_at": self.started_at,
            "finished_at": self.finished_at or datetime.now(UTC).isoformat(),
            "scanned_records": self.scanned_records,
            "scanned_files": self.scanned_files,
            "by_kind": self.by_kind(),
            "clean": self.is_clean(),
            "findings": [f.to_dict() for f in self.findings],
        }


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_files(root: Path) -> list[Path]:
    """Every artifact payload under *root* (bounded to the known suffixes)."""
    if not root.is_dir():
        return []
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in ARTIFACT_SUFFIXES:
            found.append(path)
    return sorted(found)


def _recorded_paths(records: Iterable[ObjectMetadata]) -> dict[str, ObjectMetadata]:
    """Path hint → record, for the records that carry one."""
    indexed: dict[str, ObjectMetadata] = {}
    for record in records:
        if record.path_hint:
            indexed[record.path_hint] = record
    return indexed


def scan_object_chain(
    store: ObjectMetadataStore,
    root: str | Path,
    *,
    limit: int = 10_000,
) -> ObjectScanReport:
    """Scan the object chain for the three integrity problems.

    Read-only: nothing is deleted, moved or modified. The caller decides
    what to do with the report.
    """
    report = ObjectScanReport()
    root_path = Path(root)

    records = store.list(limit=limit)
    report.scanned_records = len(records)
    recorded = _recorded_paths(records)

    # 1. Dangling references + 2. digest mismatches, per metadata record.
    for record in records:
        if not record.path_hint:
            continue
        target = Path(record.path_hint)
        if not target.is_file():
            report.findings.append(
                ObjectFinding(
                    kind=KIND_DANGLING,
                    object_id=record.object_id,
                    path=record.path_hint,
                    detail=(
                        "the metadata record points at a payload that no "
                        "longer exists"
                    ),
                    job_id=record.job_id,
                    object_kind=record.kind,
                )
            )
            continue
        expected = normalize_payload_digest(
            record.digests.get("payload_sha256", "")
        )
        if not expected:
            continue
        try:
            actual = normalize_payload_digest(payload_sha256_of_file(target))
        except OSError as exc:
            report.findings.append(
                ObjectFinding(
                    kind=KIND_DIGEST_MISMATCH,
                    object_id=record.object_id,
                    path=record.path_hint,
                    detail=f"the recorded payload could not be read: {exc}",
                    job_id=record.job_id,
                    object_kind=record.kind,
                )
            )
            continue
        if actual != expected:
            report.findings.append(
                ObjectFinding(
                    kind=KIND_DIGEST_MISMATCH,
                    object_id=record.object_id,
                    path=record.path_hint,
                    detail=(
                        "the payload was modified after it was recorded "
                        f"(expected sha256:{expected[:12]}..., "
                        f"found sha256:{actual[:12]}...)"
                    ),
                    job_id=record.job_id,
                    object_kind=record.kind,
                )
            )

    # 3. Orphans: files on disk that no record accounts for.
    files = _artifact_files(root_path)
    report.scanned_files = len(files)
    for path in files:
        if str(path) in recorded:
            continue
        # A file may still be recorded under a different (equivalent)
        # spelling of the same path — compare resolved forms so a
        # relative-vs-absolute hint does not produce a phantom orphan.
        if _resolves_to(recorded, path):
            continue
        report.findings.append(
            ObjectFinding(
                kind=KIND_ORPHAN,
                object_id="",
                path=str(path),
                detail=(
                    "an artifact payload exists that no metadata record "
                    "accounts for — it may be a leftover from a crashed run, "
                    "or evidence whose metadata was never written"
                ),
            )
        )

    report.finished_at = datetime.now(UTC).isoformat()
    return report


def _resolves_to(recorded: dict[str, ObjectMetadata], path: Path) -> bool:
    """True when some record's path_hint names the same file as *path*.

    Compared by resolved path, so "./capsules/a.zip" and an absolute
    "…/capsules/a.zip" are the same file and do not produce a phantom
    orphan finding.
    """
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for hint in recorded:
        try:
            if Path(hint).resolve() == resolved:
                return True
        except OSError:
            if hint == str(path):
                return True
    return False


def write_scan_report(report: ObjectScanReport, path: str | Path) -> str:
    """Write the scan report as JSON; returns the written path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    import json

    target.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return str(target)


__all__ = [
    "ARTIFACT_SUFFIXES",
    "FINDING_KINDS",
    "KIND_DANGLING",
    "KIND_DIGEST_MISMATCH",
    "KIND_ORPHAN",
    "ObjectFinding",
    "ObjectScanReport",
    "scan_object_chain",
    "write_scan_report",
]
