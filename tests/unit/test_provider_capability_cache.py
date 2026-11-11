"""The provider's capability verdict is cached (#1617), and the cache is
careful about what it remembers.

WHY. The probe is ELEVEN live requests against the gateway (including real
chat completions, so it costs tokens), and the streaming path asks for the
capabilities on every provider instance (``craft/llm.py::_stream_capability``
-> ``get_capabilities()`` -> ``probe_result``). The Redis store has carried a
capability cache since P1.4 -- with NO production caller: the probe was paid
again for every provider instance.

Three properties, each measured here:

* a cached verdict answers **without** probing (no gateway traffic at all),
* a probe that did NOT answer is **not** cached (a network blip must not pin
  "no capabilities" for a day),
* Redis being unavailable changes nothing for the provider (the cache is an
  optimization, never a dependency).

The legs that need Redis SKIP when no Redis answers -- the CI leg without
infrastructure has none, and "cannot measure" must not read as "measured
clean".
"""

from __future__ import annotations

from typing import Any

import pytest

from providers.openai_compatible import OpenAICompatibleProvider
from providers.probe_result import ProbeResult


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://gateway.invalid/v1",
        api_key="k",
        model="model-x",
        max_retries=0,
    )


def _redis_or_skip():
    from storage.redis import RedisStore

    store = RedisStore()
    try:
        if not store.is_ready():
            pytest.skip("no reachable Redis for the capability-cache legs")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no reachable Redis for the capability-cache legs: {exc}")
    return store


def _snapshot(capabilities: dict[str, Any], probed_at: str = "2026-11-10T00:00:00+00:00") -> dict[str, Any]:
    return {
        "capabilities": capabilities,
        "limits": {},
        "errors": [],
        "probed_at": probed_at,
    }


async def test_a_cached_verdict_answers_without_probing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _redis_or_skip()
    provider = _provider()
    key = provider._capability_cache_key()
    store.cache_provider_capability(key, _snapshot({"chat": True, "streaming": True}))
    try:
        calls = {"n": 0}

        async def fake_run(self: Any) -> ProbeResult:  # noqa: ARG001
            calls["n"] += 1
            return ProbeResult(
                provider="openai_compatible",
                base_url=provider.base_url,
                model=provider.model,
                capabilities={"chat": True, "streaming": False},
            )

        monkeypatch.setattr(
            "providers.capability_probe.CapabilityProbe.run", fake_run
        )
        result = await provider.run_probe()

        assert calls["n"] == 0, "the probe ran even though a verdict was cached"
        assert result.capabilities.get("streaming") is True
        assert result.probed_at == "2026-11-10T00:00:00+00:00"
    finally:
        store.client.delete(f"specproof:capability:{key}")


async def test_a_probe_that_answered_is_remembered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _redis_or_skip()
    provider = _provider()
    key = provider._capability_cache_key()
    store.client.delete(f"specproof:capability:{key}")
    try:
        async def fake_run(self: Any) -> ProbeResult:  # noqa: ARG001
            return ProbeResult(
                provider="openai_compatible",
                base_url=provider.base_url,
                model=provider.model,
                capabilities={"chat": True, "streaming": True},
            )

        monkeypatch.setattr(
            "providers.capability_probe.CapabilityProbe.run", fake_run
        )
        await provider.run_probe()

        cached = store.get_cached_provider_capability(key)
        assert cached is not None, "the probe's verdict was not written to the cache"
        assert cached["capabilities"]["chat"] is True
    finally:
        store.client.delete(f"specproof:capability:{key}")


async def test_a_probe_that_did_not_answer_is_not_remembered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed probe must not be cached: caching it would pin "no
    capabilities" for the whole TTL after one network blip."""
    store = _redis_or_skip()
    provider = _provider()
    key = provider._capability_cache_key()
    store.client.delete(f"specproof:capability:{key}")
    try:
        async def fake_run(self: Any) -> ProbeResult:  # noqa: ARG001
            return ProbeResult(
                provider="openai_compatible",
                base_url=provider.base_url,
                model=provider.model,
                capabilities={"chat": False, "streaming": False},
                errors=["gateway unreachable"],
            )

        monkeypatch.setattr(
            "providers.capability_probe.CapabilityProbe.run", fake_run
        )
        await provider.run_probe()

        assert store.get_cached_provider_capability(key) is None, (
            "a failed probe was cached -- one network blip would pin the "
            "provider's capabilities for a day"
        )
    finally:
        store.client.delete(f"specproof:capability:{key}")


async def test_redis_being_down_changes_nothing_for_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cache is an optimization, never a dependency: with no Redis the
    provider still probes and still answers."""
    provider = _provider()

    import storage.redis as redis_module

    def broken_store(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("no Redis here")

    monkeypatch.setattr(redis_module, "RedisStore", broken_store)

    async def fake_run(self: Any) -> ProbeResult:  # noqa: ARG001
        return ProbeResult(
            provider="openai_compatible",
            base_url=provider.base_url,
            model=provider.model,
            capabilities={"chat": True, "streaming": True},
        )

    monkeypatch.setattr("providers.capability_probe.CapabilityProbe.run", fake_run)
    result = await provider.run_probe()
    assert result.capabilities.get("chat") is True
