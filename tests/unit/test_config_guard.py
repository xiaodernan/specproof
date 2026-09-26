"""P0-A4 tests — production configuration guard."""

import pytest

from storage.config_guard import (
    _DEFAULT_CREDENTIALS,
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
    # Read the guard's own list: a second hand-written tuple here went stale the
    # moment MYSQL_USER joined the check, and "strong config" passed while the
    # guard still refused to boot.
    for var, _default in _DEFAULT_CREDENTIALS:
        monkeypatch.setenv(var, "S3cure-" + var + "-x9")
    assert validate_production_config() == []
    enforce_production_config()
