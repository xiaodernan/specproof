"""The distributed (Redis) backend of the semantic cache — hermetic legs.

The in-memory sibling (providers/semantic_cache.py) is already pinned by
tests/unit/test_semantic_cache.py. The Redis path adds a serialization
boundary and a store boundary, so these legs cover exactly those two:

1. encode/decode round trip of a real ChatCompletion through JSON;
2. a fake store serves a decoded copy back (hits exactly once, the value
   is the caller's object again — not bytes, not a dict);
3. a dead/raising store is a MISS and a counter, never an exception — the
   provider must work on a box whose Redis is on fire;
4. put() through a raising store reports False + store_errors and nothing
   else happens (evidence kinds are still rejected, same gate);
5. the policy layer with SPECPROOF_SEMANTIC_CACHE_BACKEND=redis against an
   unreachable Redis (port 1) still completes a draft-kind call fail-open;
6. evidence kinds (court|counterexample|accept_judge|contract_compile) are
   refused at the distributed boundary exactly as at the memory boundary.
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any

import pytest

from providers.semantic_cache import SemanticCache
from providers.semantic_cache_redis import SemanticCacheRedisStore
from providers.client_policy import ClientPolicy, _decode_sdk_response, _encode_sdk_response

_SDK_PAYLOAD: dict[str, Any] = {
    "id": "chatcmpl-roundtrip",
    "object": "chat.completion",
    "created": 1794559384,
    "model": "gpt-6-sol",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
}


def _sdk_response():
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate(_SDK_PAYLOAD)


class FakeStore:
    """Native-object stand-in for the Redis store (no JSON round trip)."""

    def __init__(self, *, raise_get: bool = False, raise_set: bool = False) -> None:
        self.data: dict[str, str] = {}
        self.raise_get = raise_get
        self.raise_set = raise_set

    def get(self, key: str):
        if self.raise_get:
            raise ConnectionError("fake store get is on fire")
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int):
        if self.raise_set:
            raise ConnectionError("fake store set is on fire")
        self.data[key] = value


def test_encode_decode_round_trips_a_real_chat_completion() -> None:
    raw = _encode_sdk_response(_sdk_response())
    parsed = json.loads(raw)
    assert parsed["model"] == "gpt-6-sol"
    restored = _decode_sdk_response(raw)
    assert restored.choices[0].message.content == "ok"
    assert restored.usage is not None and restored.usage.total_tokens == 12


def test_a_hit_through_the_store_returns_the_rehydrated_object() -> None:
    store = FakeStore()
    cache = SemanticCache(enabled=True, ttl_seconds=60, store=store,
                          encode=_encode_sdk_response, decode=_decode_sdk_response)
    assert cache.put("k", _sdk_response(), kind="draft") is True

    fresh = SemanticCache(enabled=True, ttl_seconds=60, store=store,
                          encode=_encode_sdk_response, decode=_decode_sdk_response)
    hit = fresh.get("k")
    assert hit is not None
    assert hit.choices[0].message.content == "ok"
    assert fresh.hits == 1 and fresh.misses == 0


def test_a_dead_store_is_a_miss_and_a_counter_never_an_exception() -> None:
    store = FakeStore(raise_get=True, raise_set=True)
    cache = SemanticCache(enabled=True, ttl_seconds=60, store=store,
                          encode=_encode_sdk_response, decode=_decode_sdk_response)
    assert cache.get("k") is None
    assert cache.misses == 1
    assert cache.store_errors == 1
    assert cache.put("k", _sdk_response(), kind="draft") is False
    assert cache.store_errors == 2


def test_evidence_kinds_are_refused_at_the_distributed_boundary() -> None:
    store = FakeStore()
    cache = SemanticCache(enabled=True, store=store,
                          encode=_encode_sdk_response, decode=_decode_sdk_response)
    assert cache.put("k", _sdk_response(), kind="court") is False
    assert cache.put("k", _sdk_response(), kind="counterexample") is False
    assert cache.put("k", _sdk_response(), kind="accept_judge") is False
    assert cache.put("k", _sdk_response(), kind="contract_compile") is False
    assert store.data == {}


def test_the_redis_store_talks_only_through_get_and_set() -> None:
    """The store's entire contract — no other Redis verbs may creep in."""
    client_calls: list[tuple] = []

    class Recorder:
        def get(self, key: str):
            client_calls.append(("get", key))
            return None

        def set(self, key: str, value: str, ex=None):
            client_calls.append(("set", key, ex))

    store = SemanticCacheRedisStore(client=Recorder())
    assert store.get("k") is None
    store.set("k", "v", ex=42)
    assert client_calls == [("get", "specproof:semcache:k"),
                            ("set", "specproof:semcache:k", 42)]


def test_policy_with_redis_backend_fails_open_on_an_unreachable_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Port 1 refuses every connection instantly — no network, no flake."""
    monkeypatch.setenv("SPECPROOF_PROVIDER_POLICY", "1")
    monkeypatch.setenv("SPECPROOF_SEMANTIC_CACHE_BACKEND", "redis")
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "1")
    monkeypatch.delenv("SPECPROOF_ROUTER_CHEAP_BASE_URL", raising=False)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        policy = ClientPolicy(max_attempts=1)

    assert policy.cache.store is not None
    assert policy.cache.enabled

    async def fake_create(_client: Any, kwargs: dict[str, Any]):
        return _sdk_response()

    import asyncio

    response = asyncio.run(
        policy.execute(
            "draft",
            {"model": "gpt-6-sol", "messages": [{"role": "user", "content": "hi"}]},
            create=fake_create,
            make_client=lambda _base: object(),
        )
    )
    assert response.choices[0].message.content == "ok"
    assert policy.cache.store_errors >= 1
