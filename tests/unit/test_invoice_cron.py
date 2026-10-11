"""Monthly invoice cron tests (BILLING_DESIGN §4 "账单周期任务", #234).

The design's §4 sentence "月初生成 invoice" had no producer of its own:
ensure_invoice() only ran when an operator opened GET /billing/invoices,
so a month could close and no invoice would exist for anyone until
somebody remembered to look. These tests pin the cron that closes the loop:

  * the closed month (previous_period_key) is derived, including the year
    rollover — never the currently open period;
  * every tenant holding a subscription is invoiced; a tenant without one
    is skipped and counted, never guessed at (no plan = no price);
  * re-running the same period is idempotent (existing invoices returned,
    no duplicates), and one tenant's failure is quarantined instead of
    killing the run;
  * the loop generates once per closed period, not once per tick;
  * with billing unconfigured the process is an honest no-op.

All mock — SQLite backend, no Docker, no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from observability.metrics import snapshot
from storage.billing import (
    SqliteBillingStore,
    period_bounds,
    seed_default_plans,
)
from storage.invoice_cron import (
    InvoiceCron,
    generate_invoices,
    previous_period_key,
    resolve_billing_url,
    store_from_env,
)

_OCT = 1_791_158_400.0  # 2026-10-05T00:00:00Z
_NOV = 1_793_836_800.0  # 2026-11-05T00:00:00Z
_JAN = 1_767_225_600.0  # 2026-01-01T00:00:00Z


def _store(tmp_path: Path) -> SqliteBillingStore:
    store = SqliteBillingStore(tmp_path / "billing.db")
    seed_default_plans(store)
    return store


def _span(period: str) -> tuple[float, float]:
    start, end = period_bounds(period)
    return start + 60.0, end - 60.0


def test_previous_period_key_is_the_closed_month() -> None:
    assert previous_period_key(_OCT) == "2026-09"


def test_previous_period_key_crosses_the_year_boundary() -> None:
    assert previous_period_key(_JAN) == "2025-12"


def test_every_subscribed_tenant_gets_a_draft(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    store.upsert_subscription("tenant-b", "free", "active", 0.0, 4_000_000_000.0)
    start, _end = _span("2026-09")
    assert store.record_usage(
        "verify:a:start", "tenant-a", "job_verify", 3.0, "job", start,
    )
    summary = generate_invoices(store, "2026-09", now_fn=lambda: _OCT)
    assert summary.period == "2026-09"
    assert sorted(summary.generated) == ["tenant-a", "tenant-b"]
    assert summary.existing == []
    assert summary.failed == []
    # The subscribed-but-silent tenant is still invoiced: the plan's base
    # monthly fee is a real line item, not "no usage therefore no bill".
    silent = store.get_invoice("tenant-b", "2026-09")
    assert silent is not None
    assert [item["metric"] for item in silent.line_items] == ["plan"]
    store.close()


def test_re_running_the_same_period_changes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    first = generate_invoices(store, "2026-09", now_fn=lambda: _OCT)
    invoice = store.get_invoice("tenant-a", "2026-09")
    assert invoice is not None
    second = generate_invoices(store, "2026-09", now_fn=lambda: _OCT)
    assert first.generated == ["tenant-a"]
    assert second.generated == []
    assert second.existing == ["tenant-a"]
    again = store.get_invoice("tenant-a", "2026-09")
    assert again is not None and again.id == invoice.id
    store.close()


def test_a_tenant_without_a_subscription_is_skipped(tmp_path: Path) -> None:
    store = _store(tmp_path)
    start, _end = _span("2026-09")
    assert store.record_usage(
        "verify:a:start", "tenant-a", "job_verify", 1.0, "job", start,
    )
    summary = generate_invoices(store, "2026-09", now_fn=lambda: _OCT)
    assert summary.generated == []
    assert summary.skipped_no_subscription == ["tenant-a"]
    assert store.get_invoice("tenant-a", "2026-09") is None
    store.close()


def test_one_tenant_failure_is_quarantined_not_fatal(tmp_path: Path) -> None:
    class _PoisonOnTenantB(SqliteBillingStore):
        """get_invoice explodes for one tenant only."""

        def get_invoice(self, tenant_id: str, period: str) -> Any:
            if tenant_id == "tenant-b":
                raise RuntimeError("ledger row quarantined")
            return super().get_invoice(tenant_id, period)

    db = tmp_path / "billing.db"
    plain = SqliteBillingStore(db)
    seed_default_plans(plain)
    plain.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    plain.upsert_subscription("tenant-b", "pro", "active", 0.0, 4_000_000_000.0)
    plain.close()
    poison = _PoisonOnTenantB(db)
    summary = generate_invoices(poison, "2026-09", now_fn=lambda: _OCT)
    assert summary.generated == ["tenant-a"]
    assert [tenant for tenant, _err in summary.failed] == ["tenant-b"]
    poison.close()


def test_generate_defaults_to_the_closed_month(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    start, _end = _span("2026-09")
    assert store.record_usage(
        "verify:a:start", "tenant-a", "job_verify", 1.0, "job", start,
    )
    summary = generate_invoices(store, now_fn=lambda: _OCT)
    assert summary.period == "2026-09"
    assert summary.generated == ["tenant-a"]
    store.close()


def test_cycle_generates_once_per_closed_period(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    cron = InvoiceCron(store, now_fn=lambda: _OCT)
    first = cron.cycle()
    assert first is not None and first.period == "2026-09"
    assert cron.cycle() is None  # same closed period: no second pass
    second = cron.cycle(_NOV)
    assert second is not None and second.period == "2026-10"
    assert second.generated == ["tenant-a"]
    assert second.existing == []  # a NEW closed period is never "existing"
    store.close()


def test_the_counters_expose_the_run(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    before = snapshot()["counters"].get("invoice_cron_invoices_total", 0.0)
    generate_invoices(store, "2026-09", now_fn=lambda: _OCT)
    after = snapshot()["counters"].get("invoice_cron_invoices_total", 0.0)
    assert after == before + 1.0
    assert snapshot()["gauges"]["invoice_cron_last_success_ts"] > 0.0
    store.close()


def test_unconfigured_billing_is_an_empty_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPECPROOF_BILLING_URL", raising=False)
    assert resolve_billing_url() == ""
    # The process-level guard is a real return, not a logged guess: the
    # no-op must be observable without running the loop.
    assert store_from_env() is None


def test_configured_billing_resolves_a_seeded_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv(
        "SPECPROOF_BILLING_URL", f"sqlite:{tmp_path / 'cron.db'}",
    )
    store = store_from_env()
    assert store is not None
    assert {plan.id for plan in store.list_plans()} == {"free", "pro"}
    store.close()
