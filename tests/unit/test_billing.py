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
  * per-job attribution (#233): every metered row carries its job_id and
    reads back through GET /billing/jobs/{job_id} under the same matrix
    (viewer refused, cross-tenant/unknown jobs 404, legacy mode 503).

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
    INVOICE_TRANSITIONS,
    METRIC_SET,
    METRIC_VALUES,
    BillingStore,
    BillingWriter,
    DuplicatePlanError,
    InMemoryBillingStore,
    InvalidInvoiceTransitionError,
    InvoiceNotFoundError,
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


class _FakeRateLimitRedis:
    """Backs enforce_rate_limit (imported at call time from storage.redis).

    `.client` returns self so the fail-open warning never fires; incr
    always reports 1, which no billing test throttles on.
    """

    @property
    def client(self) -> _FakeRateLimitRedis:
        return self

    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:
        pass
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

    # #148: the draft→issued→paid column now has a driveable state
    # machine — forward only, idempotent replay, refusal changes nothing.
    assert store.transition_invoice("tenant-a", "2026-08", "issued").status == "issued"
    assert store.transition_invoice("tenant-a", "2026-08", "issued").status == "issued"
    assert store.transition_invoice("tenant-a", "2026-08", "paid").status == "paid"
    with pytest.raises(InvalidInvoiceTransitionError):
        store.transition_invoice("tenant-a", "2026-08", "issued")
    with pytest.raises(InvoiceNotFoundError):
        store.transition_invoice("tenant-ghost", "2026-08", "issued")
    settled = store.get_invoice("tenant-a", "2026-08")
    assert settled is not None and settled.status == "paid"
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


def test_invoice_lifecycle_refuses_skips_backwards_and_unknown_words(
    tmp_path: Path,
) -> None:
    """#148: one place spells out every refused step of draft→issued→paid."""
    store = SqliteBillingStore(tmp_path / "billing.db")
    seed_default_plans(store)
    store.create_invoice(
        "tenant-a", "2026-08", [{"metric": "plan", "amount": 1.0}],
        1.0, "USD", "draft",
    )
    # draft -> paid skips issued: refused, reported with both ends,
    # and the row is untouched by the refusal.
    with pytest.raises(InvalidInvoiceTransitionError) as exc:
        store.transition_invoice("tenant-a", "2026-08", "paid")
    assert exc.value.current == "draft"
    assert exc.value.requested == "paid"
    untouched = store.get_invoice("tenant-a", "2026-08")
    assert untouched is not None and untouched.status == "draft"
    # An unknown word is a vocabulary error, not a lifecycle step.
    with pytest.raises(ValueError):
        store.transition_invoice("tenant-a", "2026-08", "settled")
    assert store.transition_invoice("tenant-a", "2026-08", "issued").status == "issued"
    assert store.transition_invoice("tenant-a", "2026-08", "paid").status == "paid"
    # paid is terminal: backward and forward-skip both refused.
    with pytest.raises(InvalidInvoiceTransitionError):
        store.transition_invoice("tenant-a", "2026-08", "issued")
    with pytest.raises(InvalidInvoiceTransitionError):
        store.transition_invoice("tenant-a", "2026-08", "draft")
    # reverse control: another tenant has no invoice here to move.
    with pytest.raises(InvoiceNotFoundError):
        store.transition_invoice("tenant-b", "2026-08", "issued")
    # The map itself is exactly the §4 vocabulary, nothing more.
    assert {k: sorted(v) for k, v in INVOICE_TRANSITIONS.items()} == {
        "draft": ["issued"], "issued": ["paid"], "paid": [],
    }
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
    monkeypatch.setattr("storage.redis.RedisStore", _FakeRateLimitRedis)


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
    billing.record_usage(
        "usage:a:1", tenant_a.id, "job_verify", 1.0, "job", 100.0,
        job_id="job-a-1",
    )
    billing.record_usage(
        "usage:b:1", tenant_b.id, "job_verify", 2.0, "job", 100.0,
        job_id="job-b-1",
    )
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
    assert lines[0] == (
        "tenant_id,event_id,metric,units,unit_label,happened_at,job_id"
    )
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
    assert store.record_usage(
        f"craft:tenant-mysql:{os.getpid()}:terminal", "tenant-mysql",
        "job_craft", 1.0, "job", job_id="job-mysql",
    )
    job_rows = store.list_usage_by_job("tenant-mysql", "job-mysql")
    assert [(r.metric, r.job_id) for r in job_rows] == [("job_craft", "job-mysql")]
    rows = store.list_usage("tenant-mysql", 0.0, time.time() + 1000.0)
    assert len(rows) == 2
    assert store.usage_total(
        "tenant-mysql", "job_verify", 0.0, time.time() + 1000.0,
    ) == 1.0


# ── Per-job attribution & read path (#233) ───────────────────────────────


# Declared domain: the ledger slice of "每作业成本会计" — every metered row
# carries the job it belongs to (job_id column; pre-#233 rows read back as
# ""), TokenBudget entries stamp the job before the billing projection, and
# GET /billing/jobs/{job_id} reads one job's metered usage back with the
# §2 RBAC matrix. Bidirectional doors:
#   green: meter/LLM rows attribute to their job and read back with totals;
#   red:   viewer refused, cross-tenant and unknown jobs answer 404
#          JOB_NOT_FOUND, legacy mode answers 503 before any query, and a
#          pre-#233 ledger upgrades in place with its rows intact.


def test_usage_rows_carry_job_id_in_memory_and_sqlite(tmp_path: Path) -> None:
    stores: list[Any] = [InMemoryBillingStore(), SqliteBillingStore(tmp_path / "b.db")]
    try:
        for store in stores:
            assert store.record_usage(
                "ev:1", "tenant-a", "job_verify", 1.0, "job", 100.0, job_id="job-9",
            )
            assert store.record_usage("ev:2", "tenant-a", "job_craft", 1.0, "job", 101.0)
            rows = store.list_usage_by_job("tenant-a", "job-9")
            assert [(r.event_id, r.job_id) for r in rows] == [("ev:1", "job-9")]
            assert store.list_usage_by_job("tenant-a", "job-none") == []
            assert store.list_usage_by_job("tenant-b", "job-9") == []
            assert store.list_usage_by_job("tenant-a", "") == []
            unattributed = [
                r for r in store.list_usage("tenant-a", 0.0, 1e12)
                if r.event_id == "ev:2"
            ]
            assert [(r.event_id, r.job_id) for r in unattributed] == [("ev:2", "")]
    finally:
        for store in stores:
            close = getattr(store, "close", None)
            if close is not None:
                close()


def test_pre_job_ledger_is_upgraded_in_place(tmp_path: Path) -> None:
    """A ledger written before #233 opens, gains the column, keeps its rows."""
    import sqlite3 as _sqlite3

    db = tmp_path / "legacy.db"
    conn = _sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE usage_ledger ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "tenant_id VARCHAR(36) NOT NULL, "
        "event_id VARCHAR(255) NOT NULL UNIQUE, "
        "metric VARCHAR(32) NOT NULL, "
        "units DOUBLE NOT NULL, "
        "unit_label VARCHAR(64) NOT NULL DEFAULT '', "
        "happened_at DOUBLE NOT NULL);"
        "INSERT INTO usage_ledger "
        "(tenant_id, event_id, metric, units, unit_label, happened_at) "
        "VALUES ('tenant-a', 'legacy:1', 'job_verify', 1.0, 'job', 50.0);"
    )
    conn.close()

    store = SqliteBillingStore(db)
    try:
        old = store.list_usage("tenant-a", 0.0, 1e12)
        assert [(r.event_id, r.job_id) for r in old] == [("legacy:1", "")]
        assert store.record_usage(
            "ev:new", "tenant-a", "job_craft", 1.0, "job", 60.0, job_id="job-new",
        )
        upgraded = store.list_usage_by_job("tenant-a", "job-new")
        assert [(r.event_id, r.job_id) for r in upgraded] == [("ev:new", "job-new")]
    finally:
        store.close()


def test_meter_events_attribute_rows_to_their_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("SPECPROOF_BILLING_URL", f"sqlite:{tmp_path / 'billing.db'}")
    reset_billing_writer()
    writer = get_billing_writer()
    assert writer is not None
    assert meter_verify_job_start("tenant-a", "job-1")
    assert meter_verify_job_end("tenant-a", "job-1", findings_count=2)
    assert meter_craft_job_terminal("tenant-a", "job-2", "succeeded")
    job1 = writer.store.list_usage_by_job("tenant-a", "job-1")
    assert sorted(r.metric for r in job1) == ["gate_findings", "job_verify"]
    assert all(r.job_id == "job-1" for r in job1)
    job2 = writer.store.list_usage_by_job("tenant-a", "job-2")
    assert [(r.metric, r.job_id) for r in job2] == [("job_craft", "job-2")]
    assert writer.store.list_usage_by_job("tenant-a", "job-3") == []
    reset_billing_writer()


def test_llm_entry_job_id_flows_to_the_ledger(tmp_path: Path) -> None:
    store = SqliteBillingStore(tmp_path / "billing.db")
    writer = BillingWriter(store)
    token = TENANT_SCOPE_VAR.set(TenantScope(tenant_id="tenant-a"))
    try:
        created = writer.record_llm_usage(
            {
                "label": "plan",
                "timestamp": "2026-10-10T00:00:00+00:00",
                "used_after": 12.0,
                "job_id": "job-llm",
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "prompt_cache_hit_tokens": 8,
                "reasoning_tokens": 2,
            },
        )
        writer.record_llm_usage(
            {
                "label": "plan",
                "timestamp": "2026-10-10T00:00:01+00:00",
                "used_after": 13.0,
                "prompt_tokens": 7,
            },
        )
    finally:
        TENANT_SCOPE_VAR.reset(token)
    assert created == [True, True, True, True]
    by_metric = {
        r.metric: r.units for r in store.list_usage_by_job("tenant-a", "job-llm")
    }
    assert by_metric == {
        "llm_tokens_in": 100.0,
        "llm_tokens_out": 10.0,
        "llm_cache_hit_tokens": 8.0,
        "llm_reasoning_tokens": 2.0,
    }
    assert store.list_usage_by_job("tenant-a", "") == []
    jobless = [
        r
        for r in store.list_usage("tenant-a", 0.0, time.time() + 1000.0)
        if r.metric == "llm_tokens_in" and r.job_id == ""
    ]
    assert [r.units for r in jobless] == [7.0]
    store.close()


def test_budget_record_stamps_the_job_id() -> None:
    clear_usage_listener()
    budget = TokenBudget(limit_tokens=1000.0)
    stamped = budget.record({"prompt_tokens": 5}, label="plan", job_id="job-b")
    plain = budget.record({"prompt_tokens": 6}, label="plan")
    assert stamped["job_id"] == "job-b"
    assert plain["job_id"] == ""


def test_job_usage_endpoint_scopes_to_the_caller_tenant(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/jobs/job-a-1",
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job-a-1"
    assert body["count"] == 1
    assert body["usage"][0]["job_id"] == "job-a-1"
    assert body["totals"] == {"job_verify": 1.0}


def test_job_usage_endpoint_hides_other_tenants_as_404(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/jobs/job-b-1",
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_job_usage_endpoint_auditor_reads_cross_tenant(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/jobs/job-b-1",
        headers=bearer(seeded_billing["tokens"]["auditor"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["usage"][0]["tenant_id"] == seeded_billing["tenant_b"]
    assert body["totals"] == {"job_verify": 2.0}


def test_job_usage_endpoint_unknown_job_is_404(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/jobs/job-nope",
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_viewer_is_refused_the_job_usage_endpoint(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/jobs/job-a-1",
        headers=bearer(seeded_billing["tokens"]["viewer"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "TENANT_FORBIDDEN"


def test_job_usage_endpoint_needs_tenant_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy mode answers 503 before any ledger query (like /admin)."""
    monkeypatch.delenv("SPECPROOF_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    from api.identity.oidc import reset_oidc_validator
    from api.identity.store import reset_identity_store
    from api.routes.billing import reset_billing_store

    reset_identity_store()
    reset_oidc_validator()
    reset_billing_store()
    client = TestClient(app)
    resp = client.get("/api/v1/billing/jobs/job-a-1")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    reset_billing_store()


def test_job_endpoint_aggregates_lifecycle_and_llm_rows(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    """The per-job view totals every metered class for one job (#233)."""
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    assert store.record_usage(
        "verify:start:job-a-2", seeded_billing["tenant_a"], "job_verify", 1.0,
        "job", 100.0, job_id="job-a-2",
    )
    assert store.record_usage(
        "llm:in:job-a-2", seeded_billing["tenant_a"], "llm_tokens_in", 120.0,
        "token", 101.0, job_id="job-a-2",
    )
    client = TestClient(app)
    resp = client.get(
        "/api/v1/billing/jobs/job-a-2",
        headers=bearer(seeded_billing["tokens"]["operator"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["totals"] == {"job_verify": 1.0, "llm_tokens_in": 120.0}
    assert {row["job_id"] for row in body["usage"]} == {"job-a-2"}


# ── Invoice issuance entry point (#244) ────────────────────────────────


def _draft_for(
    store: Any, tenant_id: str, period: str = "2026-08",
) -> Any:
    invoice = ensure_invoice(store, tenant_id, period, now_fn=lambda: 1_000_000.0)
    assert invoice.status == "draft"
    return invoice


def test_admin_walks_draft_issued_paid(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    draft = _draft_for(store, seeded_billing["tenant_a"])
    client = TestClient(app)
    headers = bearer(seeded_billing["tokens"]["admin"])

    issued = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "issued"}, headers=headers,
    )
    assert issued.status_code == 200
    body = issued.json()["invoice"]
    assert body["status"] == "issued"
    # Money fields are carried, never re-derived on the way out.
    assert body["id"] == draft.id
    assert body["total"] == draft.total
    assert body["line_items"] == draft.line_items

    paid = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "paid"}, headers=headers,
    )
    assert paid.status_code == 200
    assert paid.json()["invoice"]["status"] == "paid"


def test_reasking_the_held_status_is_an_idempotent_noop(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    _draft_for(store, seeded_billing["tenant_a"])
    client = TestClient(app)
    headers = bearer(seeded_billing["tokens"]["admin"])
    first = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "issued"}, headers=headers,
    )
    again = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "issued"}, headers=headers,
    )
    assert first.status_code == 200
    assert again.status_code == 200
    assert again.json()["invoice"]["id"] == first.json()["invoice"]["id"]
    assert again.json()["invoice"]["status"] == "issued"


def test_skipping_issued_is_refused_and_names_the_step(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    _draft_for(store, seeded_billing["tenant_a"])
    client = TestClient(app)
    resp = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "paid"},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "STATE_CONFLICT"
    assert body["schema_version"] == 1
    detail = body["detail"]
    assert "draft" in detail and "paid" in detail
    # The refused step left the invoice where it was.
    still = store.get_invoice(seeded_billing["tenant_a"], "2026-08")
    assert still is not None and still.status == "draft"


def test_paid_is_terminal_but_replay_safe(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    _draft_for(store, seeded_billing["tenant_a"])
    client = TestClient(app)
    headers = bearer(seeded_billing["tokens"]["admin"])
    for status in ("issued", "paid"):
        assert client.post(
            "/api/v1/billing/invoices/2026-08/status",
            json={"status": status}, headers=headers,
        ).status_code == 200
    # Backwards from paid is refused with the step named.
    back = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "issued"}, headers=headers,
    )
    assert back.status_code == 409
    assert "paid" in back.json()["detail"]
    # Re-asking the status already held is a crash-retry noop, not a conflict.
    replay = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "paid"}, headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json()["invoice"]["status"] == "paid"


def test_only_admin_may_issue_invoices(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    _draft_for(store, seeded_billing["tenant_a"])
    client = TestClient(app)
    for role in ("operator", "auditor", "viewer"):
        resp = client.post(
            "/api/v1/billing/invoices/2026-08/status",
            json={"status": "issued"},
            headers=bearer(seeded_billing["tokens"][role]),
        )
        assert resp.status_code == 403, role
        assert resp.json()["error"]["code"] == "TENANT_FORBIDDEN"


def test_unknown_period_is_404(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/billing/invoices/1999-01/status",
        json={"status": "issued"},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVOICE_NOT_FOUND"


def test_cross_tenant_issuance_is_indistinguishable_and_harmless(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    _draft_for(store, seeded_billing["tenant_b"])
    client = TestClient(app)
    resp = client.post(
        "/api/v1/billing/invoices/2026-08/status",
        json={"status": "issued"},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVOICE_NOT_FOUND"
    # The other tenant's invoice is exactly where it was.
    other = store.get_invoice(seeded_billing["tenant_b"], "2026-08")
    assert other is not None and other.status == "draft"


def test_issuance_needs_tenant_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy mode answers 503 before any query (like every other endpoint)."""
    monkeypatch.delenv("SPECPROOF_AUTH_ENABLED", raising=False)
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    from api.identity.oidc import reset_oidc_validator
    from api.identity.store import reset_identity_store
    from api.routes.billing import reset_billing_store

    reset_identity_store()
    reset_oidc_validator()
    reset_billing_store()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/billing/invoices/2026-08/status", json={"status": "issued"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    reset_billing_store()


def test_a_malformed_period_is_422(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/billing/invoices/2026-13/status",
        json={"status": "issued"},
        headers=bearer(seeded_billing["tokens"]["admin"]),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


def test_a_target_outside_the_walk_is_422(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    client = TestClient(app)
    for status in ("draft", "refund", "void"):
        resp = client.post(
            "/api/v1/billing/invoices/2026-08/status",
            json={"status": status},
            headers=bearer(seeded_billing["tokens"]["admin"]),
        )
        assert resp.status_code == 422, status
        assert resp.json()["error"]["code"] == "VALIDATION_FAILED"


def test_the_transition_counter_counts_advances_only(
    billing_tenant_env: None, seeded_billing: dict[str, Any],
) -> None:
    from api.routes.billing import get_billing_store

    store = get_billing_store()
    _draft_for(store, seeded_billing["tenant_a"])
    client = TestClient(app)
    headers = bearer(seeded_billing["tokens"]["admin"])
    before = snapshot_counters()
    for status in ("issued", "issued", "paid", "paid"):
        client.post(
            "/api/v1/billing/invoices/2026-08/status",
            json={"status": status}, headers=headers,
        )
    after = snapshot_counters()
    # issued/issued/paid/paid: exactly two advances (and two refused noops).
    assert after - before == 2.0


def snapshot_counters() -> float:
    from observability.metrics import snapshot

    return snapshot()["counters"].get("invoice_status_transitions_total", 0.0)
