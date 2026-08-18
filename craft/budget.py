"""M1 budget defaults and the per-task Budget gate (design doc §4.8, 附录 D).

Defaults are constants; every value can be overridden through the CRAFT_*
environment variables and the CLI flags --max-iterations / --budget-tokens /
--timeout. Exceeding any budget must stop the loop and be reported honestly —
never silently truncated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_ITERATIONS = 12
DEFAULT_MAX_STEPS = 12
DEFAULT_MAX_TOOL_CALLS = 40
DEFAULT_TOKEN_BUDGET = 200_000
DEFAULT_TIMEOUT_MINUTES = 60
# Reserved for the M4 control plane: M1 runs one job at a time, so this
# constant is documented here but not consumed by the M1 loop.
DEFAULT_MAX_PARALLEL_JOBS = 2


class BudgetError(ValueError):
    """Invalid CRAFT_* environment configuration or CLI override."""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise BudgetError(f"环境变量 {name}={raw!r} 不是整数") from exc
    if value <= 0:
        raise BudgetError(f"环境变量 {name}={value} 必须为正整数")
    return value


@dataclass(frozen=True)
class Budget:
    """Per-task resource gate. All fields are inclusive caps."""

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_steps: int = DEFAULT_MAX_STEPS
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    token_budget: int = DEFAULT_TOKEN_BUDGET
    timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES

    @classmethod
    def from_env(cls) -> Budget:
        return cls(
            max_iterations=_env_int("CRAFT_MAX_ITERATIONS", DEFAULT_MAX_ITERATIONS),
            max_steps=_env_int("CRAFT_MAX_STEPS", DEFAULT_MAX_STEPS),
            max_tool_calls=_env_int("CRAFT_MAX_TOOL_CALLS", DEFAULT_MAX_TOOL_CALLS),
            token_budget=_env_int("CRAFT_TOKEN_BUDGET", DEFAULT_TOKEN_BUDGET),
            timeout_minutes=_env_int("CRAFT_TIMEOUT_MINUTES", DEFAULT_TIMEOUT_MINUTES),
        )

    def with_overrides(
        self,
        *,
        max_iterations: int | None = None,
        token_budget: int | None = None,
        timeout_minutes: int | None = None,
    ) -> Budget:
        overrides = {
            "max_iterations": max_iterations,
            "token_budget": token_budget,
            "timeout_minutes": timeout_minutes,
        }
        for name, value in overrides.items():
            if value is not None and value <= 0:
                raise BudgetError(f"预算参数 {name}={value} 必须为正整数")
        return Budget(
            max_iterations=max_iterations if max_iterations is not None else self.max_iterations,
            max_steps=self.max_steps,
            max_tool_calls=self.max_tool_calls,
            token_budget=token_budget if token_budget is not None else self.token_budget,
            timeout_minutes=(
                timeout_minutes if timeout_minutes is not None else self.timeout_minutes
            ),
        )

    def deadline(self, started_at: float) -> float:
        return started_at + self.timeout_minutes * 60.0

    def to_dict(self) -> dict[str, int]:
        return {
            "max_iterations": self.max_iterations,
            "max_steps": self.max_steps,
            "max_tool_calls": self.max_tool_calls,
            "token_budget": self.token_budget,
            "timeout_minutes": self.timeout_minutes,
        }
