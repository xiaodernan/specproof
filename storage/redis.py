"""Redis store — cache, locks, progress for Phase 0."""

import json
import os
from dataclasses import dataclass
from typing import Any

import redis


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    password: str = "specproof_pass"
    db: int = 0

    @classmethod
    def from_env(cls) -> "RedisConfig":
        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", "specproof_pass"),
            db=0,
        )


class RedisStore:
    """Cache, locks, progress tracking. All keys have TTL."""

    def __init__(self, config: RedisConfig | None = None) -> None:
        self.config = config or RedisConfig.from_env()
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password,
                db=self.config.db,
                decode_responses=True,
                socket_timeout=5,
            )
        return self._client

    def set_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        key = f"specproof:progress:{job_id}"
        self.client.setex(key, 600, json.dumps(progress))

    def get_progress(self, job_id: str) -> dict[str, Any] | None:
        key = f"specproof:progress:{job_id}"
        val = self.client.get(key)
        return json.loads(val) if val else None

    def acquire_lock(self, job_id: str, ttl: int = 300) -> bool:
        key = f"specproof:lock:job:{job_id}"
        return bool(self.client.set(key, "1", nx=True, ex=ttl))

    def release_lock(self, job_id: str) -> None:
        key = f"specproof:lock:job:{job_id}"
        self.client.delete(key)

    def cache_llm_response(self, cache_key: str, response: dict[str, Any], ttl: int = 3600) -> None:
        key = f"specproof:cache:model:{cache_key}"
        self.client.setex(key, ttl, json.dumps(response))

    def get_cached_llm_response(self, cache_key: str) -> dict[str, Any] | None:
        key = f"specproof:cache:model:{cache_key}"
        val = self.client.get(key)
        return json.loads(val) if val else None

    def cache_provider_capability(self, base_url_hash: str, capabilities: dict[str, Any]) -> None:
        key = f"specproof:capability:{base_url_hash}"
        self.client.setex(key, 86400, json.dumps(capabilities))

    def get_cached_provider_capability(self, base_url_hash: str) -> dict[str, Any] | None:
        key = f"specproof:capability:{base_url_hash}"
        val = self.client.get(key)
        return json.loads(val) if val else None

    def is_ready(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
