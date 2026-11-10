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

This module is that reader. It answers four questions about the buckets and
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

``ambiguous_index``
    **Several** index rows point at the same object and they disagree about
    its digest. This is what the real data looks like: one eval case
    rebuilt its capsule three times and left three rows for the same
    object. Picking "the last row" would turn an ambiguity into a verdict —
    and a verdict here decides whether an operator deletes evidence. So the
    ambiguity is reported as its own finding.

Deleting is a separate, explicit act (the same rule ``orphan_scan`` follows:
a scan that silently removed what it called an orphan would destroy evidence
on the strength of a heuristic). This module reports; it never touches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from evidence.findings_report import FindingsReport
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
KIND_AMBIGUOUS_INDEX = "ambiguous_index"

#: Every finding kind, in the order a report prints them.
FINDING_KINDS = (
    KIND_UNINDEXED,
    KIND_AMBIGUOUS_INDEX,
    KIND_DIGEST_MISMATCH,
    KIND_MISSING,
)


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
class BucketReconcileReport(FindingsReport[BucketFinding]):
    """What the scan found — a report, never an action."""

    scanned_objects: int = 0
    scanned_records: int = 0
    buckets: tuple[str, ...] = ()
    #: True when the index was bigger than the read limit and the scan
    #: therefore did NOT see every row. A truncated scan that says
    #: "clean" is a lie told by omission — so the report carries the flag.
    truncated: bool = False

    def of_kind(self, kind: str) -> list[BucketFinding]:
        return [finding for finding in self.findings if finding.kind == kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "buckets": list(self.buckets),
            "scanned_objects": self.scanned_objects,
            "scanned_records": self.scanned_records,
            "truncated": self.truncated,
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


def _recorded_digest(record: Any) -> str:
    digests = getattr(record, "digests", {}) or {}
    return normalize_payload_digest(str(digests.get("payload_sha256", "") or ""))


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

    ``record_limit`` caps how many index rows are read. When the index is
    bigger than that cap, the scan is **incomplete** — and it says so in
    ``report.truncated`` rather than quietly reporting on a prefix. (The
    real index on this machine holds 1420 rows; a default cap of 1000
    would have hidden 420 of them.)
    """
    report = BucketReconcileReport(buckets=tuple(buckets))

    # Every row that names an object — several rows may name the same one,
    # and that is a finding of its own, not something to resolve silently.
    indexed: dict[str, list[Any]] = {}
    for record in metadata.list(limit=record_limit):
        report.scanned_records += 1
        ref = normalize_object_ref(getattr(record, "object_ref", "") or "")
        if ref:
            indexed.setdefault(ref, []).append(record)
    report.truncated = report.scanned_records >= record_limit

    seen: set[str] = set()
    for bucket in buckets:
        for name, _size, _digest in objects.list_bucket_objects(bucket):
            report.scanned_objects += 1
            ref = f"{bucket}/{name}"
            seen.add(ref)
            records = indexed.get(ref)
            if not records:
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

            digests = {digest for digest in (_recorded_digest(r) for r in records) if digest}
            if len(records) > 1 and len(digests) > 1:
                report.findings.append(
                    BucketFinding(
                        kind=KIND_AMBIGUOUS_INDEX,
                        bucket=bucket,
                        object_name=name,
                        detail=(
                            f"{len(records)} index rows point at this object and "
                            f"they disagree about its digest ({len(digests)} distinct "
                            "values) — the index has no single word here, so this is "
                            "reported instead of resolved"
                        ),
                    )
                )
                continue
            if not digests:
                continue
            recorded = next(iter(digests))
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
