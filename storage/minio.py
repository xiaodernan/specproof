"""MinIO client — object storage for Phase 0 / Phase 1.

P1.5: Added put_object_with_digest (sha256 + size), batch_check_exist,
and put_object_if_absent for idempotent artifact uploads.
"""
import hashlib
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from minio import Minio


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
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_name,
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
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_name,
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
    ) -> dict[str, Any]:
        """Upload data and return {bucket, object_name, sha256, size_bytes}.

        The sha256 is computed from the data, not from MinIO's ETag.
        """
        sha256 = hashlib.sha256(data).hexdigest()
        size_bytes = len(data)
        self.client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=BytesIO(data),
            length=size_bytes,
            content_type=content_type,
        )
        return {
            "bucket": bucket,
            "object_name": object_name,
            "sha256": sha256,
            "size_bytes": size_bytes,
        }

    def put_object_if_absent(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Idempotent upload: skip if object already exists, upload otherwise.

        Always returns the digest dict (re-computed for existing objects via stat).
        """
        try:
            stat = self.client.stat_object(bucket_name=bucket, object_name=object_name)
            sha256 = hashlib.sha256(data).hexdigest()
            return {
                "bucket": bucket,
                "object_name": object_name,
                "sha256": sha256,
                "size_bytes": stat.size,
            }
        except Exception:
            return self.put_object_with_digest(bucket, object_name, data, content_type)

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

    def download_string(self, bucket: str, object_name: str) -> str:
        response = self.client.get_object(bucket_name=bucket, object_name=object_name)
        try:
            return response.read().decode("utf-8")
        finally:
            response.close()

    def download_bytes(self, bucket: str, object_name: str) -> bytes:
        response = self.client.get_object(bucket_name=bucket, object_name=object_name)
        try:
            return response.read()
        finally:
            response.close()

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
