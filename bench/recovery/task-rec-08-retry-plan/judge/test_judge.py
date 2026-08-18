# mypy: ignore-errors
"""Hidden judge tests for task-rec-08: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

import pytest
from svc import backoff_plan, execute_with_retry


def test_phase1_still_works() -> None:
    assert backoff_plan(0, 1.0) == []


def test_phase2_hidden_cases() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        execute_with_retry(_boom, [0.0])
    assert execute_with_retry(lambda: 42, []) == 42


def _boom():
    raise RuntimeError("boom")


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "backoff_plan applied" in line) == 1
    assert len(lines) == 1
