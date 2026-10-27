"""Route-level auth guards shared by the admin and billing routers.

These three helpers were byte-identical copies in ``api/routes/admin.py`` and
``api/routes/billing.py`` (#482). Authorization is the last place that should
have two implementations: a fix applied to one copy would leave the other
route family on the old rule, and nothing would go red.

The middleware is the outer enforcement layer; these are the per-route guards
that name the roles a handler accepts.
"""
from __future__ import annotations

from typing import cast

from fastapi import Request

from api.errors import (
    AUTH_REQUIRED,
    PROVIDER_UNAVAILABLE,
    TENANT_FORBIDDEN,
    ApiError,
)
from api.identity.config import auth_enabled
from api.identity.principal import Principal


def principal(request: Request) -> Principal:
    """The authenticated principal, or a 401 when the middleware set none."""
    found = cast(Principal | None, getattr(request.state, "principal", None))
    if found is None:
        raise ApiError(
            status_code=401, code=AUTH_REQUIRED, detail="Missing credentials",
        )
    return found


def require_tenant_mode() -> None:
    """Refuse a tenant-only route when multi-tenant auth is off."""
    if not auth_enabled():
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=(
                "Multi-tenant auth is not enabled: set SPECPROOF_AUTH_ENABLED=true "
                "or OIDC_ISSUER"
            ),
        )


def assert_role(actor: Principal, allowed: frozenset[str]) -> None:
    """403 unless the principal holds at least one of the allowed roles."""
    if not actor.roles & allowed:
        raise ApiError(
            status_code=403,
            code=TENANT_FORBIDDEN,
            detail=f"role {sorted(actor.roles)} is not permitted here",
        )


__all__ = ["assert_role", "principal", "require_tenant_mode"]
