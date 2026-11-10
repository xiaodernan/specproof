"""The artifact store's failure seam, against a REAL object store.

What was measured before this file existed
-------------------------------------------
``storage/artifact_store.py`` is explicit about the hole it guards: the
upload can succeed while the index row fails, and the result then has to
say which of the two happened. Its own docstring calls the leftover a
"ghost" and points at the reconciliation scan.

The unit tests for it (``tests/unit/test_artifact_store*``) drive it with a
fake object client and a fake metadata store — the logic is proven, but
"the compensation really removed the bytes" and "the object really was
durable in the bucket" are statements about a double. The P1-B queue still
carried the branch's placeholder for exactly this (``test_orphan_objects_detected``,
"P1.5 artifact consistency deferred to P1-B").

What this file does
-------------------
It puts a **real MinIO** bucket and a **real SQLite metadata store** behind
the production ``ArtifactStore`` and asserts the two halves of the seam:

  1. **The happy path is real**: the bytes land in the bucket, the index
     row lands in the SQLite file, and the object's digest read back from
     the bucket equals the digest of the local file.
  2. **The compensation really deletes**: the upload succeeds, the index
     write fails, and in strict mode the object is gone from the bucket —
     checked with a real ``stat_object``, not with the double's log.
  3. **The ghost is real when the caller wants the bytes kept**: in
     non-strict mode the object survives in the bucket, the result names
     it, and it says the index row is missing — which is exactly the
     condition a reconciliation scan has to find.

Isolation
---------
A scratch bucket of this file's own is created and removed afterwards; the
production buckets are never touched. MinIO being unreachable makes the legs
skip with the real reason rather than pass vacuously. The metadata store is a
SQLite file under ``tmp_path`` — a real, persistent backend, not the
in-memory double the rest of the suite uses.
"""

from __future__ import annotations

import uuid
from contextlib import suppress
from pathlib import Path

import pytest

from storage.artifact_store import ArtifactStore
from storage.minio import MinIOClient
from storage.object_metadata import SQLiteObjectMetadataStore

#: The scratch bucket this file owns. The production buckets are never used.
BUCKET = "specproof-test-artifact-ghost"


class _FailingMetadataStore:
    """Wraps a real store and fails exactly one call — the index write.

    The underlying store is real (SQLite on disk); only this one operation
    is made to fail, because "the database was down" is not something a
    test can arrange honestly without breaking the machine.
    """

    def __init__(self, inner: SQLiteObjectMetadataStore) -> None:
        self._inner = inner

    def record(self, *args: object, **kwargs: object) -> object:
        raise RuntimeError("index write failed (injected)")

    def __getattr__(self, name: str) -> object:  # pragma: no cover - delegation
        return getattr(self._inner, name)


@pytest.fixture
def minio_client() -> MinIOClient:
    """A real MinIO client, skipped when the object store is unreachable."""
    client = MinIOClient()
    try:
        client.client.bucket_exists(BUCKET)
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no MinIO here"
        pytest.skip(f"MinIO not available for the artifact leg: {exc}")
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


def _payload(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"artifact-bytes-for-the-ghost-leg")
    return path


def test_a_real_upload_lands_in_the_bucket_and_the_index(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    store = ArtifactStore(
        objects=minio_client,
        metadata=SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3"),
        bucket=BUCKET,
    )
    payload = _payload(tmp_path, "capsule.zip")
    object_name = f"ghost-leg/{uuid.uuid4().hex[:12]}.zip"

    result = store.put_file(
        payload,
        kind="capsule",
        object_name=object_name,
        job_id="job-real",
    )

    assert result.metadata_recorded is True
    assert result.metadata_error == ""
    assert result.is_consistent is True
    # The bytes are really in the bucket, and their digest is the file's.
    assert minio_client.object_exists(BUCKET, object_name) is True
    assert minio_client.object_digest(BUCKET, object_name) == result.sha256


def test_strict_mode_really_deletes_the_object_when_the_index_write_fails(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    store = ArtifactStore(
        objects=minio_client,
        metadata=_FailingMetadataStore(SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")),
        bucket=BUCKET,
    )
    payload = _payload(tmp_path, "capsule-strict.zip")
    object_name = f"ghost-leg/{uuid.uuid4().hex[:12]}-strict.zip"

    result = store.put_file(
        payload,
        kind="capsule",
        object_name=object_name,
        job_id="job-strict",
        strict=True,
    )

    assert result.metadata_recorded is False
    assert "index write failed" in result.metadata_error
    assert result.compensated is True, (
        "strict mode promised to remove the uploaded object; the result says "
        f"compensated={result.compensated} / error={result.compensation_error!r}"
    )
    # The compensation is not a claim about a double: the bucket is asked.
    assert minio_client.object_exists(BUCKET, object_name) is False, (
        "the object is still in the bucket — the ghost the strict mode was "
        "supposed to prevent is still there"
    )


def test_non_strict_mode_keeps_the_bytes_and_names_the_ghost(
    minio_client: MinIOClient, tmp_path: Path
) -> None:
    store = ArtifactStore(
        objects=minio_client,
        metadata=_FailingMetadataStore(SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")),
        bucket=BUCKET,
    )
    payload = _payload(tmp_path, "capsule-lenient.zip")
    object_name = f"ghost-leg/{uuid.uuid4().hex[:12]}-lenient.zip"

    result = store.put_file(
        payload,
        kind="capsule",
        object_name=object_name,
        job_id="job-lenient",
        strict=False,
    )

    assert result.metadata_recorded is False
    assert result.is_consistent is False, (
        "an unindexed object is not a consistent store — the result must say so"
    )
    assert minio_client.object_exists(BUCKET, object_name) is True, (
        "non-strict mode keeps the bytes (they are the evidence); if they are "
        "gone the caller has neither the index row nor the artifact"
    )
    assert result.object_name == object_name
    assert any("orphan" in note for note in result.notes), (
        f"the result does not say the object is an orphan: {result.notes!r}"
    )
