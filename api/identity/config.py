"""Auth-mode configuration (industrialization phase 1).

Compatibility contract: auth is INERT unless explicitly enabled —
SPECPROOF_AUTH_ENABLED=true (or 1/yes/on) or OIDC_ISSUER set. When neither
is set the API behaves exactly as the single-tenant deployment: the tenant
middleware is a passthrough, the repository layer applies no tenant
predicates and the admin routes answer 503.
"""

from __future__ import annotations

import os

_TRUE_FLAGS = frozenset({"1", "true", "yes", "on"})


def auth_enabled() -> bool:
    """True when multi-tenant auth mode is explicitly configured."""
    flag = os.getenv("SPECPROOF_AUTH_ENABLED", "").strip().lower()
    if flag in _TRUE_FLAGS:
        return True
    return bool(os.getenv("OIDC_ISSUER", "").strip())


def token_hmac_key() -> str | None:
    """The HMAC key for sp_* token hashes; None when unconfigured.

    Fail-closed: with no key, token verification always rejects and minting
    raises. There is deliberately no fallback/default key — a default
    HMAC key would let a fresh deployment forge tokens from the source.
    """
    key = os.getenv("SPECPROOF_TOKEN_HMAC_KEY", "").strip()
    return key or None


def bcrypt_rounds() -> int:
    """bcrypt cost for local token secret hashes (SPECPROOF_BCRYPT_ROUNDS).

    Default 12; tests lower it to 4 to keep the suite fast. Values below 4
    are rejected (bcrypt's floor) — this is a test-speed knob, never a
    security weakening for production defaults.
    """
    raw = os.getenv("SPECPROOF_BCRYPT_ROUNDS", "12").strip()
    try:
        rounds = int(raw)
    except ValueError:
        return 12
    return rounds if rounds >= 4 else 12


def oidc_client_id() -> str:
    return os.getenv("OIDC_CLIENT_ID", "").strip()


def oidc_client_secret() -> str:
    return os.getenv("OIDC_CLIENT_SECRET", "").strip()


def oidc_role_claim() -> str:
    return os.getenv("SPECPROOF_OIDC_ROLE_CLAIM", "roles").strip() or "roles"


def oidc_tenant_claim() -> str:
    return os.getenv("SPECPROOF_OIDC_TENANT_CLAIM", "tenant_id").strip() or "tenant_id"


def default_tenant_id() -> str | None:
    value = os.getenv("SPECPROOF_DEFAULT_TENANT_ID", "").strip()
    return value or None
