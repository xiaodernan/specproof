"""P0-A4 tests — production configuration guard."""

import pytest

from storage.config_guard import (
    ProductionConfigError,
    enforce_production_config,
    validate_production_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("SPECPROOF_ENV", raising=False)
    monkeypatch.delenv("SPECPROOF_API_KEY", raising=False)
    for var in ("MYSQL_PASSWORD", "REDIS_PASSWORD", "ES_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


def test_dev_mode_allows_defaults():
    assert validate_production_config() == []
    enforce_production_config()  # must not raise


def test_production_rejects_defaults(monkeypatch):
    monkeypatch.setenv("SPECPROOF_ENV", "production")
    violations = validate_production_config()
    assert violations  # every default credential is flagged
    with pytest.raises(ProductionConfigError):
        enforce_production_config()


def test_production_passes_with_strong_config(monkeypatch):
    monkeypatch.setenv("SPECPROOF_ENV", "production")
    monkeypatch.setenv("SPECPROOF_API_KEY", "strong-key-123456")
    for var in (
        "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "MONGODB_PASSWORD",
        "ES_PASSWORD", "REDIS_PASSWORD", "RABBITMQ_PASSWORD",
        "MINIO_ROOT_PASSWORD", "MINIO_ROOT_USER",
    ):
        monkeypatch.setenv(var, "S3cure-" + var + "-x9")
    assert validate_production_config() == []
    enforce_production_config()
