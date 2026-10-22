"""`craft/budget.py` 的预算闸门契约：默认值、环境变量、覆盖、截止时间、序列化。

预算闸门的 docstring 写着「Exceeding any budget must stop the loop and be reported
honestly — never silently truncated」。这条承诺的地基是**解析与校验**：一个 `0` 或
`-3` 的预算如果被悄悄接受，循环就会在第一步停住，而报告里看不出「预算被设成了零」。
本门钉住五件事：
1. `_env_int` 的四种输入（未设 / 空白 / 合法 / 非法）；
2. `from_env` 把五个 `CRAFT_*` 变量逐一映射到字段，未设时回落到常量；
3. `with_overrides` 只覆盖三个可覆盖字段（`max_steps` / `max_tool_calls` 不在
   CLI 覆盖面内），且拒绝非正数；
4. `deadline` 把分钟换算成秒；
5. `to_dict` 恰好五个键，值即字段值；`Budget` 是 frozen（预算不可中途被改）。

只加测试，`craft/budget.py` 一字未动。
"""

from __future__ import annotations

import dataclasses

import pytest

from craft.budget import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_STEPS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_TIMEOUT_MINUTES,
    DEFAULT_TOKEN_BUDGET,
    Budget,
    BudgetError,
    _env_int,
)

_ENV_NAMES = (
    "CRAFT_MAX_ITERATIONS",
    "CRAFT_MAX_STEPS",
    "CRAFT_MAX_TOOL_CALLS",
    "CRAFT_TOKEN_BUDGET",
    "CRAFT_TIMEOUT_MINUTES",
)


@pytest.fixture(autouse=True)
def _clear_craft_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts from "no CRAFT_* set", regardless of the host shell."""
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


# ── _env_int ────────────────────────────────────────────────────────────


def test_env_int_returns_default_when_unset() -> None:
    assert _env_int("SPECPROOF_BUDGET_UNSET", 7) == 7


def test_env_int_returns_default_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_BUDGET_BLANK", "   ")
    assert _env_int("SPECPROOF_BUDGET_BLANK", 7) == 7


def test_env_int_strips_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_BUDGET_NUM", "  12 ")
    assert _env_int("SPECPROOF_BUDGET_NUM", 7) == 12


def test_env_int_rejects_non_integer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_BUDGET_BAD", "abc")
    with pytest.raises(BudgetError) as excinfo:
        _env_int("SPECPROOF_BUDGET_BAD", 7)
    message = str(excinfo.value)
    assert "SPECPROOF_BUDGET_BAD" in message
    assert "'abc'" in message


@pytest.mark.parametrize("raw", ["0", "-3"])
def test_env_int_rejects_non_positive(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("SPECPROOF_BUDGET_NONPOS", raw)
    with pytest.raises(BudgetError) as excinfo:
        _env_int("SPECPROOF_BUDGET_NONPOS", 7)
    assert "正整数" in str(excinfo.value)


# ── Budget.from_env ────────────────────────────────────────────────────


def test_from_env_maps_every_craft_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRAFT_MAX_ITERATIONS", "3")
    monkeypatch.setenv("CRAFT_MAX_STEPS", "4")
    monkeypatch.setenv("CRAFT_MAX_TOOL_CALLS", "5")
    monkeypatch.setenv("CRAFT_TOKEN_BUDGET", "600")
    monkeypatch.setenv("CRAFT_TIMEOUT_MINUTES", "7")
    budget = Budget.from_env()
    assert (
        budget.max_iterations,
        budget.max_steps,
        budget.max_tool_calls,
        budget.token_budget,
        budget.timeout_minutes,
    ) == (3, 4, 5, 600, 7)


def test_from_env_falls_back_to_defaults() -> None:
    assert Budget.from_env() == Budget(
        max_iterations=DEFAULT_MAX_ITERATIONS,
        max_steps=DEFAULT_MAX_STEPS,
        max_tool_calls=DEFAULT_MAX_TOOL_CALLS,
        token_budget=DEFAULT_TOKEN_BUDGET,
        timeout_minutes=DEFAULT_TIMEOUT_MINUTES,
    )


# ── Budget.with_overrides ──────────────────────────────────────────────


def test_with_overrides_replaces_only_the_named_fields() -> None:
    base = Budget(
        max_iterations=2,
        max_steps=3,
        max_tool_calls=4,
        token_budget=500,
        timeout_minutes=5,
    )
    out = base.with_overrides(max_iterations=9)
    assert out.max_iterations == 9
    # 不可覆盖的三个字段原样保留
    assert (out.max_steps, out.max_tool_calls, out.token_budget, out.timeout_minutes) == (
        3,
        4,
        500,
        5,
    )


def test_with_overrides_none_keeps_every_field() -> None:
    base = Budget(
        max_iterations=2,
        max_steps=3,
        max_tool_calls=4,
        token_budget=500,
        timeout_minutes=5,
    )
    assert base.with_overrides() == base


def test_with_overrides_rejects_non_positive_max_iterations() -> None:
    with pytest.raises(BudgetError) as excinfo:
        Budget().with_overrides(max_iterations=0)
    assert "正整数" in str(excinfo.value)


def test_with_overrides_rejects_non_positive_token_budget() -> None:
    with pytest.raises(BudgetError) as excinfo:
        Budget().with_overrides(token_budget=-1)
    assert "正整数" in str(excinfo.value)


def test_with_overrides_rejects_non_positive_timeout() -> None:
    with pytest.raises(BudgetError) as excinfo:
        Budget().with_overrides(timeout_minutes=0)
    assert "正整数" in str(excinfo.value)


# ── deadline / to_dict / frozen ────────────────────────────────────────


def test_deadline_converts_minutes_to_seconds() -> None:
    assert Budget(timeout_minutes=2).deadline(100.0) == 220.0


def test_to_dict_has_exactly_the_five_caps() -> None:
    budget = Budget(
        max_iterations=2,
        max_steps=3,
        max_tool_calls=4,
        token_budget=500,
        timeout_minutes=5,
    )
    payload = budget.to_dict()
    assert set(payload) == {
        "max_iterations",
        "max_steps",
        "max_tool_calls",
        "token_budget",
        "timeout_minutes",
    }
    assert payload == {
        "max_iterations": 2,
        "max_steps": 3,
        "max_tool_calls": 4,
        "token_budget": 500,
        "timeout_minutes": 5,
    }


def test_budget_is_frozen() -> None:
    budget = Budget()
    with pytest.raises(dataclasses.FrozenInstanceError):
        budget.max_iterations = 99  # type: ignore[misc]
