"""Billing & usage endpoints (industrialization phase 6).

docs/architecture/BILLING_DESIGN.md §4. All endpoints sit behind the §2
RBAC matrix (billing:read — admin/operator/auditor; viewer is refused with
TENANT_FORBIDDEN). The refusal is enforced twice: by TenantAuthMiddleware
(which classifies /api/v1/billing as billing:read) and by the handlers
themselves, so direct handler calls cannot bypass the matrix. The
cross-tenant subscriptions list additionally requires admin/auditor,
mirroring the /admin/audit view. In single-tenant mode (auth not enabled)
every endpoint answers 503 PROVIDER_UNAVAILABLE exactly like
api/routes/admin.py.

Metering itself is opt-in (SPECPROOF_BILLING_URL, storage/billing.py);
these endpoints only read the ledger. The UI (usage dashboards, per-job
cost view) and the monthly invoice cron are deferred to the UI phase —
GET /billing/invoices generates the draft invoice on demand so the data
model and reconciliation are fully exercised by tests.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import time
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from api.auth import enforce_rate_limit
from api.errors import (
    AUTH_REQUIRED,
    PROVIDER_UNAVAILABLE,
    TENANT_FORBIDDEN,
    VALIDATION_FAILED,
    ApiError,
)
from api.identity.config import auth_enabled
from api.identity.principal import Principal, principal_allowed
from storage.billing import (
    BillingStore,
    Invoice,
    Plan,
    Subscription,
    UsageRecord,
    build_billing_store,
    ensure_invoice,
    seed_default_plans,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/billing",
    tags=["billing"],
    dependencies=[Depends(enforce_rate_limit)],
)

_DEFAULT_SQLITE_URL = "sqlite:specproof_billing.db"

_cached_store: BillingStore | None = None
_cached_url: str | None = None


def billing_url() -> str:
    """The configured billing URL, or the auth-mode default when enabled.

    Mirrors api/identity/store.py: an explicit SPECPROOF_BILLING_URL wins;
    otherwise tenant mode falls back to a local SQLite file so dev
    deployments survive restarts, and legacy mode uses the in-memory
    store (the endpoints still answer 503 before any query runs).
    """
    raw = os.getenv("SPECPROOF_BILLING_URL", "").strip()
    if raw:
        return raw
    return _DEFAULT_SQLITE_URL if auth_enabled() else ""


def get_billing_store() -> BillingStore:
    """The (cached) billing store for the current configuration."""
    global _cached_store, _cached_url
    url = billing_url()
    if _cached_store is None or _cached_url != url:
        _cached_store = build_billing_store(url)
        _cached_url = url
        seed_default_plans(_cached_store)
        logger.info("billing store ready: %s", url)
    return _cached_store


def reset_billing_store() -> None:
    """Drop the cached store (tests, reconfiguration)."""
    global _cached_store, _cached_url
    _cached_store = None
    _cached_url = None


# ── Route-level guards (the middleware is the outer enforcement layer) ───────


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


def _require_billing_read(principal: Principal) -> None:
    if not principal_allowed(principal, "billing", "read"):
        raise ApiError(
            status_code=403,
            code=TENANT_FORBIDDEN,
            detail=f"role {sorted(principal.roles)} may not read billing",
        )


def _assert_role(principal: Principal, allowed: frozenset[str]) -> None:
    if not principal.roles & allowed:
        raise ApiError(
            status_code=403,
            code=TENANT_FORBIDDEN,
            detail=f"role {sorted(principal.roles)} is not permitted here",
        )


# ── Wire shapes ──────────────────────────────────────────────────────────────


def _plan_dict(plan: Plan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "name": plan.name,
        "price_monthly": plan.price_monthly,
        "quotas": plan.quotas,
        "overage": plan.overage,
    }


def _subscription_dict(sub: Subscription) -> dict[str, Any]:
    return {
        "id": sub.id,
        "tenant_id": sub.tenant_id,
        "plan_id": sub.plan_id,
        "status": sub.status,
        "period_start": sub.period_start,
        "period_end": sub.period_end,
    }


def _usage_dict(row: UsageRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "event_id": row.event_id,
        "metric": row.metric,
        "units": row.units,
        "unit_label": row.unit_label,
        "happened_at": row.happened_at,
    }


def _invoice_dict(invoice: Invoice) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "tenant_id": invoice.tenant_id,
        "period": invoice.period,
        "line_items": invoice.line_items,
        "total": invoice.total,
        "currency": invoice.currency,
        "status": invoice.status,
    }


def _usage_csv(rows: list[UsageRecord]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "tenant_id", "event_id", "metric", "units", "unit_label", "happened_at",
    ])
    for row in rows:
        writer.writerow([
            row.tenant_id, row.event_id, row.metric, row.units,
            row.unit_label, row.happened_at,
        ])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="usage.csv"'},
    )


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/plans")
async def list_plans(request: Request) -> dict[str, Any]:
    """The seeded plans with their quota/overage configuration."""
    _require_tenant_mode()
    principal = _principal(request)
    _require_billing_read(principal)
    plans = get_billing_store().list_plans()
    return {"plans": [_plan_dict(p) for p in plans], "count": len(plans)}


@router.get("/subscription")
async def my_subscription(request: Request) -> dict[str, Any]:
    """The caller tenant's active subscription (billing:read roles)."""
    _require_tenant_mode()
    principal = _principal(request)
    _require_billing_read(principal)
    sub = get_billing_store().get_subscription(principal.tenant_id)
    return {"subscription": _subscription_dict(sub) if sub is not None else None}


@router.get("/subscriptions")
async def list_subscriptions(request: Request) -> dict[str, Any]:
    """All tenants' subscriptions — admin/auditor only (audit-style view)."""
    _require_tenant_mode()
    principal = _principal(request)
    _require_billing_read(principal)
    _assert_role(principal, frozenset({"admin", "auditor"}))
    subs = get_billing_store().list_subscriptions()
    return {
        "subscriptions": [_subscription_dict(s) for s in subs],
        "count": len(subs),
    }


@router.get("/usage", response_model=None)
async def usage_report(
    request: Request,
    from_: float = Query(default=0.0, alias="from", ge=0),
    to: float | None = Query(default=None),
    fmt: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
) -> Response | dict[str, Any]:
    """Ledger rows in [from, to) as JSON (default) or CSV.

    Operators/admins see their own tenant; auditors get the cross-tenant
    audit view (every tenant's rows), mirroring the §2 matrix.
    """
    _require_tenant_mode()
    principal = _principal(request)
    _require_billing_read(principal)
    to_ts = time.time() + 1.0 if to is None else to
    if to_ts <= from_:
        raise ApiError(
            status_code=422,
            code=VALIDATION_FAILED,
            detail="'to' must be greater than 'from'",
        )
    tenant = None if "auditor" in principal.roles else principal.tenant_id
    rows = get_billing_store().list_usage(tenant, from_, to_ts)
    if fmt == "csv":
        return _usage_csv(rows)
    return {
        "usage": [_usage_dict(row) for row in rows],
        "count": len(rows),
        "from": from_,
        "to": to_ts,
    }


@router.get("/invoices")
async def list_invoices(
    request: Request,
    period: str | None = Query(
        default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
) -> dict[str, Any]:
    """Monthly invoices for the caller tenant (newest first).

    When period is given and no invoice exists yet, the draft invoice is
    generated on demand from the ledger (the production cron will call the
    same ensure_invoice at month start; the state machine draft→issued→paid
    is exercised by the store API).
    """
    _require_tenant_mode()
    principal = _principal(request)
    _require_billing_read(principal)
    store = get_billing_store()
    if period is not None:
        ensure_invoice(store, principal.tenant_id, period)
    invoices = store.list_invoices(principal.tenant_id)
    return {
        "invoices": [_invoice_dict(inv) for inv in invoices],
        "count": len(invoices),
    }
