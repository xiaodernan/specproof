"""Unit tests for storage adapters — tests run without real services."""

from storage.mysql import MySQLConfig
from storage.redis import RedisConfig


class TestMySQLConfig:
    def test_defaults(self) -> None:
        cfg = MySQLConfig()
        assert cfg.host == "localhost"
        assert cfg.port == 3306

    def test_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MYSQL_HOST", "db.example.com")
        monkeypatch.setenv("MYSQL_PORT", "3307")
        cfg = MySQLConfig.from_env()
        assert cfg.host == "db.example.com"
        assert cfg.port == 3307

    def test_password_is_not_default_in_production(self) -> None:
        cfg = MySQLConfig.from_env()
        # After from_env with no env vars, password is the compose default
        # This test ensures we don't accidentally use real keys
        assert "replace_me" not in cfg.password


class TestRedisConfig:
    def test_defaults(self) -> None:
        cfg = RedisConfig()
        assert cfg.host == "localhost"
        assert cfg.port == 6379
        assert cfg.db == 0

    def test_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("REDIS_HOST", "cache.internal")
        cfg = RedisConfig.from_env()
        assert cfg.host == "cache.internal"


class TestConfigNoLeakedKey:
    """Verify no config class hard-codes a real API key."""

    def test_mysql_config_no_hardcoded_key(self) -> None:
        cfg = MySQLConfig()
        assert "sk-" not in cfg.password.lower()

    def test_redis_config_no_hardcoded_key(self) -> None:
        cfg = RedisConfig()
        assert "sk-" not in cfg.password.lower()
