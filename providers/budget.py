"""Token budget ledger for DeepSeek V4 Pro calls.

The gateway reports per-call usage including reasoning tokens and the
KV-cache hit/miss split. This module keeps a serializable ledger (evidence
chain) of every call and enforces a pre-call budget gate: overruns raise
BudgetExceeded — catchable, never silent.

Cost model: the budget is denominated in tokens; per-token cost weights
are configurable because the gateway's pricing (output vs reasoning vs
cache-hit discount) is deployment-specific and must not be hard-coded.
Default weights are honest placeholders (1 token = 1 unit, cache hits at
0.1x) and MUST be overridden from the real gateway price card once the
endpoint is known.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

DEFAULT_COST_WEIGHTS: dict[str, float] = {
    "prompt": 1.0,
    "completion": 1.0,
    "reasoning": 1.0,
    "cache_hit": 0.1,  # KV-cache hit discount — gateway-specific; override from price card
    "cache_miss": 1.0,
}


class BudgetExceeded(Exception):  # noqa: N818 — task-mandated name, kept catchable & explicit
    """Raised when a planned or recorded call exceeds the token budget.

    Carries limit / used / charge so callers can report the overrun
    instead of silently swallowing it.
    """

    def __init__(
        self, limit: float, used: float, charge: float, label: str = ""
    ) -> None:
        self.limit = limit
        self.used = used
        self.charge = charge
        self.label = label
        suffix = f", label={label!r}" if label else ""
        super().__init__(
            f"token budget exceeded: limit={limit:g}, used={used:g}, "
            f"charge={charge:g}{suffix}"
        )


class TokenBudget:
    """Accumulating ledger of LLM token usage with a pre-call gate."""

    def __init__(
        self,
        limit_tokens: float,
        cost_weights: dict[str, float] | None = None,
    ) -> None:
        if limit_tokens < 0:
            raise ValueError("limit_tokens must be >= 0")
        self.limit_tokens = float(limit_tokens)
        self.cost_weights = {**DEFAULT_COST_WEIGHTS, **(cost_weights or {})}
        self._used = 0.0
        self.entries: list[dict[str, Any]] = []

    @property
    def used(self) -> float:
        return self._used

    @property
    def remaining(self) -> float:
        return self.limit_tokens - self._used

    def charge(
        self,
        prompt_tokens: int,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0,
    ) -> float:
        """Weighted charge units for one call."""
        weights = self.cost_weights
        return (
            prompt_tokens * weights["prompt"]
            + completion_tokens * weights["completion"]
            + reasoning_tokens * weights["reasoning"]
            + cache_hit_tokens * weights["cache_hit"]
            + cache_miss_tokens * weights["cache_miss"]
        )

    def check(
        self,
        prompt_tokens: int,
        completion_tokens: int = 0,
        reasoning_tokens: int = 0,
        cache_hit_tokens: int = 0,
        label: str = "",
    ) -> None:
        """Pre-call gate: raise BudgetExceeded when the planned charge
        would overrun the remaining budget."""
        charge = self.charge(
            prompt_tokens, completion_tokens, reasoning_tokens, cache_hit_tokens
        )
        if charge > self.remaining:
            raise BudgetExceeded(
                limit=self.limit_tokens, used=self._used, charge=charge, label=label
            )

    def record(self, usage: dict[str, Any], label: str = "") -> dict[str, Any]:
        """Record actual usage (LLMResponse.usage fields) into the ledger.

        The entry is appended BEFORE the budget is enforced so that an
        overrun stays visible in the evidence chain, then BudgetExceeded
        is raised.
        """
        prompt = _as_int(usage.get("prompt_tokens"))
        completion = _as_int(usage.get("completion_tokens"))
        reasoning = _as_int(usage.get("reasoning_tokens"))
        cache_hit = _as_int(usage.get("prompt_cache_hit_tokens"))
        cache_miss = _as_int(usage.get("prompt_cache_miss_tokens"))
        charge = self.charge(prompt, completion, reasoning, cache_hit, cache_miss)
        self._used += charge
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "label": label,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "reasoning_tokens": reasoning,
            "prompt_cache_hit_tokens": cache_hit,
            "prompt_cache_miss_tokens": cache_miss,
            "charge": round(charge, 4),
            "used_after": round(self._used, 4),
            "remaining_after": round(self.remaining, 4),
        }
        self.entries.append(entry)
        if self._used > self.limit_tokens:
            raise BudgetExceeded(
                limit=self.limit_tokens, used=self._used, charge=charge, label=label
            )
        return entry

    def to_report(self) -> dict[str, Any]:
        """Serializable ledger snapshot (evidence chain) for reports."""
        return {
            "limit_tokens": self.limit_tokens,
            "used": round(self._used, 4),
            "remaining": round(self.remaining, 4),
            "cost_weights": dict(self.cost_weights),
            "calls": len(self.entries),
            "entries": list(self.entries),
        }


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
