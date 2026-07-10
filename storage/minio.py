"""MinIO client — object storage for Phase 0."""

import os
from dataclasses import dataclass
from io import BytesIO

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
