"""The bucket-side reconciler, against a REAL bucket and a REAL index.

``evidence/bucket_reconcile.py`` closes a gap the artifact store's own
docstring pointed at: it promises that a ghost object (uploaded, never
indexed) is "recoverable by the reconciliation scan", but the scan that
existed (``evidence/orphan_scan.py``) walks the LOCAL payload directory —
nothing listed the buckets.

These legs put a real MinIO bucket and a real SQLite index behind the
reconciler and assert the three findings it claims to make:

  * ``unindexed`` — the ghost: bytes in the bucket, no index row;
  * ``missing`` — the index points at an object that is not there;
  * ``digest_mismatch`` — the object is there, but its bytes no longer hash
    to the recorded digest.

and one property that matters more than the findings themselves: the scan
**removes nothing**. A reconciler that deleted what it called a ghost would
destroy evidence on the strength of a heuristic — the rule the local
``orphan_scan`` already follows.

Isolation: a scratch bucket of this file's own; the production buckets are
never listed for deletion and never written to.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from pathlib import Path

import pytest

from evidence.bucket_reconcile import (
    KIND_DIGEST_MISMATCH,
    KIND_MISSING,
    KIND_UNINDEXED,
    reconcile_buckets,
)
from storage.minio import MinIOClient
from storage.object_metadata import (
    SQLiteObjectMetadataStore,
    new_metadata,
    payload_sha256_of_file,
)

BUCKET = "specproof-test-bucket-reconcile"


@pytest.fixture
def minio_client() -> MinIOClient:
    client = MinIOClient()
    try:
        client.client.bucket_exists(BUCKET)
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no MinIO here"
        pytest.skip(f"MinIO not available for the reconcile leg: {exc}")
    with suppress(Exception):  # the bucket may already exist
        client.client.make_bucket(BUCKET)
    try:
        yield client
    finally:
        try:
            for obj in client.client.list_objects(BUCKET, recursive=True):
                client.client.remove_object(BUCKET, obj.object_name)
            client.client.remove_bucket(BUCKET)
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass


def _payload(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _upload(minio_client: MinIOClient, name: str, data: bytes) -> str:
    """Put an object into the scratch bucket and return its digest."""
    digest = hashlib.sha256(data).hexdigest()
    minio_client.client.put_object(
        bucket_name=BUCKET,
        object_name=name,
        data=__import__("io").BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
        metadata={"X-Amz-Meta-Sha256": digest},
    )
    return digest


def test_an_unindexed_object_is_reported_as_a_ghost(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    _upload(minio_client, "ghost/capsule.zip", b"ghost-bytes")
    store = SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")

    report = reconcile_buckets(minio_client, store, [BUCKET])

    assert report.is_clean() is False
    ghosts = report.of_kind(KIND_UNINDEXED)
    assert len(ghosts) == 1
    assert ghosts[0].object_name == "ghost/capsule.zip"
    assert ghosts[0].bucket == BUCKET


def test_an_index_row_pointing_at_nothing_is_reported_as_missing(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    store = SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")
    store.record(
        new_metadata(
            "capsule",  # type: ignore[arg-type]
            {"payload_sha256": "0" * 64},
            job_id="job-missing",
            path_hint=str(tmp_path / "gone.zip"),
            object_ref=f"{BUCKET}/not-there.zip",
        )
    )

    report = reconcile_buckets(minio_client, store, [BUCKET])

    missing = report.of_kind(KIND_MISSING)
    assert len(missing) == 1
    assert missing[0].object_name == "not-there.zip"


def test_changed_bytes_are_reported_as_a_digest_mismatch(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    data = b"the-original-bytes"
    digest = _upload(minio_client, "capsule/changed.zip", data)
    store = SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")
    store.record(
        new_metadata(
            "capsule",  # type: ignore[arg-type]
            {"payload_sha256": digest},
            job_id="job-changed",
            path_hint=str(tmp_path / "capsule.zip"),
            object_ref=f"{BUCKET}/capsule/changed.zip",
        )
    )

    # The bytes change after they were recorded.
    _upload(minio_client, "capsule/changed.zip", b"the-tampered-bytes")

    report = reconcile_buckets(minio_client, store, [BUCKET])

    mismatches = report.of_kind(KIND_DIGEST_MISMATCH)
    assert len(mismatches) == 1
    assert mismatches[0].object_name == "capsule/changed.zip"


def test_a_clean_bucket_reports_nothing(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    data = b"intact-bytes"
    _upload(minio_client, "capsule/intact.zip", data)
    store = SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")
    payload = _payload(tmp_path, "capsule.zip", data)
    store.record(
        new_metadata(
            "capsule",  # type: ignore[arg-type]
            {"payload_sha256": payload_sha256_of_file(payload)},
            job_id="job-intact",
            path_hint=str(payload),
            object_ref=f"{BUCKET}/capsule/intact.zip",
        )
    )

    report = reconcile_buckets(minio_client, store, [BUCKET])

    assert report.is_clean() is True, (
        f"a clean bucket reported {report.findings!r}"
    )
    assert report.scanned_objects == 1
    assert report.scanned_records == 1


def test_the_scan_removes_nothing(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    """A reconciler that deleted what it called a ghost would destroy evidence.

    The ghost stays in the bucket after the scan, and the report says so.
    """
    _upload(minio_client, "ghost/keep-me.zip", b"evidence")
    store = SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")

    report = reconcile_buckets(minio_client, store, [BUCKET])

    assert len(report.of_kind(KIND_UNINDEXED)) == 1
    assert minio_client.object_exists(BUCKET, "ghost/keep-me.zip") is True, (
        "the scan deleted the object it reported — a scan is a report, "
        "removal is a separate, explicit act"
    )
