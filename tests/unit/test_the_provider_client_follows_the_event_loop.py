"""The SDK client must not outlive the event loop it was built in.

httpx binds its connection pool to the loop that first used it, so an
``AsyncOpenAI`` client built in one event loop cannot serve another one. A
process that runs ``asyncio.run()`` more than once — a script with one
``asyncio.run()`` per stage, a test that drives the provider from two
loops — hits exactly that, and the symptom is a ``RuntimeError: Event loop
is closed`` raised at the **ack** of the request, long after the client was
built.

This is not hypothetical: ``scripts/provider_smoke.py`` (the CI job
`provider-smoke` runs) died at stage 3 for that reason until the provider
learned to rebuild its client when the loop changed.

Two properties are pinned here:

* a client this provider built is **rebuilt** when the loop changed;
* a client **injected** by a test (which carries no loop at all) is never
  replaced — the tests that hand the provider a fake must keep their fake.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import providers.openai_compatible as module  # noqa: E402
from providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402


class _FakeSDKClient:
    """Stands in for ``AsyncOpenAI`` — the provider only builds and closes it."""

    built: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        _FakeSDKClient.built.append(kwargs)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _fake_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSDKClient.built = []
    monkeypatch.setattr(module, "AsyncOpenAI", _FakeSDKClient)


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://gateway.test",
        api_key="unit-test-key",
        model="gpt-6-sol",
        probe_on_init=False,
        max_retries=0,
    )


def test_a_client_built_in_another_loop_is_not_reused() -> None:
    provider = _provider()

    first = asyncio.run(_call(provider))
    second = asyncio.run(_call(provider))

    assert first is not second, (
        "the client was carried into a second event loop — httpx would answer "
        "'Event loop is closed' at the first request there"
    )
    assert len(_FakeSDKClient.built) == 2, "the second loop must build its own client"
    # The stale client is NOT closed: it belongs to a dead loop, and closing it
    # would raise. Dropping the reference is the disposal.


def test_an_injected_client_is_never_replaced() -> None:
    """A test's fake carries no loop; replacing it would break every test."""
    provider = _provider()
    injected = _FakeSDKClient(base_url="https://injected.test")
    _FakeSDKClient.built.clear()   # the injected fake is not a BUILD
    provider._client = injected  # noqa: SLF001 - the seam under test

    got = asyncio.run(_call(provider))

    assert got is injected
    assert _FakeSDKClient.built == [], "an injected client must not trigger a build"


def test_the_same_loop_reuses_the_client() -> None:
    """Rebuilding on every call would be a leak; only a CHANGED loop rebuilds."""
    provider = _provider()

    async def twice() -> tuple[Any, Any]:
        return provider.client, provider.client

    first, second = asyncio.run(twice())

    assert first is second
    assert len(_FakeSDKClient.built) == 1


async def _call(provider: OpenAICompatibleProvider) -> Any:
    return provider.client
