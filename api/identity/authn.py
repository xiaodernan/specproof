"""Bearer authentication: sp_* local tokens or OIDC id_tokens → Principal.

Both credential types exchange for one unified principal (§1). Local tokens
resolve entirely from the identity store (tenant/role come from the user
row — the authoritative source, never from request parameters). OIDC
id_tokens are validated against the issuer's JWKS; the subject's user row
is looked up by oidc_sub and auto-provisioned on first login (tenant from
the stored user when present, otherwise from the configured tenant claim /
SPECPROOF_DEFAULT_TENANT_ID; role from the mapped role claim, with
'viewer' as the least-privilege fallback).
"""

from __future__ import annotations

import logging
from typing import Any

from api.identity.config import default_tenant_id, oidc_tenant_claim
from api.identity.oidc import OidcError, get_oidc_validator
from api.identity.principal import Principal
from api.identity.store import get_identity_store
from api.identity.tokens import verify_local_token
from storage.identity import DuplicateUserError, IdentityStore

logger = logging.getLogger(__name__)


def _roles_to_scopes(_roles: frozenset[str]) -> frozenset[str]:
    """OIDC principals carry no token scopes: the RBAC matrix decides."""
    return frozenset()


def provision_oidc_user(claims: dict[str, Any]) -> Principal:
    """Find-or-create the OIDC subject's user; return its principal."""
    store: IdentityStore = get_identity_store()
    sub = str(claims.get("sub", ""))
    if not sub:
        raise OidcError("id_token has no sub claim")
    validator = get_oidc_validator()
    roles = validator.map_roles(claims) if validator is not None else frozenset({"viewer"})
    role = next(iter(roles), "viewer")
    user = store.get_user_by_oidc_sub(sub)
    if user is not None:
        if user.status != "active":
            raise OidcError(f"oidc user {sub} is {user.status}")
        if user.role != role:
            try:
                user = store.update_user(user.id, role=role)
            except Exception:  # noqa: BLE001 — role refresh is best effort
                logger.warning("could not refresh oidc role for %s", sub)
        return Principal(
            user_id=user.id,
            tenant_id=user.tenant_id,
            roles=frozenset({user.role}),
            scopes=_roles_to_scopes(frozenset({user.role})),
        )
    tenant_id = _oidc_tenant_id(claims)
    email = str(claims.get("email") or f"{sub}@oidc.local")
    user = store.create_user(
        tenant_id=tenant_id, email=email, role=role, oidc_sub=sub
    )
    return Principal(
        user_id=user.id,
        tenant_id=user.tenant_id,
        roles=frozenset({user.role}),
        scopes=_roles_to_scopes(frozenset({user.role})),
    )


def _oidc_tenant_id(claims: dict[str, Any]) -> str:
    claim_name = oidc_tenant_claim()
    raw = claims.get(claim_name)
    if raw:
        return str(raw)
    fallback = default_tenant_id()
    if fallback:
        return fallback
    raise OidcError(
        f"id_token has no {claim_name!r} claim and SPECPROOF_DEFAULT_TENANT_ID "
        "is not configured"
    )


def authenticate_bearer(authorization: str | None) -> Principal | None:
    """Resolve an Authorization header to a principal, or None (reject).

    Fail-closed: any error — bad token, store outage, IdP unreachable —
    returns None so the caller answers 401 without an oracle.
    """
    if not authorization:
        return None
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        return None
    token = credential.strip()
    if token.startswith("sp_"):
        try:
            return verify_local_token(get_identity_store(), token)
        except Exception:  # noqa: BLE001 — fail closed
            logger.warning("local token verification failed; rejecting")
            return None
    try:
        validator = get_oidc_validator()
        if validator is None:
            return None
        claims = validator.validate(token)
        return provision_oidc_user(claims)
    except OidcError:
        return None
    except DuplicateUserError as exc:
        logger.warning("oidc auto-provisioning conflict: %s", exc)
        return None
    except Exception:  # noqa: BLE001 — fail closed
        logger.warning("oidc verification failed; rejecting")
        return None
