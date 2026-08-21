"""Billing & usage ledger tests (industrialization phase 6, no Docker).

docs/architecture/BILLING_DESIGN.md §5 — the exit criteria:
  * ledger idempotency: the same event_id written twice produces ONE row;
  * quota enforcement: hard-stop → QUOTA_EXCEEDED pre-flight, soft-overage
    plans allow the overrun with overage units, 80% soft-limit notifies
    exactly once per (tenant, metric, period);
  * invoice reconciliation: total == Σ line_items amounts;
  * RBAC on the billing endpoints: viewer → TENANT_FORBIDDEN;
  * cross-tenant isolation: a tenant's usage never leaks into another
    tenant's view (auditor keeps the cross-tenant audit view).

All mock — SQLite/in-memory backends, no network, no Docker. A MySQL
scenario is gated on MYSQL_URL (skipped when unset), mirroring
tests/integration. Fake keys are built by string concatenation so the
no-key-leak scanner can never match them.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.identity.tokens import mint_token
from api.server import app
from providers.budget import TokenBudget, clear_usage_listener, set_usage_listener
from storage.billing import (
    _SCHEMA_MYSQL,
    _SCHEMA_SQLITE,
    DEFAULT_PLANS,
    METRIC_SET,
    METRIC_VALUES,
    BillingStore,
    BillingWriter,
    DuplicatePlanError,
    InMemoryBillingStore,
    MySqlBillingStore,
    PlanNotFoundError,
    QuotaExceededError,
    SqliteBillingStore,
    build_billing_store,
    ensure_invoice,
    get_billing_writer,
    meter_craft_job_terminal,
    meter_verify_job_end,
    meter_verify_job_start,
    period_bounds,
    reset_billing_writer,
    seed_default_plans,
)
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope

HMAC_KEY = "test" + "-hmac-" + "billing-w40"
MYSQL_URL = os.getenv("MYSQL_URL")


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


def _month_start(period: str) -> float:
    return period_bounds(period)[0]


# ── Store backends (parity scenario + invariants) ────────────────────────────


def _scenario(store: BillingStore) -> dict[str, Any]:
    """Exercise every store operation once; returns key ids."""
    seed_default_plans(store)
    seed_default_plans(store)  # idempotent
    plans = store.list_plans()
    assert {p.id for p in plans} == {"free", "pro"}
    assert store.get_plan("pro") is not None
    assert store.get_plan("missing") is None

    sub = store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4e9)
    assert store.get_subscription("tenant-a") == sub
    assert store.get_subscription("tenant-missing") is None

    assert store.record_usage("evt-1", "tenant-a", "job_verify", 1.0, "job", 100.0)
    assert not store.record_usage("evt-1", "tenant-a", "job_verify", 1.0, "job", 100.0)
    rows = store.list_usage("tenant-a", 0.0, 1_000_000.0)
    assert len(rows) == 1 and rows[0].event_id == "evt-1"
    assert store.usage_total("tenant-a", "job_verify", 0.0, 1_000_000.0) == 1.0
    assert store.usage_total("tenant-a", "job_craft", 0.0, 1_000_000.0) == 0.0

    invoice = store.create_invoice(
        "tenant-a", "2026-08", [{"metric": "plan", "amount": 99.0}],
        99.0, "USD", "draft",
    )
    assert store.get_invoice("tenant-a", "2026-08") == invoice
    assert [i.period for i in store.list_invoices("tenant-a")] == ["2026-08"]
    return {"tenant": "tenant-a", "subscription": sub.id}


def test_factory_url_contract() -> None:
    assert isinstance(build_billing_store(""), InMemoryBillingStore)
    assert isinstance(build_billing_store("sqlite::memory:"), SqliteBillingStore)
    mysql = build_billing_store("mysql://user:pass@db.example.com:3306/specproof")
    assert isinstance(mysql, MySqlBillingStore)
    with pytest.raises(ValueError):
        build_billing_store("postgres://nope")


def test_schema_and_metric_invariants() -> None:
    assert frozenset(METRIC_VALUES) == METRIC_SET
    for schema in (_SCHEMA_SQLITE, _SCHEMA_MYSQL):
        for table in (
            "billing_plans", "billing_subscriptions", "usage_ledger", "invoices",
        ):
            assert table in schema
        assert "idx_usage_tenant_time" in schema
    assert "uq_usage_event" in _SCHEMA_MYSQL
    assert "event_id VARCHAR(255) NOT NULL UNIQUE" in _SCHEMA_SQLITE


def test_in_memory_backend_scenario() -> None:
    _scenario(InMemoryBillingStore())


def test_sqlite_backend_scenario(tmp_path: Path) -> None:
    db = tmp_path / "billing.db"
    store = SqliteBillingStore(db)
    ids = _scenario(store)
    store.close()
    reopened = SqliteBillingStore(db)
    assert reopened.get_subscription(ids["tenant"]) is not None
    assert reopened.get_invoice(ids["tenant"], "2026-08") is not None
    reopened.close()


def test_ledger_idempotency_double_write_single_row(tmp_path: Path) -> None:
    """§5: same event_id double-write → exactly one ledger row."""
    store = SqliteBillingStore(tmp_path / "billing.db")
    event_id = "verify:tenant-a:job-1:start"
    assert store.record_usage(event_id, "tenant-a", "job_verify", 1.0, "job", 123.0)
    assert not store.record_usage(event_id, "tenant-a", "job_verify", 1.0, "job", 124.0)
    rows = store.list_usage("tenant-a", 0.0, 1_000_000.0)
    assert len(rows) == 1
    assert rows[0].units == 1.0
    assert rows[0].happened_at == 123.0
    store.close()


def test_duplicate_plan_rejected() -> None:
    store = InMemoryBillingStore()
    store.create_plan("x", "X", 1.0, {}, {})
    with pytest.raises(DuplicatePlanError):
        store.create_plan("x", "X", 1.0, {}, {})


def test_unknown_plan_and_metric_rejected() -> None:
    store = InMemoryBillingStore()
    with pytest.raises(PlanNotFoundError):
        store.upsert_subscription("tenant-a", "nope", "active", 0.0, 1.0)
    with pytest.raises(ValueError):
        store.record_usage("evt-x", "tenant-a", "not_a_metric", 1.0)
    with pytest.raises(ValueError):
        store.record_usage("evt-x", "tenant-a", "job_verify", -1.0)


def test_cross_tenant_usage_isolation_sqlite(tmp_path: Path) -> None:
    store = SqliteBillingStore(tmp_path / "billing.db")
    store.record_usage("a:1", "tenant-a", "job_verify", 1.0, "job", 10.0)
    store.record_usage("b:1", "tenant-b", "job_verify", 1.0, "job", 10.0)
    assert [r.event_id for r in store.list_usage("tenant-a", 0.0, 100.0)] == ["a:1"]
    assert len(store.list_usage("tenant-b", 0.0, 100.0)) == 1
    assert len(store.list_usage(None, 0.0, 100.0)) == 2
    store.close()


# ── Quota enforcement + soft-limit (§3) ──────────────────────────────────────


def _pro_writer() -> BillingWriter:
    store = InMemoryBillingStore(now_fn=lambda: 1_000_000.0)
    seed_default_plans(store)
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 2_000_000.0)
    return BillingWriter(store, now_fn=lambda: 1_000_000.0)


def _free_writer() -> BillingWriter:
    store = InMemoryBillingStore(now_fn=lambda: 1_000_000.0)
    seed_default_plans(store)
    store.upsert_subscription("tenant-a", "free", "active", 0.0, 2_000_000.0)
    return BillingWriter(store, now_fn=lambda: 1_000_000.0)


def test_quota_hard_stop_raises_quota_exceeded() -> None:
    writer = _free_writer()
    quota = float(DEFAULT_PLANS[0]["quotas"]["jobs_verify"])
    writer.store.record_usage(
        "usage:seed", "tenant-a", "job_verify", quota, "job", 999_000.0,
    )
    with pytest.raises(QuotaExceededError) as excinfo:
        writer.check_quota("tenant-a", "job_verify", 1.0)
    assert excinfo.value.metric == "job_verify"
    assert excinfo.value.quota == quota
    assert excinfo.value.used == quota
    assert excinfo.value.planned == 1.0
    # Just below the limit the pre-flight still passes (hard-stop).
    writer2 = _free_writer()
    writer2.store.record_usage(
        "usage:seed", "tenant-a", "job_verify", quota - 2.0, "job", 999_000.0,
    )
    decision = writer2.check_quota("tenant-a", "job_verify", 1.0)
    assert decision.allowed
    assert decision.ratio == pytest.approx((quota - 1.0) / quota)


def test_quota_soft_overage_allowed_with_overage_units() -> None:
    writer = _pro_writer()
    quota = float(DEFAULT_PLANS[1]["quotas"]["jobs_verify"])
    writer.store.record_usage(
        "usage:seed", "tenant-a", "job_verify", quota, "job", 999_000.0,
    )
    decision = writer.check_quota("tenant-a", "job_verify", 3.0)
    assert decision.allowed
    assert decision.enforced
    assert decision.overage_units == 3.0


def test_quota_without_subscription_not_enforced() -> None:
    writer = _pro_writer()
    decision = writer.check_quota("tenant-x", "job_verify", 1.0)
    assert decision.allowed
    assert not decision.enforced


def test_soft_limit_80_percent_notification_once_per_period() -> None:
    writer = _free_writer()
    quota = float(DEFAULT_PLANS[0]["quotas"]["jobs_verify"])
    writer.store.record_usage(
        "usage:seed", "tenant-a", "job_verify", 0.8 * quota, "job", 999_000.0,
    )
    decision = writer.check_quota("tenant-a", "job_verify", 0.0)
    assert decision.ratio == pytest.approx(0.8)
    assert len(writer.notifications) == 1
    assert writer.notifications[0]["type"] == "soft_limit"
    assert writer.notifications[0]["metric"] == "job_verify"
    # Same period → the notification is emitted exactly once.
    writer.check_quota("tenant-a", "job_verify", 0.0)
    assert len(writer.notifications) == 1


# ── Invoice reconciliation (§5) ──────────────────────────────────────────────


def test_invoice_total_equals_sum_of_line_items() -> None:
    writer = _pro_writer()
    store = writer.store
    for event_id, metric, units in (
        ("e1", "job_verify", 502.0),   # quota 500 → overage 2 × 0.10
        ("e2", "job_craft", 1.0),
        ("e3", "llm_tokens_in", 1200.0),
        ("e4", "llm_tokens_out", 900.0),
        ("e5", "gate_findings", 5.0),
    ):
        store.record_usage(event_id, "tenant-a", metric, units, "unit", 500_000.0)
    invoice = ensure_invoice(store, "tenant-a", "1970-01", now_fn=lambda: 1_000_000.0)
    assert invoice.status == "draft"
    assert invoice.currency == "USD"
    assert invoice.total > 0
    assert invoice.total == round(
        sum(float(item["amount"]) for item in invoice.line_items), 2,
    )
    overage_lines = [
        li for li in invoice.line_items if float(li.get("overage_units", 0.0)) > 0
    ]
    assert len(overage_lines) == 1
    assert overage_lines[0]["metric"] == "job_verify"
    assert overage_lines[0]["overage_units"] == 2.0
    # Regeneration for the same period is idempotent (same invoice id).
    again = ensure_invoice(store, "tenant-a", "1970-01", now_fn=lambda: 1_000_000.0)
    assert again.id == invoice.id


def test_invoice_aggregates_llm_classes_into_llm_tokens_quota() -> None:
    writer = _pro_writer()
    store = writer.store
    store.record_usage("t1", "tenant-a", "llm_tokens_in", 100.0, "token", 500_000.0)
    store.record_usage("t2", "tenant-a", "llm_tokens_out", 50.0, "token", 500_000.0)
    store.record_usage("t3", "tenant-a", "llm_cache_hit_tokens", 25.0, "token", 500_000.0)
    invoice = ensure_invoice(store, "tenant-a", "1970-01", now_fn=lambda: 1_000_000.0)
    llm_line = next(li for li in invoice.line_items if li["metric"] == "llm_tokens")
    assert llm_line["units"] == 175.0
    assert llm_line["quota"] == float(DEFAULT_PLANS[1]["quotas"]["llm_tokens"])


# ── LLM usage listener (four token classes, cache-hit 512 case) ──────────────


def test_token_budget_usage_listener_records_four_token_classes(tmp_path: Path) -> None:
    store = SqliteBillingStore(tmp_path / "billing.db")
    writer = BillingWriter(store)
    def _sink(entry: dict[str, Any]) -> None:
        writer.record_llm_usage(entry)

    token = TENANT_SCOPE_VAR.set(TenantScope(tenant_id="tenant-a"))
    set_usage_listener(_sink)
    try:
        budget = TokenBudget(limit_tokens=10_000.0)
        budget.record(
            {
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "reasoning_tokens": 300,
                "prompt_cache_hit_tokens": 512,
                "prompt_cache_miss_tokens": 64,
            },
            label="plan",
        )
    finally:
        clear_usage_listener()
        TENANT_SCOPE_VAR.reset(token)
    by_metric = {
        row.metric: row.units
        for row in store.list_usage("tenant-a", 0.0, time.time() + 1000.0)
    }
    assert by_metric == {
        "llm_tokens_in": 100.0,
        "llm_tokens_out": 200.0,
        "llm_reasoning_tokens": 300.0,
        "llm_cache_hit_tokens": 512.0,
    }
    store.close()


def test_usage_listener_defaults_off() -> None:
    clear_usage_listener()
    budget = TokenBudget(limit_tokens=10.0)
    entry = budget.record({"prompt_tokens": 1}, label="x")
    assert entry["prompt_tokens"] == 1


# ── Metering hooks (opt-in, default off) ─────────────────────────────────────


def test_meter_hooks_noop_without_configured_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECPROOF_BILLING_URL", raising=False)
    reset_billing_writer()
    assert get_billing_writer() is None
    assert meter_verify_job_start("tenant-a", "job-1") is False
    assert meter_verify_job_end("tenant-a", "job-1", findings_count=2) == 0
    assert meter_craft_job_terminal("tenant-a", "job-1", "succeeded") is False


def test_meter_events_project_onto_ledger_with_configured_writer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECPROOF_BILLING_URL", f"sqlite:{tmp_path / 'billing.db'}")
    reset_billing_writer()
    writer = get_billing_writer()
    assert writer is not None
    assert meter_verify_job_start("tenant-a", "job-1") is True
    # Replay of the same event is an idempotent no-op.
    assert meter_verify_job_start("tenant-a", "job-1") is False
    assert meter_verify_job_end("tenant-a", "job-1", findings_count=3) == 1
    assert meter_verify_job_end("tenant-a", "job-1", findings_count=3) == 0
    assert meter_craft_job_terminal("tenant-a", "job-2", "succeeded") is True
    by_metric = {
        row.metric: row.units
        for row in writer.store.list_usage("tenant-a", 0.0, time.time() + 1000.0)
    }
    assert by_metric == {
        "job_verify": 1.0, "gate_findings": 3.0, "job_craft": 1.0,
    }
    reset_billing_writer()


# ── HTTP: RBAC / isolation / export / pre-flight ─────────────────────────────


@pytest.fixture()
def billing_tenant_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tenant mode + per-test SQLite identity/billing stores."""
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


@pytest.fixture()
def seeded_billing(billing_tenant_env: None) -> dict[str, Any]:
    """Tenant A (admin/auditor/operator/viewer) + tenant B usage rows."""
    from api.identity.store import get_identity_store
    from api.routes.billing import get_billing_store

    identity = get_identity_store()
    tenant_a = identity.create_tenant("tenant-a")
    tenant_b = identity.create_tenant("tenant-b")
    users: dict[str, str] = {}
    for role in ("admin", "auditor", "operator", "viewer"):
        user = identity.create_user(tenant_a.id, f"{role}@a.example.com", role=role)
        users[role] = user.id
    tokens: dict[str, str] = {}
    for role, user_id in users.items():
        _row, token = mint_token(identity, user_id, name=role)
        tokens[role] = token
    billing = get_billing_store()
    billing.upsert_subscription(tenant_a.id, "pro", "active", 0.0, 4_000_000_000.0)
    billing.record_usage("usage:a:1", tenant_a.id, "job_verify", 1.0, "job", 100.0)
    billing.record_usage("usage:b:1", tenant_b.id, "job_verify", 2.0, "job", 100.0)
    return {"tenant_a": tenant_a.id, "tenant_b": tenant_b.id, "tokens": tokens}


def test_viewer_forbidden_on_billing_endpoints(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/usage", headers=bearer(seeded_billing["tokens"]["viewer"]),
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["error"]["code"] == "TENANT_FORBIDDEN"
    assert body["schema_version"] == 1


def test_admin_usage_scoped_to_own_tenant(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/usage", headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["usage"][0]["tenant_id"] == seeded_billing["tenant_a"]


def test_auditor_usage_cross_tenant_view(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/usage", headers=bearer(seeded_billing["tokens"]["auditor"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert {row["tenant_id"] for row in body["usage"]} == {
        seeded_billing["tenant_a"], seeded_billing["tenant_b"],
    }


def test_operator_can_read_plans(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/plans", headers=bearer(seeded_billing["tokens"]["operator"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert {p["id"] for p in body["plans"]} == {"free", "pro"}


def test_subscriptions_list_requires_admin_or_auditor(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    operator_resp = client.get(
        "/api/v1/billing/subscriptions",
        headers=bearer(seeded_billing["tokens"]["operator"]),
    )
    assert operator_resp.status_code == 403
    assert operator_resp.json()["error"]["code"] == "TENANT_FORBIDDEN"
    admin_resp = client.get(
        "/api/v1/billing/subscriptions",
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json()["count"] >= 1


def test_usage_csv_export(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/usage",
        params={"from": 0, "to": 1e12, "format": "csv"},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0] == "tenant_id,event_id,metric,units,unit_label,happened_at"
    assert len(lines) == 2  # header + the one tenant-a row


def test_usage_range_validation(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/usage",
        params={"from": 100.0, "to": 50.0},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


def test_invoices_endpoint_generates_draft_with_reconciliation(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    start = _month_start("2026-08")
    store.record_usage(
        "usage:a:aug", seeded_billing["tenant_a"], "job_verify", 502.0,
        "job", start + 60.0,
    )
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/invoices",
        params={"period": "2026-08"},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 200
    invoice = resp.json()["invoices"][0]
    assert invoice["period"] == "2026-08"
    assert invoice["status"] == "draft"
    assert invoice["total"] > 0
    assert invoice["total"] == round(
        sum(float(item["amount"]) for item in invoice["line_items"]), 2,
    )


def test_job_creation_preflight_rejects_quota_exceeded(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    """POST /jobs is refused 429 QUOTA_EXCEEDED before routing (§3)."""
    from api.identity.store import get_identity_store
    from api.routes.billing import get_billing_store

    identity = get_identity_store()
    tenant = identity.create_tenant("quota-tenant")
    user = identity.create_user(tenant.id, "operator@q.example.com", role="operator")
    _row, token = mint_token(identity, user.id, name="operator")
    billing = get_billing_store()
    billing.upsert_subscription(tenant.id, "free", "active", 0.0, 4_000_000_000.0)
    quota = float(DEFAULT_PLANS[0]["quotas"]["jobs_verify"])
    billing.record_usage(
        "usage:q:full", tenant.id, "job_verify", quota, "job", time.time(),
    )
    client = TestClient(app)
    resp = client.post("/jobs", json=_payload(), headers=bearer(token))
    assert resp.status_code == 429
    body = resp.json()
    assert body["error"]["code"] == "QUOTA_EXCEEDED"
    assert body["schema_version"] == 1


# ── MySQL integration scenario (gated on MYSQL_URL, no Docker here) ───────────


@pytest.mark.integration
@pytest.mark.skipif(
    MYSQL_URL is None, reason="MYSQL_URL not set — MySQL billing test skipped",
)
def test_mysql_backend_scenario() -> None:
    assert MYSQL_URL is not None
    store = MySqlBillingStore(MYSQL_URL)
    with store.connection() as conn:
        for statement in (
            "DELETE FROM invoices",
            "DELETE FROM usage_ledger",
            "DELETE FROM billing_subscriptions",
            "DELETE FROM billing_plans",
        ):
            conn.cursor().execute(statement)
    store.ensure_schema()
    seed_default_plans(store)
    assert {p.id for p in store.list_plans()} == {"free", "pro"}
    store.upsert_subscription("tenant-mysql", "pro", "active", 0.0, 4e9)
    event_id = f"verify:tenant-mysql:{os.getpid()}:start"
    assert store.record_usage(event_id, "tenant-mysql", "job_verify", 1.0, "job")
    assert not store.record_usage(event_id, "tenant-mysql", "job_verify", 1.0, "job")
    rows = store.list_usage("tenant-mysql", 0.0, time.time() + 1000.0)
    assert len(rows) == 1
    assert store.usage_total(
        "tenant-mysql", "job_verify", 0.0, time.time() + 1000.0,
    ) == 1.0
