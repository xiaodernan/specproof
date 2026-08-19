"""Integration tests for the ClientPolicy wiring (W44/W60 接线, ledger W94).

The full stack is real — OpenAICompatibleProvider + ClientPolicy + ModelRouter
+ RetryPolicy/classify_retry + SemanticCache — with only the SDK transport
seam faked (no network, no Docker, no live LLM), mirroring the transport-stub
convention of tests/unit/test_providers_dsv4.py:

- provider._client is replaced with a recording stub (legacy/strong tier);
- provider._make_client is monkeypatched to hand out a recording stub per
  routed base_url (cheap tier);
- RetryPolicy is injected with jitter=0.0 and a fake async sleep so the
  classify_retry matrix backoff is exact and the tests never wait.

Scenario coverage: policy-off legacy path untouched; policy-on routing to the
cheap tier for draft; the retry matrix (429 retried, 400/unknown fail closed,
timeout retried); cache hit short-circuit; evidence kind cache bypass.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openai import RateLimitError

from providers.base import LLMMessage
from providers.client_policy import ENV_POLICY, ClientPolicy
from providers.openai_compatible import OpenAICompatibleProvider
from providers.probe_result import ProbeResult
from providers.resilience import RetryPolicy
from providers.router import ENV_CHEAP_BASE_URL, ENV_CHEAP_MODEL, ModelRouter
from providers.semantic_cache import SemanticCache

STRONG_BASE_URL = "http://strong.example"
STRONG_MODEL = "strong-model"
CHEAP_BASE_URL = "http://cheap.example"
CHEAP_MODEL = "cheap-model"

# ── transport stubs (transport-stub convention of test_providers_dsv4.py) ──


class _RecordingResponder:
    """Stub chat.completions.create: replays canned outcomes, records kwargs."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.attempts = 0
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        if not self.outcomes:
            raise AssertionError("recording responder has no outcomes")
        self.attempts += 1
        self.calls.append(dict(kwargs))
        outcome = self.outcomes[min(self.attempts - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeCompletions:
    def __init__(self, responder: _RecordingResponder) -> None:
        self._responder = responder

    async def create(self, **kwargs: Any) -> Any:
        return await self._responder(**kwargs)


class _FakeChat:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.completions = _FakeCompletions(responder)


class _FakeClient:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.chat = _FakeChat(responder)
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


def _fake_response(content: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=content, reasoning_content=None, tool_calls=[]
                ),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            prompt_cache_hit_tokens=None,
            prompt_cache_miss_tokens=None,
            completion_tokens_details=None,
        ),
        model="deepseek-v4-pro",
    )


def _rate_limit_error() -> RateLimitError:
    response = SimpleNamespace(
        headers={},
        status_code=429,
        request=SimpleNamespace(
            method="POST", url="http://llm.test/v1/chat/completions"
        ),
    )
    return RateLimitError("rate limited", response=response, body=None)


class _StatusError(Exception):
    """Fake gateway error carrying an HTTP status for classify_retry."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"http {status_code}")
        self.status_code = status_code


def _mock_api_key() -> str:
    """Fake key assembled from parts.

    The security scanner (tests/security/test_no_key_leak.py) forbids a
    complete key literal anywhere in .py files, even in fixtures — mirror
    tests/unit/test_providers_dsv4.py, which builds keys by concatenation.
    """
    return "sk-" + "test-" + "1234567890abcdef"


def _router_env() -> dict[str, str]:
    return {
        "LLM_BASE_URL": STRONG_BASE_URL,
        "LLM_MODEL": STRONG_MODEL,
        ENV_CHEAP_BASE_URL: CHEAP_BASE_URL,
        ENV_CHEAP_MODEL: CHEAP_MODEL,
    }


def _make_policy(
    *,
    router: ModelRouter,
    cache: SemanticCache,
    max_attempts: int = 3,
) -> tuple[ClientPolicy, list[float]]:
    """ClientPolicy with a real RetryPolicy (jitter=0, recorded fake sleep)."""
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    retry = RetryPolicy(
        max_attempts=max_attempts,
        jitter=0.0,
        async_sleep_fn=fake_sleep,
    )
    return ClientPolicy(router=router, retry=retry, cache=cache), delays


def _make_provider(
    strong_responder: _RecordingResponder,
    *,
    policy: ClientPolicy | None = None,
    max_retries: int | None = 2,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[OpenAICompatibleProvider, dict[str, _FakeClient]]:
    provider = OpenAICompatibleProvider(
        base_url=STRONG_BASE_URL,
        api_key=_mock_api_key(),
        model=STRONG_MODEL,
        probe_on_init=False,
        max_retries=max_retries,
        policy=policy,
    )
    provider._probe_result = ProbeResult(
        provider="openai_compatible",
        base_url=provider.base_url,
        model=provider.model,
        capabilities=dict.fromkeys(ProbeResult.CAPABILITY_KEYS, True),
    )
    provider._client = _FakeClient(strong_responder)
    tier_clients: dict[str, _FakeClient] = {}

    def make_client(base_url: str) -> _FakeClient:
        if base_url not in tier_clients:
            tier_clients[base_url] = _FakeClient(_RecordingResponder([]))
        return tier_clients[base_url]

    monkeypatch.setattr(provider, "_make_client", make_client)
    return provider, tier_clients


# ── policy OFF: the exact legacy path ────────────────────────────────────


async def test_policy_off_legacy_path_untouched(monkeypatch) -> None:
    monkeypatch.delenv(ENV_POLICY, raising=False)
    strong = _RecordingResponder([_fake_response(content="legacy")])
    provider, tier_clients = _make_provider(strong, monkeypatch=monkeypatch)

    assert provider._policy is None
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])

    assert result.content == "legacy"
    assert strong.attempts == 1
    assert strong.calls[0]["model"] == STRONG_MODEL
    assert tier_clients == {}


async def test_policy_off_kind_is_inert(monkeypatch) -> None:
    monkeypatch.delenv(ENV_POLICY, raising=False)
    strong = _RecordingResponder(
        [_fake_response(content="first"), _fake_response(content="second")]
    )
    provider, _ = _make_provider(strong, monkeypatch=monkeypatch)
    messages = [LLMMessage(role="user", content="hi")]

    first = await provider.chat(messages=messages)
    second = await provider.chat(messages=messages, kind="draft")

    assert first.content == "first"
    assert second.content == "second"
    assert strong.attempts == 2
    assert strong.calls[0] == strong.calls[1]  # byte-identical request shape
    assert strong.calls[1]["model"] == STRONG_MODEL


def test_gate_accepts_only_literal_one(monkeypatch) -> None:
    monkeypatch.setenv(ENV_POLICY, "true")
    strong = _RecordingResponder([_fake_response()])
    provider, _ = _make_provider(strong, monkeypatch=monkeypatch)
    assert provider._policy is None


# ── policy ON: routing ───────────────────────────────────────────────────


async def test_env_gate_builds_policy_and_routes_draft_to_cheap(monkeypatch) -> None:
    monkeypatch.setenv(ENV_POLICY, "1")
    for name, value in _router_env().items():
        monkeypatch.setenv(name, value)
    strong = _RecordingResponder([_fake_response()])
    cheap = _RecordingResponder([_fake_response(content="cheap-draft")])
    provider, tier_clients = _make_provider(strong, monkeypatch=monkeypatch)
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)

    assert provider._policy is not None
    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], kind="draft"
    )

    assert result.content == "cheap-draft"
    assert cheap.calls[0]["model"] == CHEAP_MODEL
    assert strong.attempts == 0
    assert provider._policy.router.route_counts["cheap"] == 1


async def test_policy_on_routes_draft_to_cheap_tier(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, _ = _make_policy(router=router, cache=SemanticCache(enabled=True))
    strong = _RecordingResponder([_fake_response()])
    cheap = _RecordingResponder([_fake_response(content="cheap")])
    provider, tier_clients = _make_provider(strong, policy=policy, monkeypatch=monkeypatch)
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)

    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], kind="draft"
    )

    assert result.content == "cheap"
    assert cheap.attempts == 1
    assert cheap.calls[0]["model"] == CHEAP_MODEL
    assert strong.attempts == 0
    assert router.route_counts == {"cheap": 1, "strong": 0}


async def test_policy_on_judgment_kind_stays_strong(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, _ = _make_policy(router=router, cache=SemanticCache(enabled=True))
    strong = _RecordingResponder([_fake_response(content="verdict")])
    provider, tier_clients = _make_provider(strong, policy=policy, monkeypatch=monkeypatch)

    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], kind="court"
    )

    assert result.content == "verdict"
    assert strong.attempts == 1
    assert strong.calls[0]["model"] == STRONG_MODEL
    assert tier_clients == {}  # strong tier reused the legacy client
    assert router.route_counts == {"cheap": 0, "strong": 1}


async def test_policy_on_unknown_kind_fails_safe_to_strong(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, _ = _make_policy(router=router, cache=SemanticCache(enabled=True))
    strong = _RecordingResponder([_fake_response(content="mystery")])
    provider, _ = _make_provider(strong, policy=policy, monkeypatch=monkeypatch)

    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], kind="mystery_kind"
    )

    assert result.content == "mystery"
    assert strong.calls[0]["model"] == STRONG_MODEL
    assert policy.cache.puts == 0
    assert policy.cache.hits == 0
    assert router.route_counts == {"cheap": 0, "strong": 1}


# ── policy ON: classify_retry matrix ─────────────────────────────────────


async def test_retry_matrix_retries_429_then_succeeds(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, delays = _make_policy(
        router=router, cache=SemanticCache(enabled=True), max_attempts=3
    )
    cheap = _RecordingResponder(
        [
            _rate_limit_error(),
            _rate_limit_error(),
            _fake_response(content="ok-after-retry"),
        ]
    )
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)

    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], kind="draft"
    )

    assert result.content == "ok-after-retry"
    assert cheap.attempts == 3
    assert delays == [1.0, 2.0]  # exponential, jitter pinned to 0
    assert policy.retry.retries == 2


async def test_retry_matrix_timeout_retries(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, delays = _make_policy(
        router=router, cache=SemanticCache(enabled=True), max_attempts=3
    )
    cheap = _RecordingResponder(
        [TimeoutError("timed out"), _fake_response(content="ok")]
    )
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)

    result = await provider.chat(
        messages=[LLMMessage(role="user", content="hi")], kind="draft"
    )

    assert result.content == "ok"
    assert cheap.attempts == 2
    assert delays == [1.0]


async def test_retry_matrix_hard_status_fails_closed_without_retry(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, delays = _make_policy(
        router=router, cache=SemanticCache(enabled=True), max_attempts=3
    )
    cheap = _RecordingResponder([_StatusError(400)])
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)

    with pytest.raises(_StatusError):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")], kind="draft")

    assert cheap.attempts == 1
    assert delays == []


async def test_retry_matrix_unclassified_fails_closed_without_retry(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, delays = _make_policy(
        router=router, cache=SemanticCache(enabled=True), max_attempts=3
    )
    cheap = _RecordingResponder([RuntimeError("unclassified boom")])
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)

    with pytest.raises(RuntimeError):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")], kind="draft")

    assert cheap.attempts == 1
    assert delays == []


# ── policy ON: semantic cache ────────────────────────────────────────────


async def test_cache_hit_short_circuits_second_call(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    cache = SemanticCache(enabled=True)
    policy, _ = _make_policy(router=router, cache=cache)
    cheap = _RecordingResponder([_fake_response(content="draft-plan")])
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)
    messages = [LLMMessage(role="user", content="plan this")]

    first = await provider.chat(messages=messages, kind="draft")
    second = await provider.chat(messages=messages, kind="draft")

    assert first.content == "draft-plan"
    assert second.content == "draft-plan"
    assert cheap.attempts == 1  # the second call never reached the transport
    assert cache.hits == 1
    assert cache.misses == 1
    assert cache.puts == 1


async def test_evidence_kind_bypasses_cache(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    cache = SemanticCache(enabled=True)
    policy, _ = _make_policy(router=router, cache=cache)
    strong = _RecordingResponder(
        [_fake_response(content="verdict-a"), _fake_response(content="verdict-b")]
    )
    provider, _ = _make_provider(strong, policy=policy, monkeypatch=monkeypatch)
    messages = [LLMMessage(role="user", content="judge this")]

    first = await provider.chat(messages=messages, kind="court")
    second = await provider.chat(messages=messages, kind="court")

    assert first.content == "verdict-a"
    assert second.content == "verdict-b"  # recomputed, never replayed
    assert strong.attempts == 2
    assert cache.hits == 0
    assert cache.misses == 0
    assert cache.puts == 0
    assert cache.rejected == 0


async def test_edit_plan_routes_cheap_but_is_never_cached(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    cache = SemanticCache(enabled=True)
    policy, _ = _make_policy(router=router, cache=cache)
    cheap = _RecordingResponder(
        [_fake_response(content="edit-a"), _fake_response(content="edit-b")]
    )
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = _FakeClient(cheap)
    messages = [LLMMessage(role="user", content="edit the plan")]

    first = await provider.chat(messages=messages, kind="edit_plan")
    second = await provider.chat(messages=messages, kind="edit_plan")

    assert first.content == "edit-a"
    assert second.content == "edit-b"
    assert cheap.attempts == 2
    assert cheap.calls[0]["model"] == CHEAP_MODEL
    assert cache.hits == 0
    assert cache.misses == 0
    assert cache.puts == 0


def test_cache_key_is_deterministic_and_prompt_sensitive() -> None:
    policy = ClientPolicy(
        router=ModelRouter(env=_router_env()),
        retry=RetryPolicy(max_attempts=1),
        cache=SemanticCache(enabled=True),
    )
    kwargs: dict[str, Any] = {
        "model": CHEAP_MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "timeout": 180.0,
    }
    key_a = policy.cache_key_for(kwargs)
    # Key order inside messages is canonicalized away.
    reordered = dict(
        kwargs, messages=[{"content": "hi", "role": "user"}]
    )
    key_b = policy.cache_key_for(reordered)
    different = dict(
        kwargs, messages=[{"role": "user", "content": "bye"}]
    )
    key_c = policy.cache_key_for(different)

    assert key_a == key_b
    assert key_c != key_a


async def test_close_closes_policy_tier_clients(monkeypatch) -> None:
    router = ModelRouter(env=_router_env())
    policy, _ = _make_policy(router=router, cache=SemanticCache(enabled=True))
    cheap_client = _FakeClient(_RecordingResponder([_fake_response()]))
    provider, tier_clients = _make_provider(
        _RecordingResponder([]), policy=policy, monkeypatch=monkeypatch
    )
    tier_clients[CHEAP_BASE_URL] = cheap_client

    await provider.chat(messages=[LLMMessage(role="user", content="hi")], kind="draft")
    await provider.close()

    assert cheap_client.closed == 1
    assert provider._client is None
