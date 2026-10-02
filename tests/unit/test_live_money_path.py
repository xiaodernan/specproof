"""The live money path, end to end (#148) — BILLING_DESIGN.md §2/§3/§4.

One tenant, one request chain, one ledger, one invoice:

  POST /jobs (HTTP) → tenant stamping (§6, principal only) →
  meter_verify_job_start (§2 hook) → GET /billing/usage (§4 read) →
  GET /billing/invoices (draft, total == Σ line_items) →
  draft → issued → paid (§4 lifecycle via BillingStore.transition_invoice).

Reverse controls ride along: the free plan's hard-stop quota flips the same
POST from 202 to 429 (§3), a body-supplied tenant_id is stripped before the
route model sees it (§6), another tenant's money is invisible on the HTTP
read path, and a wrong (tenant, period) key refuses the transition with
InvoiceNotFoundError instead of silently no-opping.

MySQL is faked at the route level, at exactly the seam production uses:
storage/mysql.py:399-401 stamps row["tenant_id"] from current_scope().
Billing is the real per-test SQLite store (two instances, one file — the
route store and the metering writer, which is how production converges too).
"""

from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import api.routes.jobs as jobs_module
from api.identity.tokens import mint_token
from api.server import app
from storage.billing import (
    DEFAULT_PLANS,
    InvalidInvoiceTransitionError,
    InvoiceNotFoundError,
    current_period_key,
    meter_verify_job_start,
    reset_billing_writer,
)
from storage.tenant_scope import current_scope

HMAC_KEY = "test" + "-hmac-" + "money-path-148"


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload() -> dict[str, str]:
    return {
        "repo_path": "D:/repo",
        "base_ref": "base",
        "head_ref": "head",
        "spec_path": "demo/requirement.txt",
        "depth": "FAST",
    }


class _FakeRateLimitRedis:
    """Backs enforce_rate_limit (imported at call time from storage.redis).

    `.client` returns self so the fail-open warning never fires; incr always
    reports 1, which no test here throttles on.
    """

    @property
    def client(self) -> _FakeRateLimitRedis:
        return self

    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:
        pass


class _ScopeStampingMySQL:
    """create_job_with_outbox mirrors storage/mysql.py:399-401 — the row's
    tenant_id comes from the request-scoped TenantScope (§6), never the body."""

    rows: dict[str, dict[str, Any]] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    @classmethod
    def reset(cls) -> None:
        cls.rows = {}

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        row = dict(job)
        row["status"] = "QUEUED"
        scope = current_scope()
        if scope is not None:
            row["tenant_id"] = scope.tenant_id
        _ScopeStampingMySQL.rows[job["id"]] = row
        return str(job["id"])


@pytest.fixture()
def money_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> Generator[None, None, None]:
    """Tenant mode + per-test SQLite identity/billing + faked jobs store."""
    monkeypatch.setenv("SPECPROOF_AUTH_ENABLED", "true")
    monkeypatch.setenv("SPECPROOF_IDENTITY_URL", f"sqlite:{tmp_path / 'identity.db'}")
    monkeypatch.setenv("SPECPROOF_BILLING_URL", f"sqlite:{tmp_path / 'billing.db'}")
    monkeypatch.setenv("SPECPROOF_TOKEN_HMAC_KEY", HMAC_KEY)
    monkeypatch.setenv("SPECPROOF_BCRYPT_ROUNDS", "4")
    monkeypatch.delenv("SPECPROOF_API_KEY", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SPECPROOF_DEFAULT_TENANT_ID", raising=False)
    from api.identity.oidc import reset_oidc_validator
    from api.identity.store import reset_identity_store
    from api.routes.billing import reset_billing_store

    reset_identity_store()
    reset_oidc_validator()
    reset_billing_store()
    reset_billing_writer()
    _ScopeStampingMySQL.reset()
    monkeypatch.setattr(jobs_module, "MySQLStore", _ScopeStampingMySQL)
    monkeypatch.setattr("storage.redis.RedisStore", _FakeRateLimitRedis)
    yield
    reset_identity_store()
    reset_billing_store()
    reset_billing_writer()
    _ScopeStampingMySQL.reset()


@pytest.fixture()
def money_tenant(money_env: None) -> dict[str, Any]:
    """One tenant on the free plan with admin/operator tokens."""
    from api.identity.store import get_identity_store
    from api.routes.billing import get_billing_store

    identity = get_identity_store()
    tenant = identity.create_tenant("tenant-money")
    tokens: dict[str, str] = {}
    for role in ("admin", "operator"):
        user = identity.create_user(
            tenant.id, f"{role}@money.example.com", role=role,
        )
        _row, token = mint_token(identity, user.id, name=role)
        tokens[role] = token
    billing = get_billing_store()
    billing.upsert_subscription(tenant.id, "free", "active", 0.0, 4_000_000_000.0)
    return {"tenant": tenant.id, "tokens": tokens, "billing": billing}


def test_money_flows_from_http_request_to_durable_invoice(
    money_tenant: dict[str, Any],
) -> None:
    """§6 → §2 → §4 in one chain: job accepted, stamped, charged, invoiced."""
    client = TestClient(app)
    resp = client.post(
        "/jobs",
        json={**_payload(), "tenant_id": "tenant-evil"},
        headers=bearer(money_tenant["tokens"]["operator"]),
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    row = _ScopeStampingMySQL.rows[job_id]
    # §6: the row carries the CALLER's tenant — the body's tenant_id was
    # dropped by the middleware before the route model ever saw it, so the
    # strict allowlist and the scope stamp agree on one source.
    assert row["tenant_id"] == money_tenant["tenant"]
    # §2: the pipeline start hook charges one job_verify unit for THAT tenant.
    assert meter_verify_job_start(money_tenant["tenant"], job_id) is True
    # §4: the money is visible on the tenant's own usage read path.
    admin = bearer(money_tenant["tokens"]["admin"])
    usage = client.get("/api/v1/billing/usage", headers=admin)
    assert usage.status_code == 200
    metrics = [(r["metric"], r["units"]) for r in usage.json()["usage"]]
    assert ("job_verify", 1.0) in metrics
    # §4: the draft invoice for the current period reconciles.
    period = current_period_key()
    resp = client.get(
        "/api/v1/billing/invoices", params={"period": period}, headers=admin,
    )
    assert resp.status_code == 200
    invoices = resp.json()["invoices"]
    assert [i["period"] for i in invoices] == [period]
    invoice = invoices[0]
    assert invoice["status"] == "draft"
    assert invoice["total"] == round(
        sum(float(item["amount"]) for item in invoice["line_items"]), 2,
    )


def test_free_plan_allowance_spent_flips_the_same_post_to_429(
    money_tenant: dict[str, Any],
) -> None:
    """§3 hard-stop: the identical POST that was 202 becomes 429."""
    client = TestClient(app)
    operator = bearer(money_tenant["tokens"]["operator"])
    assert client.post("/jobs", json=_payload(), headers=operator).status_code == 202
    quota = float(DEFAULT_PLANS[0]["quotas"]["jobs_verify"])
    money_tenant["billing"].record_usage(
        "usage:fill:free", money_tenant["tenant"], "job_verify", quota,
        "job", time.time(),
    )
    resp = client.post("/jobs", json=_payload(), headers=operator)
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "QUOTA_EXCEEDED"
    assert body["schema_version"] == 1
    # The refusal never reached the jobs store: one accepted row, not two.
    assert len(_ScopeStampingMySQL.rows) == 1


def test_invoice_walks_the_lifecycle_and_refuses_skips(
    money_tenant: dict[str, Any],
) -> None:
    """§4 draft → issued → paid: forward only, idempotent, reversible to none."""
    client = TestClient(app)
    admin = bearer(money_tenant["tokens"]["admin"])
    period = current_period_key()
    store = money_tenant["billing"]
    tenant = money_tenant["tenant"]
    assert client.get(
        "/api/v1/billing/invoices", params={"period": period}, headers=admin,
    ).status_code == 200
    # draft -> paid skips issued: refused, and the refused step changed nothing.
    with pytest.raises(InvalidInvoiceTransitionError):
        store.transition_invoice(tenant, period, "paid")
    assert store.get_invoice(tenant, period).status == "draft"
    # An unknown word is a vocabulary error, not a lifecycle step.
    with pytest.raises(ValueError):
        store.transition_invoice(tenant, period, "settled")
    assert store.transition_invoice(tenant, period, "issued").status == "issued"
    # Crash-retry: asking for the status already held is an idempotent replay.
    assert store.transition_invoice(tenant, period, "issued").status == "issued"
    assert store.transition_invoice(tenant, period, "paid").status == "paid"
    with pytest.raises(InvalidInvoiceTransitionError):
        store.transition_invoice(tenant, period, "draft")
    # The HTTP read path reports the durable status — no separate cache.
    invoices = client.get(
        "/api/v1/billing/invoices", headers=admin,
    ).json()["invoices"]
    assert invoices[0]["status"] == "paid"


def test_another_tenants_money_is_neither_readable_nor_transitionable(
    money_tenant: dict[str, Any],
) -> None:
    """§6 isolation: B's ledger/invoice stay on B's side of every boundary."""
    from api.identity.store import get_identity_store

    identity = get_identity_store()
    tenant_b = identity.create_tenant("tenant-b")
    user_b = identity.create_user(tenant_b.id, "admin@b.example.com", role="admin")
    _row, token_b = mint_token(identity, user_b.id, name="admin")
    store = money_tenant["billing"]
    period = current_period_key()
    store.record_usage(
        "usage:a:1", money_tenant["tenant"], "job_verify", 3.0, "job",
        time.time(),
    )
    store.record_usage(
        "usage:b:1", tenant_b.id, "job_verify", 7.0, "job", time.time(),
    )
    store.create_invoice(
        tenant_b.id, period, [{"metric": "plan", "amount": 0.0}],
        0.0, "USD", "draft",
    )
    client = TestClient(app)
    # A's admin sees A's 3.0 units and none of B's 7.0.
    usage_a = client.get(
        "/api/v1/billing/usage", headers=bearer(money_tenant["tokens"]["admin"]),
    ).json()
    assert any(
        r["tenant_id"] == money_tenant["tenant"] and r["units"] == 3.0
        for r in usage_a["usage"]
    )
    assert all(r["tenant_id"] != tenant_b.id for r in usage_a["usage"])
    # B's admin sees B's 7.0 units.
    usage_b = client.get(
        "/api/v1/billing/usage", headers=bearer(token_b),
    ).json()
    assert any(
        r["tenant_id"] == tenant_b.id and r["units"] == 7.0
        for r in usage_b["usage"]
    )
    # The wrong (tenant, period) key refuses instead of silently no-opping,
    # and B's draft is untouched by the refusal.
    with pytest.raises(InvoiceNotFoundError):
        store.transition_invoice(money_tenant["tenant"], period, "issued")
    assert store.get_invoice(tenant_b.id, period).status == "draft"
