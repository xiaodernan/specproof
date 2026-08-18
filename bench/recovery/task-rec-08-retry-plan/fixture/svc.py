# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Retry execution (task-rec-08)."""

import time  # noqa: F401 — 第二阶段执行器 (execute_with_retry) 使用


def backoff_plan(retries: int, base: float) -> list[float]:
    return [base * (2 ** index) for index in range(retries)]


def execute_with_retry(func, delays: list[float]):
    raise NotImplementedError("phase 2 pending")
