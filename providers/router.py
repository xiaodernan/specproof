"""Two-tier model router — model routing economics (Hermes-class advantage #1).

Mechanical steps (draft / diagnose / edit_plan) may run on a cheaper model;
judgment steps (court / counterexample / accept_judge / contract_compile)
always run on the strong tier. Unknown task kinds route to the strong tier
(fail-safe), and a cheap-tier failure falls back to strong with a log line
and a counter — a failed cheap call is retried on strong, never silently
dropped.

Configuration (environment):

    SPECPROOF_ROUTER_CHEAP_BASE_URL / SPECPROOF_ROUTER_CHEAP_MODEL
        both set        -> cheap tier enabled
        partially set   -> cheap tier DISABLED (warning logged; fail closed,
                           never route to a half-configured gateway)
        both unset      -> identical to today: everything routes to strong
    SPECPROOF_ROUTER_STRONG_BASE_URL / SPECPROOF_ROUTER_STRONG_MODEL
        optional per-field overrides; each falls back to
        LLM_BASE_URL / LLM_MODEL (model default "deepseek-v4-pro", mirroring
        the provider default).

The router returns provider CONFIG (base_url/model), never constructs
clients. api_key stays LLM_API_KEY for both tiers. Nothing on the existing
call path imports this module, so an unconfigured deployment is
byte-identical to today.

Task-kind vocabulary follows the routing table of
docs/interview/INTERVIEW_MATERIALS.md §3; callers map their own task names
onto it (e.g. craft's "plan" -> draft, "judge" -> court).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_STRONG_MODEL = "deepseek-v4-pro"

ENV_CHEAP_BASE_URL = "SPECPROOF_ROUTER_CHEAP_BASE_URL"
ENV_CHEAP_MODEL = "SPECPROOF_ROUTER_CHEAP_MODEL"
ENV_STRONG_BASE_URL = "SPECPROOF_ROUTER_STRONG_BASE_URL"
ENV_STRONG_MODEL = "SPECPROOF_ROUTER_STRONG_MODEL"
ENV_LLM_BASE_URL = "LLM_BASE_URL"
ENV_LLM_MODEL = "LLM_MODEL"

#: Mechanical task kinds that may ride the cheap tier.
CHEAP_TASK_KINDS: frozenset[str] = frozenset({"draft", "diagnose", "edit_plan"})

#: Judgment task kinds that always ride the strong tier.
STRONG_TASK_KINDS: frozenset[str] = frozenset(
    {"court", "counterexample", "accept_judge", "contract_compile"}
)

KNOWN_TASK_KINDS: frozenset[str] = CHEAP_TASK_KINDS | STRONG_TASK_KINDS

LOGGER = logging.getLogger("providers.router")


@dataclass(frozen=True)
class ProviderRoute:
    """One resolved provider config: tier + base_url + model.

    base_url/model may be empty strings for the strong tier, which callers
    pass through as None so OpenAICompatibleProvider re-reads its own
    LLM_BASE_URL/LLM_MODEL env defaults — the legacy construction path.
    """

    tier: Literal["cheap", "strong"]
    base_url: str
    model: str
    is_fallback: bool = False

    def as_provider_kwargs(self) -> dict[str, str | None]:
        """Provider constructor kwargs; empty config degrades to env defaults."""
        return {"base_url": self.base_url or None, "model": self.model or None}


def _read(env: Mapping[str, str], name: str, default: str = "") -> str:
    return env.get(name, default).strip()


class ModelRouter:
    """Route(task_kind) -> ProviderRoute; cheap failures fall back to strong."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        source: Mapping[str, str] = os.environ if env is None else env

        cheap_base = _read(source, ENV_CHEAP_BASE_URL)
        cheap_model = _read(source, ENV_CHEAP_MODEL)
        self.cheap_enabled = bool(cheap_base) and bool(cheap_model)
        if bool(cheap_base) != bool(cheap_model):
            LOGGER.warning(
                "cheap tier config is partial (%s/%s); both must be set — "
                "cheap tier disabled, everything routes to strong",
                ENV_CHEAP_BASE_URL,
                ENV_CHEAP_MODEL,
            )

        strong_base = _read(source, ENV_STRONG_BASE_URL, _read(source, ENV_LLM_BASE_URL))
        strong_model = _read(
            source, ENV_STRONG_MODEL, _read(source, ENV_LLM_MODEL, DEFAULT_STRONG_MODEL)
        )

        self.tiers: dict[str, tuple[str, str]] = {
            "cheap": (cheap_base, cheap_model),
            "strong": (strong_base, strong_model),
        }
        self.route_counts: dict[str, int] = {"cheap": 0, "strong": 0}
        self.fallback_count = 0

    def configured_tiers(self) -> frozenset[str]:
        """Tiers usable by route(): strong always, cheap only when enabled."""
        if self.cheap_enabled:
            return frozenset({"cheap", "strong"})
        return frozenset({"strong"})

    def route(self, task_kind: str) -> ProviderRoute:
        """Select the provider config for a task kind.

        cheap kinds ride the cheap tier ONLY when it is enabled; every
        other kind — strong kinds, unknown kinds, or a disabled cheap
        tier — rides strong (fail-safe).
        """
        kind = task_kind.strip().lower()
        if self.cheap_enabled and kind in CHEAP_TASK_KINDS:
            tier: Literal["cheap", "strong"] = "cheap"
        else:
            tier = "strong"
        base_url, model = self.tiers[tier]
        self.route_counts[tier] += 1
        return ProviderRoute(tier=tier, base_url=base_url, model=model)

    def on_failure(self, route: ProviderRoute) -> ProviderRoute:
        """Cheap failure -> strong fallback (logged + counted).

        A strong route is returned unchanged — the fallback never loops.
        """
        if route.tier != "cheap":
            return route
        self.fallback_count += 1
        LOGGER.warning(
            "cheap tier call failed (model=%s); falling back to strong "
            "tier (fallback #%d)",
            route.model,
            self.fallback_count,
        )
        strong_base, strong_model = self.tiers["strong"]
        return ProviderRoute(
            tier="strong", base_url=strong_base, model=strong_model, is_fallback=True
        )

    def metrics(self) -> dict[str, Any]:
        """Serializable routing statistics (loggable by craft/loop)."""
        return {
            "router_configured": self.cheap_enabled,
            "configured_tiers": sorted(self.configured_tiers()),
            "route_counts": dict(self.route_counts),
            "fallback_count": self.fallback_count,
            "cheap": (
                {"base_url": self.tiers["cheap"][0], "model": self.tiers["cheap"][1]}
                if self.cheap_enabled
                else None
            ),
            "strong": {
                "base_url": self.tiers["strong"][0],
                "model": self.tiers["strong"][1],
            },
        }
