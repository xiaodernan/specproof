"""Unit tests for providers.semantic_cache — no network, no Docker."""

import hashlib

import pytest

from providers.semantic_cache import (
    CACHEABLE_KINDS,
    EVIDENCE_KINDS,
    SemanticCache,
    cache_key,
    cacheable,
)


class FakeClock:
    """Injectable monotonic clock: only moves when advance() is called."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestCacheableGate:
    @pytest.mark.parametrize("kind", ["draft", "diagnose"])
    def test_cacheable_kinds(self, kind: str) -> None:
        assert cacheable(kind) is True

    @pytest.mark.parametrize("kind", sorted(EVIDENCE_KINDS))
    def test_evidence_kinds_hard_false(self, kind: str) -> None:
        assert cacheable(kind) is False

    @pytest.mark.parametrize(
        "kind", ["edit_plan", "plan", "court_appeal", "unknown", ""]
    )
    def test_non_cacheable_kinds_fail_closed(self, kind: str) -> None:
        assert cacheable(kind) is False

    def test_normalization_ignores_case_and_whitespace(self) -> None:
        assert cacheable("  DRAFT ") is True
        assert cacheable("Court") is False

    def test_kind_sets_match_contract(self) -> None:
        assert frozenset({"draft", "diagnose"}) == CACHEABLE_KINDS
        assert frozenset(
            {"court", "counterexample", "accept_judge", "contract_compile"}
        ) == EVIDENCE_KINDS


class TestSemanticCacheBehavior:
    def test_off_by_default(self) -> None:
        cache = SemanticCache()
        assert cache.enabled is False
        assert cache.get("any") is None
        assert cache.put("any", "value", kind="draft") is False
        assert cache.size == 0
        assert cache.stats()["enabled"] is False

    def test_disabled_cache_never_counts(self) -> None:
        cache = SemanticCache()
        cache.get("k")
        cache.put("k", "v", kind="draft")
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.puts == 0

    def test_hit_and_miss(self) -> None:
        cache = SemanticCache(enabled=True)
        key = cache_key("digest", "model", {"temperature": 0.1})
        assert cache.get(key) is None
        assert cache.put(key, {"content": "draft answer"}, kind="draft") is True
        assert cache.get(key) == {"content": "draft answer"}
        assert cache.get(key) == {"content": "draft answer"}
        assert cache.hits == 2
        assert cache.misses == 1
        assert cache.size == 1

    def test_ttl_expiry(self) -> None:
        clock = FakeClock()
        cache = SemanticCache(ttl_seconds=10.0, enabled=True, clock=clock)
        key = cache_key("d", "m", {})
        cache.put(key, "v", kind="diagnose")
        clock.advance(9.9)
        assert cache.get(key) == "v"
        clock.advance(0.2)  # 10.1 > ttl
        assert cache.get(key) is None
        assert cache.expirations == 1
        assert cache.misses == 1
        assert cache.hits == 1
        assert cache.size == 0

    def test_ttl_zero_expires_immediately(self) -> None:
        cache = SemanticCache(ttl_seconds=0.0, enabled=True)
        key = cache_key("d", "m", {})
        cache.put(key, "v", kind="draft")
        assert cache.get(key) is None

    def test_lru_eviction_when_full(self) -> None:
        cache = SemanticCache(max_entries=2, ttl_seconds=3600.0, enabled=True)
        k1 = cache_key("d1", "m", {})
        k2 = cache_key("d2", "m", {})
        k3 = cache_key("d3", "m", {})
        cache.put(k1, "v1", kind="draft")
        cache.put(k2, "v2", kind="draft")
        cache.put(k3, "v3", kind="draft")  # evicts k1 (least recently used)
        assert cache.get(k1) is None
        assert cache.get(k2) == "v2"
        assert cache.get(k3) == "v3"
        assert cache.evictions == 1
        assert cache.size == 2

    def test_lru_get_refreshes_recency(self) -> None:
        cache = SemanticCache(max_entries=2, ttl_seconds=3600.0, enabled=True)
        k1, k2, k3 = (cache_key(f"d{i}", "m", {}) for i in (1, 2, 3))
        cache.put(k1, "v1", kind="draft")
        cache.put(k2, "v2", kind="draft")
        assert cache.get(k1) == "v1"  # k1 becomes most recently used
        cache.put(k3, "v3", kind="draft")  # evicts k2 instead of k1
        assert cache.get(k1) == "v1"
        assert cache.get(k2) is None
        assert cache.get(k3) == "v3"

    def test_put_updates_existing_key_without_growth(self) -> None:
        cache = SemanticCache(max_entries=2, ttl_seconds=3600.0, enabled=True)
        key = cache_key("d", "m", {})
        assert cache.put(key, "old", kind="draft") is True
        assert cache.put(key, "new", kind="draft") is True
        assert cache.size == 1
        assert cache.get(key) == "new"
        assert cache.evictions == 0

    def test_expired_entries_swept_before_lru_eviction(self) -> None:
        clock = FakeClock()
        cache = SemanticCache(max_entries=2, ttl_seconds=10.0, enabled=True, clock=clock)
        k1, k2, k3 = (cache_key(f"d{i}", "m", {}) for i in (1, 2, 3))
        cache.put(k1, "v1", kind="draft")
        clock.advance(11.0)
        cache.put(k2, "v2", kind="draft")
        cache.put(k3, "v3", kind="draft")  # capacity pressure: k1 is expired, not evicted
        assert cache.get(k1) is None
        assert cache.get(k2) == "v2"
        assert cache.get(k3) == "v3"
        assert cache.evictions == 0
        assert cache.expirations == 1

    def test_clear_drops_entries_but_keeps_counters(self) -> None:
        cache = SemanticCache(enabled=True)
        key = cache_key("d", "m", {})
        cache.put(key, "v", kind="draft")
        cache.clear()
        assert cache.size == 0
        assert cache.get(key) is None
        assert cache.puts == 1

    def test_stats_snapshot(self) -> None:
        cache = SemanticCache(max_entries=4, ttl_seconds=30.0, enabled=True)
        cache.put(cache_key("d", "m", {}), "v", kind="draft")
        stats = cache.stats()
        assert stats["enabled"] is True
        assert stats["max_entries"] == 4
        assert stats["ttl_seconds"] == 30.0
        assert stats["size"] == 1
        assert stats["puts"] == 1
        assert stats["hits"] == 0

    def test_invalid_config_rejected(self) -> None:
        with pytest.raises(ValueError):
            SemanticCache(max_entries=0)
        with pytest.raises(ValueError):
            SemanticCache(ttl_seconds=-1.0)


class TestEvidenceKindsNeverCached:
    @pytest.mark.parametrize("kind", sorted(EVIDENCE_KINDS))
    def test_put_rejects_evidence_kinds(self, kind: str) -> None:
        cache = SemanticCache(enabled=True)
        key = cache_key("digest", "model", {})
        assert cache.put(key, "verdict", kind=kind) is False
        assert cache.get(key) is None
        assert cache.size == 0
        assert cache.rejected == 1
        assert cache.puts == 0

    def test_evidence_kind_rejection_never_poisons_existing_entries(self) -> None:
        cache = SemanticCache(enabled=True)
        draft_key = cache_key("digest", "model", {})
        cache.put(draft_key, "draft", kind="draft")
        assert cache.put(draft_key, "verdict", kind="court") is False
        assert cache.get(draft_key) == "draft"

    def test_put_without_kind_skips_gate(self) -> None:
        cache = SemanticCache(enabled=True)
        key = cache_key("digest", "model", {})
        assert cache.put(key, "raw", kind=None) is True
        assert cache.get(key) == "raw"


class TestCacheKey:
    def test_sha256_hex_format(self) -> None:
        key = cache_key("d1", "m1", {"a": 1})
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)
        expected = hashlib.sha256(b'd1|m1|{"a":1}').hexdigest()
        assert key == expected

    def test_params_order_insensitive(self) -> None:
        assert cache_key("d", "m", {"a": 1, "b": [1, 2]}) == cache_key(
            "d", "m", {"b": [1, 2], "a": 1}
        )

    def test_sensitive_to_prompt_model_and_params(self) -> None:
        base = cache_key("d", "m", {"t": 0.1})
        assert base != cache_key("d2", "m", {"t": 0.1})
        assert base != cache_key("d", "m2", {"t": 0.1})
        assert base != cache_key("d", "m", {"t": 0.2})
        assert base != cache_key("d", "m", {"t": 0.1, "extra": True})

    def test_non_json_params_serialize_stably(self) -> None:
        class Token:
            def __str__(self) -> str:
                return "tok"

        assert cache_key("d", "m", {"v": Token()}) == cache_key("d", "m", {"v": Token()})
