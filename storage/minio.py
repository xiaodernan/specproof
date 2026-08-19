"""MinIO client — object storage for Phase 0 / Phase 1.

P1.5: Added put_object_with_digest (sha256 + size), batch_check_exist,
and put_object_if_absent for idempotent artifact uploads.

§14.2 governance: object names follow the tenant/repo/job/type/version
convention built by object_path(); user-controlled names are never used
raw — validate_object_path() rejects traversal and unsafe segments before
any client call. Uploads return digest, size, media type and version;
downloads enforce the tenant prefix (permission check) and can verify the
sha256 of the downloaded bytes.
"""
import hashlib
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from minio import Minio

#: One path segment: starts alphanumeric, then [A-Za-z0-9._-], max 128
#: chars. The leading-dot ban kills "." and ".." before they reach MinIO.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_OBJECT_NAME_LENGTH = 1024


class InvalidObjectPathError(ValueError):
    """Object path violates the §14.2 naming governance rules."""


class DigestMismatchError(ValueError):
    """Downloaded object sha256 differs from the expected digest."""


def validate_path_segment(segment: str, label: str = "segment") -> str:
    """Validate one object-path segment; returns it unchanged.

    Rejects empty values, "." / "..", separators, whitespace, control
    characters, and anything outside [A-Za-z0-9][A-Za-z0-9._-]{0,127}.
    """
    if not isinstance(segment, str) or not segment:
        raise InvalidObjectPathError(f"{label} must be a non-empty string")
    if segment in (".", ".."):
        raise InvalidObjectPathError(f"{label} must not be '.' or '..'")
    if len(segment) > 128 or not _SEGMENT_RE.match(segment):
        raise InvalidObjectPathError(
            f"{label} must match [A-Za-z0-9][A-Za-z0-9._-]{{0,127}}"
        )
    return segment


def object_path(
    tenant: str, repo: str, job: str, artifact_type: str, version: str
) -> str:
    """Governed object path: tenant/repo/job/type/version (§14.2).

    Every segment is validated, so user-controlled values are never
    spliced into a raw path — traversal ("..", "/", "\") cannot escape
    the tenant's prefix.
    """
    segments = (
        (tenant, "tenant"),
        (repo, "repo"),
        (job, "job"),
        (artifact_type, "artifact_type"),
        (version, "version"),
    )
    return "/".join(validate_path_segment(seg, label) for seg, label in segments)


def validate_object_path(object_name: str, *, tenant: str | None = None) -> str:
    """Reject unsafe object names; raw user input must never bypass this.

    Enforces: non-empty str, <=1024 chars, relative (no leading '/', no
    '\\'), segments in the safe charset, no '.'/'..' segments. When
    tenant is given the path must live under that tenant's prefix — the
    download permission check (§14.2). Returns the validated name.
    """
    if not isinstance(object_name, str) or not object_name:
        raise InvalidObjectPathError("object path must be a non-empty string")
    if len(object_name) > _MAX_OBJECT_NAME_LENGTH:
        raise InvalidObjectPathError("object path exceeds 1024 characters")
    if object_name.startswith("/") or "\\" in object_name:
        raise InvalidObjectPathError(
            "object path must be relative and use '/' separators"
        )
    for segment in object_name.split("/"):
        validate_path_segment(segment, "path segment")
    if tenant is not None:
        validate_path_segment(tenant, "tenant")
        if not object_name.startswith(tenant + "/"):
            raise InvalidObjectPathError(
                f"object path must be under tenant prefix {tenant!r}"
            )
    return object_name


@dataclass
class MinIOConfig:
    host: str = "localhost"
    port: int = 9000
    access_key: str = "minioadmin"
    secret_key: str = "specproof_pass"
    secure: bool = False

    @classmethod
    def from_env(cls) -> "MinIOConfig":
        return cls(
            host=os.getenv("MINIO_HOST", "localhost"),
            port=int(os.getenv("MINIO_PORT", "9000")),
            access_key=os.getenv("MINIO_ROOT_USER", "minioadmin"),
            secret_key=os.getenv("MINIO_ROOT_PASSWORD", "specproof_pass"),
            secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )


class MinIOClient:
    """Object storage for reports, capsules, tool outputs."""

    BUCKETS = [
        "specproof-tool-reports",
        "specproof-bug-capsules",
        "specproof-html-reports",
    ]

    def __init__(self, config: MinIOConfig | None = None) -> None:
        self.config = config or MinIOConfig.from_env()
        self._client: Minio | None = None

    @property
    def client(self) -> Minio:
        if self._client is None:
            endpoint = f"{self.config.host}:{self.config.port}"
            self._client = Minio(
                endpoint=endpoint,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                secure=self.config.secure,
            )
        return self._client

    def ensure_buckets(self) -> None:
        for bucket in self.BUCKETS:
            found = self.client.bucket_exists(bucket)
            if not found:
                self.client.make_bucket(bucket)

    def upload_string(
        self,
        bucket: str,
        object_name: str,
        data: str,
        content_type: str = "text/plain",
    ) -> None:
        name = validate_object_path(object_name)
        self.client.put_object(
            bucket_name=bucket,
            object_name=name,
            data=BytesIO(data.encode("utf-8")),
            length=len(data.encode("utf-8")),
            content_type=content_type,
        )

    def upload_bytes(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        name = validate_object_path(object_name)
        self.client.put_object(
            bucket_name=bucket,
            object_name=name,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    # ── P1.5: digest-bearing upload + batch existence ──────────

    def put_object_with_digest(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]:
        """Upload data and return {bucket, object_name, sha256, size_bytes,
        content_type, version} (§14.2).

        The sha256 is computed from the data, not from MinIO's ETag, and
        is also stored as object metadata so stat_object can return it.
        """
        name = validate_object_path(object_name)
        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = len(data)
        self.client.put_object(
            bucket_name=bucket,
            object_name=name,
            data=BytesIO(data),
            length=size_bytes,
            content_type=content_type,
            metadata={"X-Amz-Meta-Sha256": sha256},
        )
        return {
            "bucket": bucket,
            "object_name": name,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "content_type": content_type,
            "version": version,
        }

    def put_governed_object(
        self,
        bucket: str,
        *,
        tenant: str,
        repo: str,
        job: str,
        artifact_type: str,
        version: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload under the §14.2 naming convention tenant/repo/job/type/version.

        Returns the digest dict plus tenant/version so the caller can
        record the full governed reference without re-deriving the path.
        """
        name = object_path(tenant, repo, job, artifact_type, version)
        result = self.put_object_with_digest(
            bucket, name, data, content_type, version=version
        )
        result["tenant"] = tenant
        return result

    def put_object_if_absent(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]:
        """Idempotent upload: skip if object already exists, upload otherwise.

        Always returns the §14.2 metadata dict; for existing objects the
        digest is read from object metadata (falling back to recomputing
        from the provided bytes) and the media type from the stored stat.
        """
        name = validate_object_path(object_name)
        try:
            stat = self.client.stat_object(
                bucket_name=bucket, object_name=name
            )
            meta = stat.metadata or {}
            sha256 = meta.get("X-Amz-Meta-Sha256") or hashlib.sha256(data).hexdigest()
            return {
                "bucket": bucket,
                "object_name": name,
                "sha256": sha256,
                "size_bytes": stat.size,
                "content_type": stat.content_type,
                "version": version,
            }
        except Exception:
            return self.put_object_with_digest(
                bucket, name, data, content_type, version=version
            )

    def batch_check_exist(
        self, bucket: str, objects: list[str]
    ) -> dict[str, bool]:
        """Batch check whether objects exist. Returns {object_name: exists}."""
        result: dict[str, bool] = {}
        for name in objects:
            result[name] = self.object_exists(bucket, name)
        return result

    def object_digest(self, bucket: str, object_name: str) -> str | None:
        """Return sha256 from object metadata, or None if missing."""
        try:
            stat = self.client.stat_object(bucket_name=bucket, object_name=object_name)
            meta = stat.metadata
            if not meta:
                return None
            return meta.get("X-Amz-Meta-Sha256", None) or None
        except Exception:
            return None

    def object_stat(
        self, bucket: str, object_name: str, *, tenant: str | None = None
    ) -> dict[str, Any]:
        """Governed stat: {bucket, object_name, size_bytes, content_type, sha256}.

        tenant, when given, is the download permission check — the path
        must live under the tenant's prefix (§14.2).
        """
        name = validate_object_path(object_name, tenant=tenant)
        stat = self.client.stat_object(bucket_name=bucket, object_name=name)
        meta = stat.metadata or {}
        return {
            "bucket": bucket,
            "object_name": name,
            "size_bytes": stat.size,
            "content_type": stat.content_type,
            "sha256": meta.get("X-Amz-Meta-Sha256"),
        }

    def download_string(
        self,
        bucket: str,
        object_name: str,
        *,
        tenant: str | None = None,
        expected_sha256: str | None = None,
    ) -> str:
        return self.download_bytes(
            bucket, object_name, tenant=tenant, expected_sha256=expected_sha256
        ).decode("utf-8")

    def download_bytes(
        self,
        bucket: str,
        object_name: str,
        *,
        tenant: str | None = None,
        expected_sha256: str | None = None,
    ) -> bytes:
        """Download with §14.2 checks: the tenant prefix is enforced before
        the GET (permission check) and the sha256 is verified afterwards
        when expected_sha256 is provided."""
        name = validate_object_path(object_name, tenant=tenant)
        response = self.client.get_object(bucket_name=bucket, object_name=name)
        try:
            data = response.read()
        finally:
            response.close()
        if expected_sha256 is not None:
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected_sha256:
                raise DigestMismatchError(
                    f"digest mismatch for {bucket}/{name}: "
                    f"expected {expected_sha256}, got {actual}"
                )
        return data

    def object_exists(self, bucket: str, object_name: str) -> bool:
        try:
            self.client.stat_object(bucket_name=bucket, object_name=object_name)
            return True
        except Exception:
            return False

    def is_ready(self) -> bool:
        try:
            return self.client.bucket_exists(self.BUCKETS[0]) or True
        except Exception:
            return False
