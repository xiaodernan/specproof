"""Redis store — cache, locks, progress streams, lease, budget for Phase 1.

P1.4: Added Redis Streams for progress, worker lease, and LLM token budget.
Backlog #9: progress entries carry a per-job monotonic sequence number
(atomic INCR counter key sharing the stream's TTL) and the retention
policy (XADD MAXLEN + key TTL) is configurable via RedisConfig.
All keys carry TTL — no permanent business state in Redis.
"""
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import redis

#: Default progress-stream retention policy (§14.3): XADD MAXLEN cap per
#: job stream, and TTL for the stream key plus its sequence-counter key.
STREAM_DEFAULT_MAXLEN = 1000
STREAM_DEFAULT_TTL_SECONDS = 86400


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    password: str = "specproof_pass"
    db: int = 0
    #: Progress-stream retention (§14.3): XADD MAXLEN cap and key TTL.
    stream_maxlen: int = STREAM_DEFAULT_MAXLEN
    stream_ttl_seconds: int = STREAM_DEFAULT_TTL_SECONDS

    @classmethod
    def from_env(cls) -> "RedisConfig":
        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD", "specproof_pass"),
            db=0,
            stream_maxlen=int(
                os.getenv("REDIS_STREAM_MAXLEN", str(STREAM_DEFAULT_MAXLEN))
            ),
            stream_ttl_seconds=int(
                os.getenv("REDIS_STREAM_TTL_SECONDS", str(STREAM_DEFAULT_TTL_SECONDS))
            ),
        )


class RedisStore:
    """Cache, locks, progress tracking, leases, and LLM budget. All keys have TTL."""

    #: Retained-history cap per job stream (XADD MAXLEN; default value,
    #: configurable via RedisConfig.stream_maxlen / REDIS_STREAM_MAXLEN).
    STREAM_MAXLEN = STREAM_DEFAULT_MAXLEN
    #: TTL for the stream key and its sequence counter (default value,
    #: configurable via RedisConfig.stream_ttl_seconds / REDIS_STREAM_TTL_SECONDS).
    STREAM_TTL_SECONDS = STREAM_DEFAULT_TTL_SECONDS

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

    def sequence_key(self, job_id: str) -> str:
        """Per-job monotonic sequence counter key (§14.3 event numbering).

        The counter makes the SSE `sequence` field trim-proof: XADD MAXLEN
        renumbers the retained window's ranks, while this counter only ever
        grows for the life of the stream (both keys share the same TTL and
        are written together, so they expire together).
        """
        return f"specproof:stream:job:{job_id}:seq"

    def xadd_progress(self, job_id: str, node: str, status: str,
                      message: str = "", percent: float = 0.0) -> str:
        """Append a progress event to the job's stream. Returns the entry ID.

        Every entry carries the job's next absolute sequence number (`seq`
        field from an atomic INCR), so clients can dedupe and re-order by
        sequence even after MAXLEN trimming drops older entries. A failed
        XADD can leave a gap in the sequence; monotonicity, not contiguity,
        is the contract.
        """
        seq = int(self.client.incr(self.sequence_key(job_id)))
        self.client.expire(
            self.sequence_key(job_id), self.config.stream_ttl_seconds
        )
        data = {
            "seq": str(seq),
            "node": node,
            "status": status,  # "running", "completed", "failed"
            "at": datetime.now(UTC).isoformat(),
            "percent": str(percent),
            "message": message,
        }
        key = self.stream_key(job_id)
        entry_id = self.client.xadd(
            key, cast(Any, data), maxlen=self.config.stream_maxlen
        )
        # Set TTL on the stream key (24h by default)
        self.client.expire(key, self.config.stream_ttl_seconds)
        return str(entry_id)

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100,
    ) -> list[dict[str, Any]]:
        """Read progress events from the stream starting from from_id.

        Returns list of {id, sequence, node, status, at, percent,
        message} dicts; sequence is the entry's absolute per-job number
        (0 for entries written before the counter existed).
        """
        key = self.stream_key(job_id)
        try:
            result = cast(Any, self.client.xread({key: from_id}, count=count))
            if not result:
                return []
            entries: list[dict[str, Any]] = []
            for _stream_name, messages in result:
                for msg_id, fields in messages:
                    entries.append({
                        "id": str(msg_id),
                        "sequence": int(fields.get("seq") or 0),
                        "node": str(fields.get("node", "")),
                        "status": str(fields.get("status", "")),
                        "at": str(fields.get("at", "")),
                        "percent": float(fields.get("percent", 0)),
                        "message": str(fields.get("message", "")),
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

    def lease_start_key(self, job_id: str) -> str:
        """Max-hold window marker: expires max_hold_seconds after acquire."""
        return f"specproof:lease:job:{job_id}:start"

    def lease_cap_flag_key(self, job_id: str) -> str:
        """Persistent flag: a max-hold cap was configured for this job's
        lease. Without it (legacy leases) renewals are unlimited — behavior
        identical to the pre-cap code."""
        return f"specproof:lease:job:{job_id}:cap"

    def acquire_lease(
        self,
        job_id: str,
        worker_id: str,
        ttl: int = 30,
        max_hold_seconds: int | None = None,
    ) -> bool:
        """Try to acquire a lease for job_id. Returns True if acquired.

        max_hold_seconds caps the TOTAL hold: the start marker expires
        after the cap and renew_lease then refuses, so a wedged worker's
        lease lapses on its own instead of renewing forever. None keeps
        the legacy unlimited behavior (no marker, no flag).
        """
        key = self.lease_key(job_id)
        # SET NX: only succeeds if key doesn't exist
        acquired = bool(self.client.set(key, worker_id, nx=True, ex=ttl))
        if acquired and max_hold_seconds is not None:
            self.client.set(self.lease_cap_flag_key(job_id), "1")
            self.client.set(
                self.lease_start_key(job_id), worker_id, ex=max_hold_seconds,
            )
        return acquired

    def renew_lease(self, job_id: str, worker_id: str, ttl: int = 30) -> bool:
        """Renew an existing lease. Worker must own the lease AND the
        max-hold window (when a cap was configured) must still be open."""
        key = self.lease_key(job_id)
        current = self.client.get(key)
        if current != worker_id:
            return False
        capped = bool(self.client.exists(self.lease_cap_flag_key(job_id)))
        if capped and not self.client.exists(self.lease_start_key(job_id)):
            return False  # max hold exhausted — let the lease lapse
        self.client.expire(key, ttl)
        return True

    def release_lease(self, job_id: str, worker_id: str) -> None:
        """Release a lease. Only releases if owned by worker_id (Lua safety).
        Max-hold marker keys are cleaned up with the lease."""
        key = self.lease_key(job_id)
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            redis.call("DEL", KEYS[2])
            redis.call("DEL", KEYS[3])
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        self.client.eval(
            lua_script, 3, key,
            self.lease_start_key(job_id), self.lease_cap_flag_key(job_id),
            worker_id,
        )

    def get_lease_owner(self, job_id: str) -> str | None:
        """Return the worker_id that holds the lease, or None."""
        val = self.client.get(self.lease_key(job_id))
        return str(val) if val is not None else None

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
