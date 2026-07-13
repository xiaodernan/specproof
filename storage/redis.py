"""Redis store — P1.4 locks, budgets, progress streams, and SSE support.

P0.5: cache, basic lock, provider capability cache
P1.4: Stream-based progress, token-based lock with Lua unlock,
      budget tracking, workspace lease, rate limiting.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import redis

logger = logging.getLogger(__name__)

# Lua script for safe lock release — only deletes if token matches
_SAFE_UNLOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


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


@dataclass
class BudgetSnapshot:
    tool_calls: int = 0
    llm_tokens: int = 0
    estimated_cost: float = 0.0
    experiments: int = 0
    elapsed_seconds: float = 0.0


class RedisStore:
    """Cache, locks, progress, budget, and stream support."""

    _safe_unlock: Any = None  # Registered Lua script handle

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

    # ── P0.5: Progress (simple key-value) ─────────────────────────

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

    # ── P1.4: Token-based lock with safe unlock ──────────────────

    def acquire_lock_token(self, resource: str, ttl: int = 30) -> str | None:
        """Acquire a lock with random token. Returns token on success, None on failure."""
        token = uuid.uuid4().hex
        key = f"specproof:lock:{resource}"
        acquired = self.client.set(key, token, nx=True, ex=ttl)
        return token if acquired else None

    def release_lock_token(self, resource: str, token: str) -> bool:
        """Release a lock only if the token matches (Lua atomic)."""
        key = f"specproof:lock:{resource}"
        if self._safe_unlock is None:
            self._safe_unlock = self.client.register_script(_SAFE_UNLOCK_SCRIPT)
        result = self._safe_unlock(keys=[key], args=[token])
        return bool(result)

    def renew_lock_token(self, resource: str, token: str, ttl: int = 30) -> bool:
        """Extend lock TTL if the token still matches."""
        key = f"specproof:lock:{resource}"
        current = self.client.get(key)
        if current == token:
            self.client.expire(key, ttl)
            return True
        return False

    # ── P1.4: Workspace lease ────────────────────────────────────

    def acquire_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool:
        key = f"specproof:lease:job:{job_id}"
        return bool(self.client.set(key, worker_id, nx=True, ex=ttl))

    def renew_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool:
        key = f"specproof:lease:job:{job_id}"
        current = self.client.get(key)
        if current == worker_id:
            self.client.expire(key, ttl)
            return True
        return False

    def release_lease(self, job_id: str, worker_id: str) -> bool:
        key = f"specproof:lease:job:{job_id}"
        current = self.client.get(key)
        if current == worker_id:
            self.client.delete(key)
            return True
        return False

    def get_lease_owner(self, job_id: str) -> str | None:
        key = f"specproof:lease:job:{job_id}"
        val: str | None = self.client.get(key)  # type: ignore[assignment]
        return val

    # ── P1.4: Budget tracking ────────────────────────────────────

    def init_budget(
        self,
        job_id: str,
        max_tokens: int = 100000,
        max_tool_calls: int = 500,
        max_cost: float = 5.0,
    ) -> None:
        key = f"specproof:budget:job:{job_id}"
        self.client.hset(
            key,
            mapping={
                "max_tokens": max_tokens,
                "llm_tokens": 0,
                "max_tool_calls": max_tool_calls,
                "tool_calls": 0,
                "max_cost": str(max_cost),
                "estimated_cost": "0.0",
                "experiments": 0,
                "started_at": str(time.time()),
            },
        )
        self.client.expire(key, 3600)

    def consume_budget(
        self,
        job_id: str,
        *,
        tokens: int = 0,
        tool_calls: int = 0,
        cost: float = 0.0,
        experiments: int = 0,
    ) -> bool:
        """Atomically increment budget counters. Returns True if within limits."""
        key = f"specproof:budget:job:{job_id}"
        pipe = self.client.pipeline()
        pipe.hgetall(key)
        pipe.hincrby(key, "llm_tokens", tokens)
        pipe.hincrby(key, "tool_calls", tool_calls)
        pipe.hincrbyfloat(key, "estimated_cost", cost)
        pipe.hincrby(key, "experiments", experiments)
        results = pipe.execute()
        prev = results[0]
        if not prev:
            return False
        cur_tokens = int(str(prev.get(b"llm_tokens", prev.get("llm_tokens", 0)))) + tokens
        max_tokens = int(str(prev.get(b"max_tokens", prev.get("max_tokens", 100000))))
        return cur_tokens <= max_tokens

    def get_budget(self, job_id: str) -> BudgetSnapshot:
        key = f"specproof:budget:job:{job_id}"
        data = self.client.hgetall(key)
        if not data:
            return BudgetSnapshot()
        return BudgetSnapshot(
            tool_calls=int(float(str(data.get("tool_calls", 0)))),
            llm_tokens=int(float(str(data.get("llm_tokens", 0)))),
            estimated_cost=float(str(data.get("estimated_cost", 0))),
            experiments=int(float(str(data.get("experiments", 0)))),
            elapsed_seconds=time.time() - float(str(data.get("started_at", time.time()))),
        )

    def is_budget_exceeded(self, job_id: str) -> bool:
        key = f"specproof:budget:job:{job_id}"
        data = self.client.hgetall(key)
        if not data:
            return False
        tokens = int(float(str(data.get("llm_tokens", 0))))
        max_tokens = int(float(str(data.get("max_tokens", 100000))))
        cost = float(str(data.get("estimated_cost", 0)))
        max_cost = float(str(data.get("max_cost", 5.0)))
        return tokens > max_tokens or cost > max_cost

    # ── P1.4: Progress Stream ────────────────────────────────────

    def xadd_progress(self, job_id: str, data: dict[str, Any], maxlen: int = 1000) -> str:
        """Append to job progress stream. Returns the entry ID."""
        stream_key = f"specproof:stream:job:{job_id}"
        flat: dict[str, Any] = {}
        for k, v in data.items():
            flat[k] = json.dumps(v) if not isinstance(v, str) else v
        entry_id: Any = self.client.xadd(stream_key, flat, maxlen=maxlen, approximate=True)  # type: ignore[arg-type]
        self.client.expire(stream_key, 3600)
        if isinstance(entry_id, bytes):
            entry_id = entry_id.decode()
        return str(entry_id)

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100, block_ms: int = 0
    ) -> list[dict[str, Any]]:
        """Read progress entries from a stream starting at from_id."""
        stream_key = f"specproof:stream:job:{job_id}"
        result: Any = self.client.xread(
            {stream_key: from_id}, count=count, block=block_ms,
        )
        entries: list[dict[str, Any]] = []
        if result:
            for _stream_name, messages in result:
                for msg_id, fields in messages:
                    entry: dict[str, Any] = {"id": msg_id}
                    for k, v in fields.items():
                        try:
                            entry[k] = json.loads(v) if isinstance(v, str) else v
                        except (json.JSONDecodeError, TypeError):
                            entry[k] = v
                    entries.append(entry)
        return entries

    def xread_progress_tail(
        self, job_id: str, from_id: str = "$", count: int = 100
    ) -> list[dict[str, Any]]:
        """Read new entries only (from_id='$' returns only new entries after call)."""
        return self.xread_progress(job_id, from_id=from_id, count=count)

    def xlen(self, job_id: str) -> int:
        stream_key = f"specproof:stream:job:{job_id}"
        return int(self.client.xlen(stream_key))

    # ── P1.4: Rate limiter ───────────────────────────────────────

    def check_rate(
        self, key: str, max_requests: int = 10, window_seconds: int = 60
    ) -> bool:
        """Simple sliding-window rate limiter. Returns True if allowed."""
        rk = f"specproof:rate:{key}"
        now = time.time()
        window_start = now - window_seconds
        pipe = self.client.pipeline()
        pipe.zremrangebyscore(rk, 0, window_start)
        pipe.zcard(rk)
        pipe.zadd(rk, {str(now): now})
        pipe.expire(rk, window_seconds + 10)
        _, count, _, _ = pipe.execute()
        return int(count) < max_requests

    # ── P0.5: cache helpers ──────────────────────────────────────

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
