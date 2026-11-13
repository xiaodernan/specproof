"""Redis backing for the semantic cache (draft | diagnose kinds ONLY).

The evidence chain must ALWAYS be freshly computed; this module inherits the
hard exclusions from ``semantic_cache.cacheable`` — nothing here changes which
kinds may be cached, only WHERE the cached bytes live. The single reason for a
distributed store is replica arithmetic: the api and worker services run the
craft loop on the same inputs more than once (retries, redeploys, seeds), and
per-process LRU threw that work away on every restart; with this store the
second replica to see the same mechanical prompt answers it in ~1ms instead of
a ~10s LLM call.

Design rules, same as the in-memory sibling:

* 50ms socket budgets — a dead Redis must NOT stall a generation. Both
  timeouts are 0.05s; failures surface to the cache as counters and misses.
* Keys are sha256 hex under a fixed prefix — safe charset, no PII shape, and
  the prefix makes fleet-wide flushes (SCAN + DEL) explicit operator verbs.
* Entries carry the caller's TTL as ``ex`` — no permanent state anywhere in
  this cache; eviction pressure belongs to Redis' own maxmemory policy.
* ``decode_responses=True`` — values are JSON text, not RESP bytes; callers
  always get ``str | None`` back.
"""

from __future__ import annotations

import os
from typing import Any

from storage.env_config import int_env

_REDIS_SOCKET_TIMEOUT_SECONDS = 0.05
_REDIS_CONNECT_TIMEOUT_SECONDS = 0.05
_REDIS_DEFAULT_DB = 0


class SemanticCacheRedisStore:
    """``SemanticCacheStore`` over one bounded Redis client (or an injected fake)."""

    PREFIX = "specproof:semcache:"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        db: int = _REDIS_DEFAULT_DB,
        client: Any | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return
        import redis

        self._client = redis.Redis(
            host=host if host is not None else os.getenv("REDIS_HOST", "localhost"),
            port=port if port is not None else int_env("REDIS_PORT", 6379),
            password=(
                password
                if password is not None
                else os.getenv("REDIS_PASSWORD", "specproof_pass")
            ),
            db=db,
            socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_SECONDS,
            decode_responses=True,
            health_check_interval=30,
        )

    def get(self, key: str) -> str | None:
        raw = self._client.get(self.PREFIX + key)
        if raw is None:
            return None
        return raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")

    def set(self, key: str, value: str, ex: int) -> None:
        self._client.set(self.PREFIX + key, value, ex=max(1, int(ex)))
