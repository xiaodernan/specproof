"""Semantic cache for non-evidence LLM steps only (grand-plan §6.1 / M9).

The evidence chain must ALWAYS be freshly computed — a cached verdict could
be replayed with stale inputs and poison the report. Only mechanical,
non-evidence task kinds may be cached: draft and diagnose. Every other kind
is hard-excluded by :func:`cacheable`:

- court / counterexample / accept_judge / contract_compile — evidence kinds
  whose verdicts must never come from a cache;
- edit_plan — mutates the plan, rides the cheap router tier but is NOT cached;
- unknown kinds — fail closed (False).

Keys are sha256 digests of the prompt digest, the model and the canonicalized
request params::

    key = sha256(prompt_digest + "|" + model + "|" + canonical_json(params))

The default cache is an in-memory TTL + LRU store: expired entries are evicted on
read and on capacity pressure, and when full the least recently used entry
is dropped. It is OFF by default (enabled=False). ``craft/loop.py`` and
``providers/client_policy.py`` both import it at module scope, but the loop
only ever uses a cache a caller hands it and no product call site does — the
single product construction is ``providers/client_policy.py``, behind
``SPECPROOF_PROVIDER_POLICY=1``. An unconfigured deployment is therefore
byte-identical to today, and its ``cache_hits`` metric reads 0 because there is
no cache, not because nothing matched. Enable explicitly::

    cache = SemanticCache(enabled=True)
    key = cache_key(digest, model, params)
    if cacheable(kind):
        hit = cache.get(key) or cache.put(key, compute(), kind=kind)

Distributed backing (optional, same fail-closed kinds): pass ``store=`` (any
``SemanticCacheStore`` — the shipped implementation is the Redis one in
``providers/semantic_cache_redis.py``) plus ``encode``/``decode`` for the payload.
The evidence-kind exclusions and the disabled default are unchanged; every
store operation is wrapped so a Redis hiccup becomes a counter and a miss,
never an exception — a cache must not fail the call it accelerates.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any, Protocol, runtime_checkable

#: The only task kinds a semantic cache may serve (non-evidence, mechanical).
CACHEABLE_KINDS: frozenset[str] = frozenset({"draft", "diagnose"})

#: Evidence kinds — caching these would replay verdicts instead of
#: recomputing them, poisoning the evidence chain. Hard-excluded.
EVIDENCE_KINDS: frozenset[str] = frozenset(
    {"court", "counterexample", "accept_judge", "contract_compile"}
)

DEFAULT_MAX_ENTRIES = 1024
DEFAULT_TTL_SECONDS = 300.0


@runtime_checkable
class SemanticCacheStore(Protocol):
    """The minimal distributed-store contract the cache needs (fail-open).

    Implementations must return ``str | None`` from ``get`` and accept a TTL
    in seconds (``ex``) in ``set``; any exception they raise is counted and
    treated as absence (never as failure of the caller's work). The only
    implementation shipped is the Redis one in ``semantic_cache_redis.py``.
    """

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ex: int) -> None: ...


def cacheable(kind: str) -> bool:
    """True ONLY for draft | diagnose; everything else is hard False.

    The evidence kinds (court / counterexample / accept_judge /
    contract_compile), edit_plan, and unknown kinds all fail closed.
    Matching is case- and whitespace-insensitive.
    """
    return kind.strip().lower() in CACHEABLE_KINDS


def cache_key(prompt_digest: str, model: str, params: Mapping[str, Any]) -> str:
    """Deterministic sha256 cache key over prompt digest + model + params.

    Params are canonicalized (sorted keys, compact JSON, str() fallback for
    non-JSON values) so insertion order and value reprs never change the key.
    """
    canonical = json.dumps(
        dict(params), sort_keys=True, separators=(",", ":"), default=str
    )
    material = f"{prompt_digest}|{model}|{canonical}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class SemanticCache:
    """In-memory TTL + LRU cache for cacheable (non-evidence) task kinds.

    Off by default: when disabled, get() returns None and put() is a no-op,
    so wiring one in is the only way to change behavior. The clock is
    injectable (defaults to time.monotonic) so tests never sleep.
    """

    def __init__(
        self,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        enabled: bool = False,
        clock: Callable[[], float] = time.monotonic,
        store: SemanticCacheStore | None = None,
        encode: Callable[[Any], str] | None = None,
        decode: Callable[[str], Any] | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.store = store
        #: Serialization for the distributed path. Defaults to an identity pair
        #: (raw Python objects are not storable cross-process, so callers that
        #: pass a store must pass encode/decode too — the identity fallback
        #: exists for stores that hold native objects, e.g. test fakes).
        self._encode = encode if encode is not None else (lambda value: value)
        self._decode = decode if decode is not None else (lambda raw: raw)
        # Counters (disabled operations never touch them).
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0
        self.puts = 0
        self.rejected = 0
        #: Distributed-store failures observed (fail-open: counted, never raised).
        self.store_errors = 0

    @property
    def size(self) -> int:
        return len(self._entries)

    def get(self, key: str) -> Any | None:
        """Return the cached value or None (disabled, absent, or expired).

        A hit refreshes the entry's LRU recency. Note that a stored None
        value is indistinguishable from a miss; consult the hits counter
        when that matters.
        """
        if not self.enabled:
            return None
        if self.store is not None:
            raw: str | None
            try:
                raw = self.store.get(key)
            except Exception:  # noqa: BLE001 - the cache must not fail the call
                self.store_errors += 1
                self.misses += 1
                return None
            if raw is None:
                self.misses += 1
                return None
            try:
                value = self._decode(raw)
            except Exception:  # noqa: BLE001 - a poisoned entry is a miss
                self.store_errors += 1
                self.misses += 1
                return None
            self.hits += 1
            return value
        now = self._clock()
        entry = self._entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        expires_at, value = entry
        if now >= expires_at:
            del self._entries[key]
            self.expirations += 1
            self.misses += 1
            return None
        self._entries.move_to_end(key)
        self.hits += 1
        return value

    def put(self, key: str, value: Any, kind: str | None = None) -> bool:
        """Store a value; hard-refuses evidence kinds. Returns True when stored.

        kind=None skips the kind gate (the caller asserts cacheability);
        any non-cacheable kind is rejected and never stored.
        """
        if not self.enabled:
            return False
        if kind is not None and not cacheable(kind):
            self.rejected += 1
            return False
        if self.store is not None:
            try:
                payload = self._encode(value)
                self.store.set(key, payload, ex=max(1, int(self.ttl_seconds)))
            except Exception:  # noqa: BLE001 - writing a cache is best-effort
                self.store_errors += 1
                return False
            self.puts += 1
            return True
        self._entries[key] = (self._clock() + self.ttl_seconds, value)
        self._entries.move_to_end(key)
        self.puts += 1
        self._enforce_capacity(self._clock())
        return True

    def clear(self) -> None:
        """Drop every entry (counters are kept).

        With a distributed store, only the local LRU is dropped — remote
        entries expire on their TTL; callers wanting a fleet-wide flush
        must flush the keyspace, not this method.
        """
        self._entries.clear()

    def _enforce_capacity(self, now: float) -> None:
        """Sweep expired entries under capacity pressure, then LRU-evict."""
        if len(self._entries) >= self.max_entries:
            expired = [
                key
                for key, (expires_at, _value) in self._entries.items()
                if now >= expires_at
            ]
            for key in expired:
                del self._entries[key]
                self.expirations += 1
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
            self.evictions += 1

    def stats(self) -> dict[str, Any]:
        """Serializable snapshot (mirrors ModelRouter.metrics / TokenBudget.to_report)."""
        return {
            "enabled": self.enabled,
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
            "size": self.size,
            "backend": "redis" if self.store is not None else "memory",
            "store_errors": self.store_errors,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "puts": self.puts,
            "rejected": self.rejected,
        }
