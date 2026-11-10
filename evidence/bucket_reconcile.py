"""Bucket-side reconciliation: objects in the object store vs. the index.

The gap this closes
-------------------
``storage/artifact_store.py`` is explicit that it can leave a **ghost**:
the upload succeeds, the index row does not, and (in lenient mode) the bytes
stay in the bucket because those bytes are the evidence. Its docstring says
such an object is "recoverable by the reconciliation scan".

That scan existed for the LOCAL payload store
(``evidence/orphan_scan.py`` — it walks a payload directory and compares it
with the index). It never existed for the **buckets**: nothing listed the
objects in ``specproof-bug-capsules`` & co. and asked which of them the index
does not know about. So the promise in the artifact store's docstring pointed
at a reader that did not exist.

This module is that reader. It answers three questions about the buckets and
the index, and it answers them **without deleting anything**:

``unindexed``
    The object is in the bucket and no index row points at it. This is the
    ghost the artifact store's lenient mode leaves behind — durable bytes
    that nothing accounts for.

``missing``
    An index row points at an object that is not in the bucket. The chain
    says "here is the evidence" and the evidence is gone.

``digest_mismatch``
    The object is there and the index knows it, but the bytes no longer
    hash to the recorded digest: the artifact changed after it was recorded.

Deleting is a separate, explicit act (the same rule ``orphan_scan`` follows:
a scan that silently removed what it called an orphan would destroy evidence
on the strength of a heuristic). This module reports; it never touches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from storage.object_metadata import (
    ObjectMetadataStore,
    normalize_object_ref,
    normalize_payload_digest,
)

logger = logging.getLogger(__name__)

#: Finding kinds — closed vocabulary.
KIND_UNINDEXED = "unindexed"
KIND_MISSING = "missing"
KIND_DIGEST_MISMATCH = "digest_mismatch"

#: Every finding kind, in the order a report prints them.
FINDING_KINDS = (KIND_UNINDEXED, KIND_MISSING, KIND_DIGEST_MISMATCH)


class ObjectStoreLike:
    """The slice of the object store this module uses.

    ``list_bucket_objects`` returns the objects as ``(name, size, sha256)``
    triples; ``sha256`` is the digest the store itself reports and may be
    empty when the backend does not expose one (the caller then skips the
    digest comparison rather than guessing).
    """

    def list_bucket_objects(self, bucket: str) -> list[tuple[str, int, str]]:
        raise NotImplementedError

    def object_digest(self, bucket: str, object_name: str) -> str | None:
        raise NotImplementedError


@dataclass(frozen=True)
class BucketFinding:
    """One broken link between the bucket and the index."""

    kind: str
    bucket: str
    object_name: str
    detail: str = ""


@dataclass
class BucketReconcileReport:
    """What the scan found — a report, never an action."""

    findings: list[BucketFinding] = field(default_factory=list)
    scanned_objects: int = 0
    scanned_records: int = 0
    buckets: tuple[str, ...] = ()

    def is_clean(self) -> bool:
        return not self.findings

    def of_kind(self, kind: str) -> list[BucketFinding]:
        return [finding for finding in self.findings if finding.kind == kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "buckets": list(self.buckets),
            "scanned_objects": self.scanned_objects,
            "scanned_records": self.scanned_records,
            "is_clean": self.is_clean(),
            "findings": [
                {
                    "kind": finding.kind,
                    "bucket": finding.bucket,
                    "object_name": finding.object_name,
                    "detail": finding.detail,
                }
                for finding in self.findings
            ],
        }


def reconcile_buckets(
    objects: ObjectStoreLike,
    metadata: ObjectMetadataStore,
    buckets: tuple[str, ...] | list[str],
    *,
    record_limit: int = 1000,
) -> BucketReconcileReport:
    """Compare the buckets with the index and report every broken link.

    Read-only: no object is removed, no index row is touched. The caller
    decides what to do with the report.
    """
    report = BucketReconcileReport(buckets=tuple(buckets))

    indexed: dict[str, Any] = {}
    for record in metadata.list(limit=record_limit):
        report.scanned_records += 1
        ref = normalize_object_ref(getattr(record, "object_ref", "") or "")
        if ref:
            indexed[ref] = record

    seen: set[str] = set()
    for bucket in buckets:
        for name, _size, _digest in objects.list_bucket_objects(bucket):
            report.scanned_objects += 1
            ref = f"{bucket}/{name}"
            seen.add(ref)
            record = indexed.get(ref)
            if record is None:
                report.findings.append(
                    BucketFinding(
                        kind=KIND_UNINDEXED,
                        bucket=bucket,
                        object_name=name,
                        detail=(
                            "the object is in the bucket and no index row "
                            "points at it — a ghost left by an upload whose "
                            "index write failed"
                        ),
                    )
                )
                continue
            recorded = normalize_payload_digest(
                str((getattr(record, "digests", {}) or {}).get("payload_sha256", ""))
            )
            if not recorded:
                continue
            try:
                actual = objects.object_digest(bucket, name)
            except Exception as exc:  # noqa: BLE001 — a store that cannot answer is not a verdict
                report.findings.append(
                    BucketFinding(
                        kind=KIND_DIGEST_MISMATCH,
                        bucket=bucket,
                        object_name=name,
                        detail=f"the digest could not be read: {type(exc).__name__}: {exc}",
                    )
                )
                continue
            if actual is None:
                continue
            if normalize_payload_digest(str(actual)) != recorded:
                report.findings.append(
                    BucketFinding(
                        kind=KIND_DIGEST_MISMATCH,
                        bucket=bucket,
                        object_name=name,
                        detail=(
                            f"the object hashes to {normalize_payload_digest(str(actual))} "
                            f"but the index recorded {recorded}"
                        ),
                    )
                )

    for ref in sorted(indexed):
        if ref in seen:
            continue
        bucket, _, name = ref.partition("/")
        report.findings.append(
            BucketFinding(
                kind=KIND_MISSING,
                bucket=bucket,
                object_name=name,
                detail=(
                    "the index points at an object that is not in the bucket — "
                    "the chain says 'here is the evidence' and the evidence is gone"
                ),
            )
        )

    report.findings.sort(
        key=lambda finding: (FINDING_KINDS.index(finding.kind)
                             if finding.kind in FINDING_KINDS else len(FINDING_KINDS),
                             finding.bucket,
                             finding.object_name)
    )
    return report
