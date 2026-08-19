"""ClientPolicy — env-gated wiring of router / retry / semantic cache into
the provider call path (W44/W60 接线, ledger W94).

SPECPROOF_PROVIDER_POLICY=1 enables the layer. Unset — or any other value —
keeps the exact legacy path: OpenAICompatibleProvider does not construct a
ClientPolicy unless the gate is on, so an unconfigured deployment is
byte-identical to today (routing, tenacity retry and cache are all inert).

When enabled, one kind-tagged chat() call flows through three delivered
modules, in order:

1. route  — ModelRouter.route(kind): mechanical kinds (draft | diagnose |
            edit_plan) ride the cheap tier when SPECPROOF_ROUTER_CHEAP_* is
            fully configured; judgment kinds (court | counterexample |
            accept_judge | contract_compile) and unknown kinds ride strong
            (fail-safe). Routing only selects base_url/model — the provider
            stays the single owner of client construction and parsing.
2. cache  — cacheable kinds only (draft | diagnose, per semantic_cache).
            A hit short-circuits the network call; a miss is stored after a
            successful call. Evidence kinds bypass the cache entirely (the
            module hard-refuses them) and edit_plan is routed but never
            cached.
3. retry  — RetryPolicy.execute_async applies the classify_retry matrix,
            REPLACING the tenacity wrapper for policy calls only: 429 / 500 /
            502 / 503, timeouts and connection errors retry with jittered
            exponential backoff; 400 / 401 / 403 / 422 and unclassified
            failures fail closed. The attempt budget mirrors LLM_MAX_RETRIES
            (+1 attempt) so the legacy cap is preserved.

The layer never builds SDK clients: the provider injects make_client(base_url)
and create(client, kwargs), which keeps this layer thin. A cheap-tier failure
is NOT auto-failed-over here — ModelRouter.on_failure() offers that fallback
for a caller that wants it; it is left out so the layer stays predictable.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .resilience import CircuitBreaker, RetryPolicy
from .router import ModelRouter, ProviderRoute
from .semantic_cache import SemanticCache, cache_key, cacheable

#: Environment gate — the single switch for the whole layer (default off).
ENV_POLICY = "SPECPROOF_PROVIDER_POLICY"


def client_policy_enabled(env: Mapping[str, str] | None = None) -> bool:
    """True only for SPECPROOF_PROVIDER_POLICY=1 (default off, fail closed)."""
    source: Mapping[str, str] = os.environ if env is None else env
    return source.get(ENV_POLICY, "").strip() == "1"


def _sha256_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class ClientPolicy:
    """Route + cache + retry orchestration for one kind-tagged provider call."""

    def __init__(
        self,
        *,
        router: ModelRouter | None = None,
        retry: RetryPolicy | None = None,
        cache: SemanticCache | None = None,
        max_attempts: int = 3,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.router = router if router is not None else ModelRouter()
        self.retry = (
            retry
            if retry is not None
            else RetryPolicy(max_attempts=max_attempts, breaker=breaker)
        )
        # The policy owns its cache instance and switches it ON: the env gate
        # above is the layer switch, not the module's standalone default.
        self.cache = cache if cache is not None else SemanticCache(enabled=True)

    def route(self, kind: str) -> ProviderRoute:
        """Resolve the provider config (tier + base_url + model) for a kind."""
        return self.router.route(kind)

    def cache_key_for(self, kwargs: Mapping[str, Any]) -> str:
        """Deterministic semantic-cache key: prompt digest + model + params.

        Messages hash into the prompt digest; every remaining request field
        (model, tools, thinking, timeout, ...) is canonicalized into the
        params half, so a different request never reuses another's entry.
        """
        prompt_digest = _sha256_digest(_canonical_json(kwargs.get("messages")))
        model = str(kwargs.get("model", ""))
        params = {key: value for key, value in kwargs.items() if key != "messages"}
        return cache_key(prompt_digest, model, params)

    async def execute(
        self,
        kind: str,
        kwargs: dict[str, Any],
        *,
        create: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        make_client: Callable[[str], Any],
    ) -> Any:
        """One kind-tagged call under the policy: route → cache → retry.

        The callable pair is injected by the provider: make_client resolves
        the routed base_url to an SDK client (the provider's own client when
        the route carries no base_url or resolves to the provider's own
        endpoint) and create performs one raw completion call on it. The
        returned value is the raw SDK response; the provider parses it,
        exactly as on the legacy path. kwargs["model"] is updated in place
        when the route names a model.
        """
        route = self.route(kind)
        if route.model:
            kwargs["model"] = route.model
        key = self.cache_key_for(kwargs) if cacheable(kind) else None
        if key is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        client = make_client(route.base_url)

        async def attempt() -> Any:
            return await create(client, kwargs)

        response = await self.retry.execute_async(attempt)
        if key is not None:
            self.cache.put(key, response, kind=kind)
        return response
