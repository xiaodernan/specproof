"""Unit tests for P1.4 Redis Stream, lock, and budget operations."""

import pytest

from storage.redis import BudgetSnapshot, RedisConfig


class TestRedisConfig:
    def test_defaults(self) -> None:
        c = RedisConfig()
        assert c.host == "localhost"
        assert c.port == 6379

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDIS_HOST", "redis.internal")
        monkeypatch.setenv("REDIS_PORT", "6380")
        monkeypatch.setenv("REDIS_PASSWORD", "s3cret")
        c = RedisConfig.from_env()
        assert c.host == "redis.internal"
        assert c.port == 6380
        assert c.password == "s3cret"


class TestBudgetSnapshot:
    def test_defaults(self) -> None:
        b = BudgetSnapshot()
        assert b.tool_calls == 0
        assert b.llm_tokens == 0
        assert b.estimated_cost == 0.0

    def test_with_values(self) -> None:
        b = BudgetSnapshot(
            tool_calls=42,
            llm_tokens=15000,
            estimated_cost=0.75,
            experiments=3,
            elapsed_seconds=120.5,
        )
        assert b.tool_calls == 42
        assert b.llm_tokens == 15000
        assert b.estimated_cost == 0.75
        assert b.experiments == 3
        assert b.elapsed_seconds == 120.5
