"""P1-7: the metadata record must say where the bytes ARE.

The object-metadata store could only answer "the payload lived at this
local path". But the payload lives in the OBJECT STORE, under
"bucket/object-name" — a coordinate the machine holding the bucket can
resolve and the local path cannot: the path is where the file WAS, the
object ref is where the bytes ARE.

Without it, an artifact uploaded to MinIO could not be found again by
the reference the bucket understands; the chain had to fall back to
path inference, which is exactly what this store exists to replace.

These tests pin:
- the record carries the object coordinate;
- a half-written coordinate is rejected instead of stored;
- the coordinate RESOLVES the record (the new capability);
- it survives a round trip through SQLite, including a store created
  BEFORE the column existed (the migration);
- the artifact store records the coordinate the upload actually
  reported — not the one that was asked for.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from storage.artifact_store import ArtifactStore
from storage.object_metadata import (
    InMemoryObjectMetadataStore,
    ObjectMetadataError,
    SQLiteObjectMetadataStore,
    new_metadata,
    normalize_object_ref,
    resolve_object,
)

BUCKET = "specproof"
OBJECT_NAME = "jobs/job-1/report.html"
OBJECT_REF = f"{BUCKET}/{OBJECT_NAME}"


def _meta(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "kind": "capsule",
        "digests": {"payload_sha256": "a" * 64},
        "job_id": "job-1",
        "contract_ids": ("AUTH-01",),
        "path_hint": "/tmp/capsule.zip",
    }
    fields.update(overrides)
    return new_metadata(**fields)


class FakeObjectStore:
    """A MinIO double that reports the coordinate it actually stored."""

    def __init__(self, *, stored_bucket: str = "", stored_name: str = "") -> None:
        self.stored_bucket = stored_bucket
        self.stored_name = stored_name
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object_with_digest(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]:
        import hashlib

        stored = self.stored_bucket or bucket
        name = self.stored_name or object_name
        self.objects[(stored, name)] = data
        return {
            "bucket": stored,
            "object_name": name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "content_type": content_type,
            "version": version,
        }

    def remove_object(self, bucket: str, object_name: str) -> None:
        self.objects.pop((bucket, object_name), None)


# ── the record ──────────────────────────────────────────────────────────────


def test_a_record_carries_the_object_reference() -> None:
    metadata = _meta(object_ref=OBJECT_REF)
    assert metadata.object_ref == OBJECT_REF
    assert metadata.path_hint == "/tmp/capsule.zip", (
        "the path hint is still recorded — the two coordinates answer "
        "different questions"
    )


def test_a_file_only_record_has_no_object_reference() -> None:
    assert _meta().object_ref == ""


@pytest.mark.parametrize(
    "value",
    ["bucket/", "/object-name", "object-name", "bucket//object-name"],
)
def test_a_half_written_reference_is_rejected(value: str) -> None:
    """A reference that names no bucket OR no object can never resolve.

    Storing it would be worse than not storing it: the row would look
    indexed, and every lookup would come back empty.
    """
    with pytest.raises(ObjectMetadataError):
        _meta(object_ref=value)


def test_the_reference_is_normalized() -> None:
    assert normalize_object_ref(f"  {OBJECT_REF}  ") == OBJECT_REF
    assert normalize_object_ref("") == ""


# ── the resolution (the new capability) ─────────────────────────────────────


def test_the_object_reference_resolves_the_record() -> None:
    store = InMemoryObjectMetadataStore()
    store.record(_meta(object_ref=OBJECT_REF))
    found = resolve_object(store, OBJECT_REF)
    assert found is not None
    assert found.object_ref == OBJECT_REF


def test_an_unknown_object_reference_resolves_to_nothing() -> None:
    store = InMemoryObjectMetadataStore()
    store.record(_meta(object_ref=OBJECT_REF))
    assert resolve_object(store, "specproof/jobs/other/report.html") is None


def test_the_reference_is_tried_before_the_path_hint() -> None:
    """The object coordinate is the one a different machine can use.

    The path hint is advisory; the object ref is the address. When both
    are present, the address wins.
    """
    store = InMemoryObjectMetadataStore()
    record = store.record(_meta(object_ref=OBJECT_REF))
    found = resolve_object(store, record.path_hint)
    assert found is not None
    assert found.object_id == record.object_id


# ── persistence, including the migration ───────────────────────────────────


def test_the_reference_survives_a_sqlite_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "objects.sqlite3"
    store = SQLiteObjectMetadataStore(db)
    record = store.record(_meta(object_ref=OBJECT_REF))
    store.close()

    reopened = SQLiteObjectMetadataStore(db)
    try:
        found = reopened.get(record.object_id)
        assert found is not None
        assert found.object_ref == OBJECT_REF
    finally:
        reopened.close()


def test_a_store_created_before_the_column_gets_it(tmp_path: Path) -> None:
    """The migration: an older store must not fail on the new column.

    CREATE TABLE IF NOT EXISTS never touches an existing table, so a
    store written by an older build would keep working until the first
    SELECT that names object_ref — and then fail with a column error
    that reads like corruption.
    """
    db = tmp_path / "legacy.sqlite3"
    legacy = sqlite3.connect(str(db))
    legacy.execute(
        "CREATE TABLE object_metadata ("
        "object_id VARCHAR(32) PRIMARY KEY, "
        "kind VARCHAR(32) NOT NULL, "
        "payload_sha256 VARCHAR(64) NOT NULL DEFAULT '', "
        "digests_json TEXT NOT NULL, "
        "job_id VARCHAR(128) NOT NULL DEFAULT '', "
        "contract_ids_json TEXT NOT NULL DEFAULT '[]', "
        "created_at REAL NOT NULL, "
        "path_hint TEXT NOT NULL DEFAULT '')"
    )
    legacy.commit()
    legacy.close()

    store = SQLiteObjectMetadataStore(db)
    try:
        record = store.record(_meta(object_ref=OBJECT_REF))
        found = store.get(record.object_id)
        assert found is not None
        assert found.object_ref == OBJECT_REF
    finally:
        store.close()


# ── the wiring: the artifact store records the coordinate ───────────────────


def test_the_artifact_store_records_the_object_coordinate(tmp_path: Path) -> None:
    payload = tmp_path / "report.html"
    payload.write_text("<html>ok</html>", encoding="utf-8")
    objects = FakeObjectStore()
    metadata = InMemoryObjectMetadataStore()
    store = ArtifactStore(objects, metadata, bucket=BUCKET)

    result = store.put_file(
        payload, kind="capsule", object_name=OBJECT_NAME, job_id="job-1",
    )

    assert result.metadata_recorded is True
    record = metadata.get(result.metadata_object_id)
    assert record is not None
    assert record.object_ref == OBJECT_REF


def test_the_recorded_coordinate_is_the_one_the_upload_reported(
    tmp_path: Path,
) -> None:
    """The bucket decides where the bytes are; the record must follow it.

    If the store renames or re-buckets the object, the recorded
    coordinate that names the REQUESTED name would point at nothing.
    """
    payload = tmp_path / "report.html"
    payload.write_text("<html>ok</html>", encoding="utf-8")
    objects = FakeObjectStore(stored_bucket="evidence", stored_name="moved.html")
    metadata = InMemoryObjectMetadataStore()
    store = ArtifactStore(objects, metadata, bucket=BUCKET)

    result = store.put_file(
        payload, kind="capsule", object_name=OBJECT_NAME, job_id="job-1",
    )

    record = metadata.get(result.metadata_object_id)
    assert record is not None
    assert record.object_ref == "evidence/moved.html"
    # And the object is findable by exactly that coordinate.
    assert resolve_object(metadata, "evidence/moved.html") is not None
