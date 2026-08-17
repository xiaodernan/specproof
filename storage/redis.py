"""Redis store — cache, locks, progress streams, lease, budget for Phase 1.

P1.4: Added Redis Streams for progress, worker lease, and LLM token budget.
All keys carry TTL — no permanent business state in Redis.
"""

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
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
    """Cache, locks, progress tracking, leases, and LLM budget. All keys have TTL."""

    # Stream MAXLEN: keep last ~1000 progress events per job
    STREAM_MAXLEN = 1000

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

    # ── Progress (deprecated simple key, kept for P0.5 compat) ─

    def set_progress(self, job_id: str, progress: dict[str, Any]) -> None:
        key = f"specproof:progress:{job_id}"
        self.client.setex(key, 600, json.dumps(progress))

    def get_progress(self, job_id: str) -> dict[str, Any] | None:
        key = f"specproof:progress:{job_id}"
        val = self.client.get(key)
        return json.loads(val) if val else None

    # ── Redis Stream: progress events ─────────────────────────

    def stream_key(self, job_id: str) -> str:
        return f"specproof:stream:job:{job_id}"

    def xadd_progress(self, job_id: str, node: str, status: str,
                      message: str = "", percent: float = 0.0) -> str:
        """Append a progress event to the job's stream. Returns the entry ID."""
        data = {
            "node": node,
            "status": status,  # "running", "completed", "failed"
            "at": datetime.now(UTC).isoformat(),
            "percent": str(percent),
            "message": message,
        }
        key = self.stream_key(job_id)
        entry_id = self.client.xadd(key, data, maxlen=self.STREAM_MAXLEN)
        # Set TTL on the stream key (24h)
        self.client.expire(key, 86400)
        return entry_id

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]:
        """Read progress events from the stream starting from from_id.

        Returns list of {id, node, status, at, percent, message} dicts.
        """
        key = self.stream_key(job_id)
        try:
            result = self.client.xread({key: from_id}, count=count)
            if not result:
                return []
            entries = []
            for stream_name, messages in result:
                for msg_id, fields in messages:
                    entries.append({
                        "id": msg_id,
                        "node": fields.get("node", ""),
                        "status": fields.get("status", ""),
                        "at": fields.get("at", ""),
                        "percent": float(fields.get("percent", 0)),
                        "message": fields.get("message", ""),
                    })
            return entries
        except redis.ResponseError:
            return []

    def stream_length(self, job_id: str) -> int:
        try:
            return self.client.xlen(self.stream_key(job_id))
        except redis.ResponseError:
            return 0

    # ── Worker lease ──────────────────────────────────────────

    def lease_key(self, job_id: str) -> str:
        return f"specproof:lease:job:{job_id}"

    def acquire_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool:
        """Try to acquire a lease for job_id. Returns True if acquired."""
        key = self.lease_key(job_id)
        # SET NX: only succeeds if key doesn't exist
        return bool(self.client.set(key, worker_id, nx=True, ex=ttl))

    def renew_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool:
        """Renew an existing lease. Worker must own the lease."""
        key = self.lease_key(job_id)
        current = self.client.get(key)
        if current != worker_id:
            return False
        self.client.expire(key, ttl)
        return True

    def release_lease(self, job_id: str, worker_id: str) -> None:
        """Release a lease. Only releases if owned by worker_id (Lua safety)."""
        key = self.lease_key(job_id)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        self.client.eval(lua_script, 1, key, worker_id)

    def get_lease_owner(self, job_id: str) -> str | None:
        """Return the worker_id that holds the lease, or None."""
        return self.client.get(self.lease_key(job_id))

    # ── LLM Token budget ──────────────────────────────────────

    def budget_key(self, job_id: str) -> str:
        return f"specproof:budget:job:{job_id}"

    def init_budget(self, job_id: str, max_tokens: int) -> None:
        """Initialize the token budget for a job."""
        key = self.budget_key(job_id)
        self.client.set(key, str(max_tokens), ex=7200)

    def consume_budget(self, job_id: str, tokens: int) -> bool:
        """Consume tokens from the budget. Returns False if budget exceeded."""
        key = self.budget_key(job_id)
        remaining = self.client.decrby(key, tokens)
        if remaining < 0:
            self.client.incrby(key, tokens)  # rollback
            return False
        return True

    def check_budget(self, job_id: str) -> int:
        """Return remaining budget tokens. -1 if budget not initialized."""
        val = self.client.get(self.budget_key(job_id))
        return int(val) if val else -1

    # ── Lock ──────────────────────────────────────────────────

    def acquire_lock(self, job_id: str, ttl: int = 300) -> bool:
        key = f"specproof:lock:job:{job_id}"
        return bool(self.client.set(key, "1", nx=True, ex=ttl))

    def release_lock(self, job_id: str) -> None:
        key = f"specproof:lock:job:{job_id}"
        self.client.delete(key)

    # ── Cache ─────────────────────────────────────────────────

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

    # ── idempotency ───────────────────────────────────────────

    def set_idempotent(self, event_id: str, ttl: int = 86400) -> bool:
        """Mark an event as processed. Returns False if already processed."""
        key = f"specproof:idempotent:{event_id}"
        return bool(self.client.set(key, "1", nx=True, ex=ttl))

    def is_idempotent(self, event_id: str) -> bool:
        """Check if an event has already been processed."""
        return bool(self.client.exists(f"specproof:idempotent:{event_id}"))

    # ── health ────────────────────────────────────────────────

    def is_ready(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
