"""Fault injection: the object upload succeeded, the index write failed (P3-7).

The two-store hole. The artifact bytes are durable in object storage; the
index row that makes them findable lives in a database. When the upload
succeeds and the record fails, a silent ``except: pass`` leaves a GHOST:
the object exists, nothing points at it, and the evidence chain has a hole
nobody can find.

These tests pin the honest behaviour:

- the result always states whether the index was written;
- the failure is never swallowed — the reason rides on the result;
- strict mode removes the object again (no ghost), and a failed
  compensation is REPORTED rather than hidden;
- non-strict mode keeps the object and hands back the reconciliation
  hint a scan needs to find it;
- an upload failure RAISES — there is no artifact to describe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from storage.artifact_store import ArtifactStore, orphan_candidates
from storage.object_metadata import InMemoryObjectMetadataStore


class FakeObjectStore:
    """A MinIO double: records uploads and deletes."""

    def __init__(self, *, fail_upload: bool = False, fail_remove: bool = False) -> None:
        self.fail_upload = fail_upload
        self.fail_remove = fail_remove
        self.objects: dict[tuple[str, str], bytes] = {}
        self.removed: list[tuple[str, str]] = []

    def put_object_with_digest(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]:
        if self.fail_upload:
            raise RuntimeError("minio unreachable")
        import hashlib

        self.objects[(bucket, object_name)] = data
        return {
            "bucket": bucket,
            "object_name": object_name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "content_type": content_type,
            "version": version,
        }

    def remove_object(self, bucket: str, object_name: str) -> None:
        if self.fail_remove:
            raise RuntimeError("minio refused the delete")
        self.objects.pop((bucket, object_name), None)
        self.removed.append((bucket, object_name))


class FailingMetadataStore:
    """A metadata store whose record() always fails."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or RuntimeError("mysql unavailable")
        self.attempts = 0

    def record(self, metadata: Any) -> Any:
        self.attempts += 1
        raise self.error

    def get(self, object_id: str) -> Any:
        return None

    def list(self, limit: int = 1000) -> list[Any]:
        return []

    def by_job(self, job_id: str) -> list[Any]:
        return []

    def by_kind(self, kind: str) -> list[Any]:
        return []

    def by_digest(self, digest: str) -> list[Any]:
        return []

    def by_contract(self, contract_id: str) -> list[Any]:
        return []


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "capsule.zip"
    path.write_bytes(b"PK\x03\x04 capsule bytes")
    return path


# ── the happy path ─────────────────────────────────────────────────────────


def test_upload_and_record_leaves_a_consistent_store(tmp_path: Path) -> None:
    objects = FakeObjectStore()
    metadata = InMemoryObjectMetadataStore()
    store = ArtifactStore(objects, metadata)  # type: ignore[arg-type]

    result = store.put_file(
        _artifact(tmp_path),
        kind="capsule",
        object_name="tenant/repo/job/capsule/1",
        job_id="job-1",
    )

    assert result.metadata_recorded is True
    assert result.is_consistent is True
    assert result.metadata_error == ""
    assert objects.objects  # the bytes are there
    assert len(metadata.list()) == 1  # and the index points at them


# ── the fault: upload OK, index write fails ────────────────────────────────


def test_metadata_failure_is_reported_not_swallowed(tmp_path: Path) -> None:
    objects = FakeObjectStore()
    metadata = FailingMetadataStore()
    store = ArtifactStore(objects, metadata)  # type: ignore[arg-type]

    result = store.put_file(
        _artifact(tmp_path),
        kind="capsule",
        object_name="tenant/repo/job/capsule/1",
    )

    assert result.metadata_recorded is False
    assert "mysql unavailable" in result.metadata_error
    assert result.is_consistent is False
    assert metadata.attempts == 1, "the record was actually attempted"


def test_non_strict_mode_keeps_the_object_and_hands_back_a_hint(
    tmp_path: Path,
) -> None:
    """The bytes are the evidence; the index is a convenience. Keep them,
    and say where they are so a reconciliation scan can find them."""
    objects = FakeObjectStore()
    store = ArtifactStore(objects, FailingMetadataStore())  # type: ignore[arg-type]

    result = store.put_file(
        _artifact(tmp_path),
        kind="capsule",
        object_name="tenant/repo/job/capsule/1",
    )

    assert objects.objects, "the object must survive in non-strict mode"
    assert objects.removed == []
    hint = orphan_candidates(result)
    assert hint is not None
    assert hint["object_name"] == "tenant/repo/job/capsule/1"
    assert hint["sha256"]


def test_strict_mode_removes_the_object_again(tmp_path: Path) -> None:
    """All-or-nothing: a failed index write must not leave a ghost."""
    objects = FakeObjectStore()
    store = ArtifactStore(objects, FailingMetadataStore())  # type: ignore[arg-type]

    result = store.put_file(
        _artifact(tmp_path),
        kind="capsule",
        object_name="tenant/repo/job/capsule/1",
        strict=True,
    )

    assert result.metadata_recorded is False
    assert result.compensated is True
    assert result.compensation_error == ""
    assert objects.objects == {}, "the compensating delete must have run"
    assert objects.removed == [("specproof", "tenant/repo/job/capsule/1")]


def test_a_failed_compensation_is_reported(tmp_path: Path) -> None:
    """The delete can fail too. Then the ghost REMAINS — and the result
    must say so, because a silent failure here hides the only evidence
    that something is inconsistent."""
    objects = FakeObjectStore(fail_remove=True)
    store = ArtifactStore(objects, FailingMetadataStore())  # type: ignore[arg-type]

    result = store.put_file(
        _artifact(tmp_path),
        kind="capsule",
        object_name="tenant/repo/job/capsule/1",
        strict=True,
    )

    assert result.compensated is False
    assert "minio refused the delete" in result.compensation_error
    assert result.is_consistent is False
    assert objects.objects, "the object really is still there"
    assert any("reconciliation scan" in note for note in result.notes)


def test_an_upload_failure_raises(tmp_path: Path) -> None:
    """No artifact exists, so there is nothing to describe — raise."""
    objects = FakeObjectStore(fail_upload=True)
    store = ArtifactStore(objects, InMemoryObjectMetadataStore())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="minio unreachable"):
        store.put_file(
            _artifact(tmp_path),
            kind="capsule",
            object_name="tenant/repo/job/capsule/1",
        )


def test_a_successful_upload_records_the_real_digest(tmp_path: Path) -> None:
    """The index must carry the digest of the bytes that were uploaded."""
    objects = FakeObjectStore()
    metadata = InMemoryObjectMetadataStore()
    store = ArtifactStore(objects, metadata)  # type: ignore[arg-type]

    result = store.put_file(
        _artifact(tmp_path),
        kind="capsule",
        object_name="tenant/repo/job/capsule/1",
    )

    record = metadata.list()[0]
    assert record.digests["payload_sha256"] == result.sha256


# ── the reconciliation seam ────────────────────────────────────────────────


def test_a_recorded_artifact_needs_no_reconciliation(tmp_path: Path) -> None:
    objects = FakeObjectStore()
    store = ArtifactStore(objects, InMemoryObjectMetadataStore())  # type: ignore[arg-type]
    result = store.put_file(
        _artifact(tmp_path), kind="capsule", object_name="t/r/j/c/1",
    )
    assert orphan_candidates(result) is None


def test_the_result_is_json_serializable(tmp_path: Path) -> None:
    import json

    objects = FakeObjectStore()
    store = ArtifactStore(objects, FailingMetadataStore())  # type: ignore[arg-type]
    result = store.put_file(
        _artifact(tmp_path), kind="capsule", object_name="t/r/j/c/1",
    )
    payload = json.dumps(result.to_dict())
    assert "metadata_recorded" in payload


def test_the_store_uses_the_given_metadata_backend(tmp_path: Path) -> None:
    """The store does not reach for a global — the backend is injected."""
    metadata = InMemoryObjectMetadataStore()
    objects = FakeObjectStore()
    store = ArtifactStore(objects, metadata)  # type: ignore[arg-type]
    store.put_file(_artifact(tmp_path), kind="capsule", object_name="t/r/j/c/1")
    # The injected backend is the one that was written to.
    assert len(metadata.list()) == 1
    assert metadata.list()[0].kind == "capsule"
