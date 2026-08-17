"""Production configuration guard (P0-A4).

Enterprise rule: in production, default passwords must NEVER ship. When
SPECPROOF_ENV=production, the guard verifies every credential is overridden
and refuses to start otherwise. In dev/CI the defaults remain usable.
"""

from __future__ import annotations

import os

_DEFAULT_CREDENTIALS = (
    ("MYSQL_PASSWORD", "specproof_pass"),
    ("MYSQL_ROOT_PASSWORD", "specproof_root"),
    ("MONGODB_PASSWORD", "specproof_pass"),
    ("ES_PASSWORD", "specproof_pass"),
    ("REDIS_PASSWORD", "specproof_pass"),
    ("RABBITMQ_PASSWORD", "specproof_pass"),
    ("MINIO_ROOT_PASSWORD", "specproof_pass"),
    ("MINIO_ROOT_USER", "minioadmin"),
)


class ProductionConfigError(RuntimeError):
    """Raised when production config uses default credentials."""


def is_production() -> bool:
    return os.getenv("SPECPROOF_ENV", "").strip().lower() == "production"


def validate_production_config() -> list[str]:
    """Return violations. Empty list = config is production-safe."""
    if not is_production():
        return []
    violations: list[str] = []
    for var, default in _DEFAULT_CREDENTIALS:
        value = os.getenv(var, "")
        if not value or value == default:
            violations.append(
                f"{var} is unset or still the default ({default!r})"
            )
    if not os.getenv("SPECPROOF_API_KEY"):
        violations.append("SPECPROOF_API_KEY is not configured")
    return violations


def enforce_production_config() -> None:
    """Raise ProductionConfigError with all violations (fail-fast)."""
    violations = validate_production_config()
    if violations:
        raise ProductionConfigError(
            "Insecure production configuration:\n- " + "\n- ".join(violations)
        )
