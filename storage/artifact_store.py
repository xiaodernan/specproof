"""Artifact store: object upload + metadata index, with an honest failure seam.

P3-7 fault injection: "对象上传成功后写库失败".

This is the classic two-store hole. The artifact bytes live in object
storage; the index row that makes them FINDABLE lives in a database.
Upload-then-record has two failure windows:

* the upload fails — nothing was written, the caller must know;
* the upload succeeds and the RECORD fails — the bytes are durable and
  verifiable by their digest, but nothing points at them. A silent
  ``except: pass`` here turns a recoverable inconsistency into a ghost:
  the object exists, nothing knows it, and the evidence chain has a hole
  nobody can find.

This module makes the second case explicit instead of swallowing it. The
result ALWAYS states what actually happened:

``metadata_recorded``
    True when the index row was written.

``metadata_error``
    Why it was not, when it was not.

``compensated``
    True when the uploaded object was removed again (strict mode). A
    compensation is a DELETE and it can itself fail — that failure is
    reported, never hidden.

Two modes, both honest:

``strict=True``
    The caller wants all-or-nothing. A metadata failure triggers a
    compensating delete of the uploaded object, so the store does not
    accumulate ghosts. If the compensation fails, the result says so and
    the object remains — recoverable by the reconciliation scan.

``strict=False``
    The caller wants the artifact kept (it is the durable evidence; the
    index is a convenience). The result says the index write failed and
    names the object so a later reconciliation can find it.

Nothing here raises for a metadata failure: the caller gets a result it
can act on. The MinIO upload failure DOES raise — there is no artifact
to describe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from storage.object_metadata import (
    ObjectKind,
    ObjectMetadata,
    ObjectMetadataStore,
    new_metadata,
    payload_sha256_of_file,
)

logger = logging.getLogger(__name__)


class ObjectStoreLike(Protocol):
    """The slice of the MinIO client this module uses."""

    def put_object_with_digest(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]: ...

    def remove_object(self, bucket: str, object_name: str) -> None: ...


@dataclass
class ArtifactResult:
    """What actually happened when one artifact was stored."""

    bucket: str
    object_name: str
    sha256: str
    size_bytes: int
    content_type: str
    metadata_recorded: bool
    metadata_object_id: str = ""
    metadata_error: str = ""
    compensated: bool = False
    compensation_error: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def is_consistent(self) -> bool:
        """True when the bytes and the index agree.

        False in two cases, both real: the index write failed (a ghost
        until reconciled) and the compensation failed (a ghost that
        reconciliation MUST find).
        """
        return self.metadata_recorded and not self.compensation_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "object_name": self.object_name,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "metadata_recorded": self.metadata_recorded,
            "metadata_object_id": self.metadata_object_id,
            "metadata_error": self.metadata_error,
            "compensated": self.compensated,
            "compensation_error": self.compensation_error,
            "is_consistent": self.is_consistent,
            "notes": list(self.notes),
        }


class ArtifactStore:
    """Store an artifact and index it, reporting the truth about both."""

    def __init__(
        self,
        objects: ObjectStoreLike,
        metadata: ObjectMetadataStore,
        *,
        bucket: str = "specproof",
    ) -> None:
        self._objects = objects
        self._metadata = metadata
        self._bucket = bucket

    def put_file(
        self,
        path: str | Path,
        *,
        kind: ObjectKind,
        object_name: str,
        job_id: str = "",
        contract_ids: tuple[str, ...] = (),
        content_type: str = "application/octet-stream",
        version: str | None = None,
        strict: bool = False,
    ) -> ArtifactResult:
        """Upload the file at *path* and index it.

        The upload itself failing RAISES (there is no artifact to
        describe). A metadata failure does not raise: it is reported on
        the result, and in strict mode the uploaded object is removed
        again so the store does not keep ghosts.
        """
        source = Path(path)
        data = source.read_bytes()
        digest = {
            "payload_sha256": payload_sha256_of_file(source),
        }

        uploaded = self._objects.put_object_with_digest(
            self._bucket, object_name, data, content_type, version
        )

        # The coordinate the bucket understands (P1-7): the record
        # must say where the bytes ARE, not only where the file was
        # when it was uploaded. A path hint alone cannot be
        # resolved on the machine that holds the bucket.
        stored_bucket = str(uploaded.get("bucket") or self._bucket)
        stored_name = str(uploaded.get("object_name") or object_name)

        try:
            record = self._metadata.record(
                new_metadata(
                    kind,
                    digest,
                    job_id=job_id,
                    contract_ids=contract_ids,
                    path_hint=str(source),
                    object_ref=f"{stored_bucket}/{stored_name}",
                )
            )
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            logger.warning(
                "artifact uploaded but its metadata record failed (%s: %s) — "
                "the object %s/%s is durable but unindexed",
                type(exc).__name__, exc, self._bucket, object_name,
            )
            result = ArtifactResult(
                bucket=str(uploaded.get("bucket") or self._bucket),
                object_name=str(uploaded.get("object_name") or object_name),
                sha256=str(uploaded.get("sha256") or ""),
                size_bytes=int(uploaded.get("size_bytes") or 0),
                content_type=str(uploaded.get("content_type") or content_type),
                metadata_recorded=False,
                metadata_error=f"{type(exc).__name__}: {exc}",
            )
            if strict:
                self._compensate(result)
            else:
                result.notes.append(
                    "the object is durable and verifiable by its digest, but "
                    "no index row points at it — a reconciliation scan will "
                    "find it as an orphan"
                )
            return result

        return ArtifactResult(
            bucket=str(uploaded.get("bucket") or self._bucket),
            object_name=str(uploaded.get("object_name") or object_name),
            sha256=str(uploaded.get("sha256") or ""),
            size_bytes=int(uploaded.get("size_bytes") or 0),
            content_type=str(uploaded.get("content_type") or content_type),
            metadata_recorded=True,
            metadata_object_id=record.object_id,
        )

    def _compensate(self, result: ArtifactResult) -> None:
        """Remove the uploaded object after a failed index write (strict mode).

        A compensation that itself fails is REPORTED, not swallowed: the
        object is still there and the reconciliation scan must find it.
        """
        try:
            self._objects.remove_object(result.bucket, result.object_name)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            result.compensation_error = f"{type(exc).__name__}: {exc}"
            result.notes.append(
                "the compensating delete failed — the object remains and must "
                "be found by a reconciliation scan"
            )
            logger.warning(
                "compensating delete failed for %s/%s: %s",
                result.bucket, result.object_name, exc,
            )
            return
        result.compensated = True
        result.notes.append(
            "the uploaded object was removed again — the store holds no ghost"
        )

    def put_bytes(
        self,
        data: bytes,
        *,
        kind: ObjectKind,
        object_name: str,
        job_id: str = "",
        contract_ids: tuple[str, ...] = (),
        content_type: str = "application/octet-stream",
        version: str | None = None,
        strict: bool = False,
    ) -> ArtifactResult:
        """Upload raw bytes and index them (same contract as put_file)."""
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            handle.write(data)
            temp_path = Path(handle.name)
        try:
            return self.put_file(
                temp_path,
                kind=kind,
                object_name=object_name,
                job_id=job_id,
                contract_ids=contract_ids,
                content_type=content_type,
                version=version,
                strict=strict,
            )
        finally:
            temp_path.unlink(missing_ok=True)


def orphan_candidates(
    result: ArtifactResult,
) -> dict[str, str] | None:
    """The reconciliation hint for an unindexed artifact, or None.

    A reconciliation pass needs enough to FIND the object again: the
    bucket, the object name and the digest that proves what it is.
    """
    if result.metadata_recorded:
        return None
    return {
        "bucket": result.bucket,
        "object_name": result.object_name,
        "sha256": result.sha256,
    }


__all__ = [
    "ArtifactResult",
    "ArtifactStore",
    "ObjectMetadata",
    "ObjectStoreLike",
    "orphan_candidates",
]
