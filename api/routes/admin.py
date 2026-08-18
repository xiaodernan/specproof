"""Multi-tenant auth + admin routes (industrialization phase 1).

Auth endpoints (prefix-less):
  GET  /auth/config                  auth mode + OIDC settings for the SPA
  GET  /auth/me                      the request principal (user/tenant/roles)
  GET  /auth/oidc/login              redirect to the IdP authorization endpoint
  GET  /auth/oidc/callback           authorization-code exchange → SPA redirect

Admin endpoints (/api/v1/admin, RBAC-governed by the §2 matrix):
  GET/POST /tenants                  admin only
  GET/POST /users, /users/{id}/role, /users/{id}/status
                                     admin / operator (own tenant)
  GET/POST /tokens, DELETE /tokens/{id}
                                     admin / operator (own tenant, show-once)
  GET      /audit                    admin / auditor (cross-tenant view)

Enforcement layers: the TenantAuthMiddleware already rejected anonymous
requests and RBAC violations before these handlers run; the handlers
additionally enforce the tenant scope (operator = own tenant only, 404 on
cross-tenant resources — never 403) and role-escalation limits. In
single-tenant mode (auth not enabled) every endpoint answers 503
PROVIDER_UNAVAILABLE — the API surface stays unchanged for legacy
deployments.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Any, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from api.auth import enforce_rate_limit
from api.errors import (
    AUTH_REQUIRED,
    PROVIDER_UNAVAILABLE,
    STATE_CONFLICT,
    TENANT_FORBIDDEN,
    USER_NOT_FOUND,
    VALIDATION_FAILED,
    ApiError,
)
from api.identity.config import (
    auth_enabled,
    oidc_client_id,
    oidc_client_secret,
)
from api.identity.oidc import OidcError, get_oidc_validator
from api.identity.principal import Principal
from api.identity.store import get_identity_store
from api.identity.tokens import TokenConfigError, mint_token
from storage.identity import ROLE_SET, DuplicateUserError, IdentityStore, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tenant-auth"])
admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["tenant-admin"],
    dependencies=[Depends(enforce_rate_limit)],
)

# ── OIDC authorization-code flow state (single-process, TTL-bounded) ────────

_OIDC_PENDING: dict[str, dict[str, Any]] = {}
_OIDC_LOCK = threading.Lock()
_OIDC_STATE_TTL_SECONDS = 600.0


def _principal(request: Request) -> Principal:
    principal = cast(Principal | None, getattr(request.state, "principal", None))
    if principal is None:
        raise ApiError(
            status_code=401, code=AUTH_REQUIRED, detail="Missing credentials",
        )
    return principal


def _require_tenant_mode() -> None:
    if not auth_enabled():
        raise ApiError(
            status_code=503,
            code=PROVIDER_UNAVAILABLE,
            detail=(
                "Multi-tenant auth is not enabled: set SPECPROOF_AUTH_ENABLED=true "
                "or OIDC_ISSUER"
            ),
        )


def _store() -> IdentityStore:
    return get_identity_store()


def _assert_role(principal: Principal, allowed: frozenset[str]) -> None:
    if not principal.roles & allowed:
        raise ApiError(
            status_code=403,
            code=TENANT_FORBIDDEN,
            detail=f"role {sorted(principal.roles)} is not permitted here",
        )


def _spa_redirect(fragment: dict[str, str]) -> RedirectResponse:
    return RedirectResponse(url="/#" + urlencode(fragment), status_code=302)


# ── /auth/* ──────────────────────────────────────────────────────────────────


@router.get("/auth/config")
async def auth_config() -> dict[str, Any]:
    """Auth mode + OIDC settings — read by the SPA login page."""
    validator = get_oidc_validator()
    return {
        "auth_mode": "tenant" if auth_enabled() else "legacy",
        "oidc": {
            "enabled": validator is not None,
            "issuer": validator.issuer if validator is not None else "",
            "client_id": validator.client_id if validator is not None else "",
        },
    }


@router.get("/auth/me")
async def auth_me(request: Request) -> dict[str, Any]:
    """The request principal (set by TenantAuthMiddleware)."""
    _require_tenant_mode()
    principal = _principal(request)
    payload = principal.to_dict()
    try:
        user = _store().get_user(principal.user_id)
        payload["email"] = user.email if user is not None else ""
    except Exception:  # noqa: BLE001 — email is cosmetic on this endpoint
        payload["email"] = ""
    return {"principal": payload}


@router.get("/auth/oidc/login", include_in_schema=False)
async def oidc_login(return_to: str = "") -> RedirectResponse:
    """Start the authorization-code flow; state/nonce are bound and TTL'd."""
    _require_tenant_mode()
    validator = get_oidc_validator()
    if validator is None:
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE,
            detail="OIDC is not configured (OIDC_ISSUER missing)",
        )
    try:
        authorization_endpoint = validator.discovery().get("authorization_endpoint")
    except OidcError as exc:
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE, detail=str(exc),
        ) from exc
    if not authorization_endpoint:
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE,
            detail="IdP discovery document has no authorization_endpoint",
        )
    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    with _OIDC_LOCK:
        now = time.time()
        for key in [k for k, v in _OIDC_PENDING.items()
                    if v["created_at"] + _OIDC_STATE_TTL_SECONDS < now]:
            _OIDC_PENDING.pop(key, None)
        _OIDC_PENDING[state] = {
            "nonce": nonce,
            "return_to": return_to[:2048],
            "created_at": now,
        }
    params = urlencode({
        "response_type": "code",
        "client_id": oidc_client_id(),
        "redirect_uri": _oidc_redirect_uri(),
        "scope": "openid email profile roles",
        "state": state,
        "nonce": nonce,
    })
    return RedirectResponse(f"{authorization_endpoint}?{params}", status_code=302)


def _oidc_redirect_uri() -> str:
    import os

    base = os.getenv("SPECPROOF_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/auth/oidc/callback"


@router.get("/auth/oidc/callback", include_in_schema=False)
async def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
) -> RedirectResponse:
    """Authorization-code exchange; hands the id_token to the SPA fragment."""
    _require_tenant_mode()
    if error:
        return _spa_redirect({"oidc_error": error_description or error})
    with _OIDC_LOCK:
        pending = _OIDC_PENDING.pop(state, None)
    if pending is None or pending["created_at"] + _OIDC_STATE_TTL_SECONDS < time.time():
        return _spa_redirect({"oidc_error": "state mismatch or expired"})
    validator = get_oidc_validator()
    if validator is None or not code:
        return _spa_redirect({"oidc_error": "missing authorization code"})
    try:
        token_endpoint = validator.discovery().get("token_endpoint")
        if not token_endpoint:
            return _spa_redirect({"oidc_error": "IdP has no token_endpoint"})
        token_payload = validator.exchange_code(
            str(token_endpoint),
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _oidc_redirect_uri(),
                "client_id": oidc_client_id(),
                "client_secret": oidc_client_secret(),
            },
        )
        id_token = str(token_payload.get("id_token") or "")
        if not id_token:
            return _spa_redirect({"oidc_error": "token endpoint returned no id_token"})
        claims = validator.validate(id_token, nonce=str(pending["nonce"]))
    except (OidcError, KeyError) as exc:
        logger.warning("oidc callback failed: %s", exc)
        return _spa_redirect({"oidc_error": "token exchange failed"})
    from api.identity.authn import provision_oidc_user

    try:
        principal = provision_oidc_user(claims)
    except OidcError as exc:
        logger.warning("oidc provisioning failed: %s", exc)
        return _spa_redirect({"oidc_error": "identity provisioning failed"})
    fragment: dict[str, str] = {
        "oidc_token": id_token,
        "tenant_id": principal.tenant_id,
        "user_id": principal.user_id,
    }
    if pending["return_to"]:
        fragment["return_to"] = pending["return_to"]
    return _spa_redirect(fragment)


# ── /api/v1/admin/tenants ───────────────────────────────────────────────────


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plan_id: str = Field(default="free", min_length=1, max_length=64)


@admin_router.get("/tenants")
async def list_tenants(request: Request) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin"}))
    tenants = _store().list_tenants()
    return {
        "tenants": [
            {
                "id": t.id, "name": t.name, "plan_id": t.plan_id,
                "status": t.status, "created_at": t.created_at,
            }
            for t in tenants
        ],
        "count": len(tenants),
    }


@admin_router.post("/tenants", status_code=201)
async def create_tenant(request: Request, payload: TenantCreate) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin"}))
    tenant = _store().create_tenant(name=payload.name, plan_id=payload.plan_id)
    return {
        "tenant": {
            "id": tenant.id, "name": tenant.name, "plan_id": tenant.plan_id,
            "status": tenant.status, "created_at": tenant.created_at,
        }
    }


# ── /api/v1/admin/users ─────────────────────────────────────────────────────


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str = Field(default="viewer", min_length=1, max_length=32)
    tenant_id: str | None = None


class RoleUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=32)


class StatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=32)


def _tenant_for_user_creation(principal: Principal, requested: str | None) -> str:
    # Tenant comes from the principal; a request-side tenant_id only takes
    # effect for admins (manage) — operators always act on their own tenant.
    if "admin" in principal.roles and requested:
        return requested
    return principal.tenant_id


def _user_or_404(store: IdentityStore, principal: Principal, user_id: str) -> User:
    user = store.get_user(user_id)
    if user is None or (
        user.tenant_id != principal.tenant_id and "admin" not in principal.roles
    ):
        # Cross-tenant is 404, never 403 (no existence leak).
        raise ApiError(status_code=404, code=USER_NOT_FOUND, detail="User not found")
    return user


@admin_router.get("/users")
async def list_users(request: Request, tenant_id: str | None = None) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    store = _store()
    target = _tenant_for_user_creation(principal, tenant_id)
    users = [
        {
            "id": u.id, "tenant_id": u.tenant_id, "email": u.email,
            "role": u.role, "status": u.status, "created_at": u.created_at,
        }
        for u in store.list_users(target)
    ]
    return {"users": users, "count": len(users)}


@admin_router.post("/users", status_code=201)
async def create_user(request: Request, payload: UserCreate) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    tenant_id = _tenant_for_user_creation(principal, payload.tenant_id)
    allowed_roles = ROLE_SET if "admin" in principal.roles else frozenset(
        {"viewer", "operator"}
    )
    if payload.role not in allowed_roles:
        raise ApiError(
            status_code=403,
            code=TENANT_FORBIDDEN,
            detail=f"role {payload.role!r} cannot be granted by "
                   f"{sorted(principal.roles)}",
        )
    try:
        user = _store().create_user(tenant_id=tenant_id, email=payload.email,
                                    role=payload.role)
    except DuplicateUserError as exc:
        raise ApiError(
            status_code=409, code=STATE_CONFLICT, detail=str(exc),
        ) from exc
    return {
        "user": {
            "id": user.id, "tenant_id": user.tenant_id, "email": user.email,
            "role": user.role, "status": user.status, "created_at": user.created_at,
        }
    }


@admin_router.post("/users/{user_id}/role")
async def update_user_role(
    request: Request, user_id: str, payload: RoleUpdate,
) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    allowed_roles = ROLE_SET if "admin" in principal.roles else frozenset(
        {"viewer", "operator"}
    )
    if payload.role not in allowed_roles:
        raise ApiError(
            status_code=403, code=TENANT_FORBIDDEN,
            detail=f"role {payload.role!r} cannot be granted by "
                   f"{sorted(principal.roles)}",
        )
    store = _store()
    user = _user_or_404(store, principal, user_id)
    if user.role == "admin" and "admin" not in principal.roles:
        raise ApiError(
            status_code=403, code=TENANT_FORBIDDEN,
            detail="only an admin may change an admin user",
        )
    user = store.update_user(user_id, role=payload.role)
    return {
        "user": {
            "id": user.id, "tenant_id": user.tenant_id, "email": user.email,
            "role": user.role, "status": user.status, "created_at": user.created_at,
        }
    }


@admin_router.post("/users/{user_id}/status")
async def update_user_status(
    request: Request, user_id: str, payload: StatusUpdate,
) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    if payload.status not in ("active", "disabled"):
        raise ApiError(
            status_code=422, code=VALIDATION_FAILED,
            detail=f"invalid user status {payload.status!r}",
        )
    store = _store()
    user = _user_or_404(store, principal, user_id)
    if user.role == "admin" and "admin" not in principal.roles:
        raise ApiError(
            status_code=403, code=TENANT_FORBIDDEN,
            detail="only an admin may change an admin user",
        )
    user = store.update_user(user_id, status=payload.status)
    return {
        "user": {
            "id": user.id, "tenant_id": user.tenant_id, "email": user.email,
            "role": user.role, "status": user.status, "created_at": user.created_at,
        }
    }


# ── /api/v1/admin/tokens ────────────────────────────────────────────────────


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: str = Field(default="", max_length=1024)
    ttl_days: int | None = Field(default=None, ge=1, le=3650)
    user_id: str | None = None


def _token_rows_for_tenant(store: IdentityStore, principal: Principal) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for user in store.list_users(principal.tenant_id):
        for token in store.list_tokens(user.id):
            rows.append({
                "id": token.id,
                "user_id": token.user_id,
                "user_email": user.email,
                "name": token.name,
                "scopes": token.scopes,
                "expires_at": token.expires_at,
                "last_used_at": token.last_used_at,
                "created_at": token.created_at,
            })
    return rows


@admin_router.get("/tokens")
async def list_tokens(request: Request) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    rows = _token_rows_for_tenant(_store(), principal)
    return {"tokens": rows, "count": len(rows)}


@admin_router.post("/tokens", status_code=201)
async def create_token(request: Request, payload: TokenCreate) -> dict[str, Any]:
    """Mint a scoped sp_* token — the cleartext is returned exactly once."""
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    store = _store()
    target_user_id = payload.user_id or principal.user_id
    target = _user_or_404(store, principal, target_user_id)
    if target.role == "admin" and "admin" not in principal.roles:
        raise ApiError(
            status_code=403, code=TENANT_FORBIDDEN,
            detail="only an admin may mint tokens for an admin user",
        )
    try:
        row, token = mint_token(
            store, user_id=target.id, name=payload.name,
            scopes=payload.scopes, ttl_days=payload.ttl_days,
        )
    except TokenConfigError as exc:
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE, detail=str(exc),
        ) from exc
    return {
        "token": {
            "id": row.id,
            "user_id": row.user_id,
            "name": row.name,
            "scopes": row.scopes,
            "expires_at": row.expires_at,
            "created_at": row.created_at,
        },
        # Show-once: the cleartext is never stored and cannot be recovered.
        "cleartext": token,
    }


@admin_router.delete("/tokens/{token_id}")
async def revoke_token(request: Request, token_id: str) -> dict[str, Any]:
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "operator"}))
    store = _store()
    tokens = [t for user in store.list_users(principal.tenant_id)
              for t in store.list_tokens(user.id)]
    if not any(t.id == token_id for t in tokens):
        raise ApiError(status_code=404, code=USER_NOT_FOUND, detail="Token not found")
    store.revoke_token(token_id)
    return {"revoked": True, "token_id": token_id}


# ── /api/v1/admin/audit ─────────────────────────────────────────────────────


@admin_router.get("/audit")
async def list_audit(
    request: Request, limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    """Audit log view — admin and auditor (§2: cross-tenant audit view)."""
    _require_tenant_mode()
    principal = _principal(request)
    _assert_role(principal, frozenset({"admin", "auditor"}))
    try:
        from storage.mysql import MySQLStore

        rows = MySQLStore().list_audit_logs(limit)
    except Exception as exc:  # noqa: BLE001 — storage outage is a 503
        raise ApiError(
            status_code=503, code=PROVIDER_UNAVAILABLE,
            detail=f"audit store unavailable: {exc}",
        ) from exc
    return {"audit": rows, "count": len(rows)}
