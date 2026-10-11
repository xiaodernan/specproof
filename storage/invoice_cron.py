"""Monthly invoice cron (BILLING_DESIGN §4 "账单周期任务").

The design's §4 sentence "月初生成 invoice" had no producer of its own:
ensure_invoice() only ran when an operator opened GET /billing/invoices, so
a month could close and no invoice would exist for anyone until somebody
remembered to look. This module is that producer — a standalone process
(``python -m storage.invoice_cron``) that, once per closed month, generates
the draft invoice of every tenant that can actually be priced.

What it pins down honestly:

* **The closed month, never the open one.** previous_period_key() derives
  the last *closed* period (year rollover included); billing an open month
  would invoice usage that is still being written. SPECPROOF_INVOICE_PERIOD
  overrides the period for rehearsals.
* **No plan, no invoice.** Candidates come from the period's usage rows and
  the subscription table; a tenant without a resolvable subscription (no
  sub, or only a cancelled one) is skipped and counted, never priced at an
  invented rate.
* **Idempotent re-entry.** ensure_invoice() returns the existing invoice
  for (tenant, period), so a crash-restart mid-month and a second cron
  instance converge on the same rows (UNIQUE(tenant_id, period)).
* **One tenant never kills the month.** A per-tenant failure is quarantined
  with its error text in the run summary and a counter, and the run
  continues.
* **Billing off is an honest no-op.** With SPECPROOF_BILLING_URL unset the
  process logs and returns 0 instead of guessing a store.

Metrics: invoice_cron_invoices_total / invoice_cron_existing_total /
invoice_cron_skipped_no_subscription_total / invoice_cron_failed_total and
the gauge invoice_cron_last_success_ts, served on INVOICE_CRON_METRICS_PORT
(default 9103) via observability.metrics_http — same shape as the outbox
relay. Wiring the port into compose.observability.yml's scrape list stays
with the deployment side, not faked here.
"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from observability.metrics import incr, set_gauge
from storage.billing import (
    BillingStore,
    billing_url,
    build_billing_store,
    ensure_invoice,
    seed_default_plans,
)

logger = logging.getLogger(__name__)

#: How often the loop wakes to check whether the closed month advanced.
DEFAULT_INTERVAL_SECONDS = 3600.0
#: Process-local /metrics port (the outbox relay owns 9101).
DEFAULT_METRICS_PORT = 9103


def previous_period_key(now: float | None = None) -> str:
    """The 'YYYY-MM' billing period that closed before ``now``.

    Derived from the first day of the current month minus one day, so the
    year rollover (2026-01-01 → 2025-12) needs no special case.
    """
    ts = time.time() if now is None else now
    first_of_month = datetime.fromtimestamp(ts, tz=UTC).replace(day=1)
    last_of_previous = first_of_month - timedelta(days=1)
    return f"{last_of_previous.year:04d}-{last_of_previous.month:02d}"


@dataclass
class InvoiceRunSummary:
    """What one generation run did, per tenant (no silent drops)."""

    period: str
    generated: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    skipped_no_subscription: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _candidate_tenants(store: BillingStore, start_ts: float, end_ts: float) -> list[str]:
    """Tenants that could owe the period: usage rows + subscription rows."""
    candidates: list[str] = [row.tenant_id for row in store.list_usage(None, start_ts, end_ts)]
    candidates.extend(sub.tenant_id for sub in store.list_subscriptions())
    out: list[str] = []
    for tenant in candidates:
        if tenant and tenant not in out:
            out.append(tenant)
    return out


def generate_invoices(
    store: BillingStore,
    period: str | None = None,
    *,
    now_fn: Callable[[], float] | None = None,
) -> InvoiceRunSummary:
    """Generate (or keep) every tenant's draft invoice for one closed period.

    Idempotent by (tenant, period): an existing invoice is reported in
    ``existing`` and never duplicated. A tenant without a resolvable
    subscription is reported in ``skipped_no_subscription`` instead of being
    priced at an invented rate; a per-tenant failure lands in ``failed``
    without stopping the run.
    """
    effective = (
        period
        if period is not None
        else previous_period_key(now_fn() if now_fn is not None else None)
    )
    start, end = _bounds(effective)
    generated: list[str] = []
    existing: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []
    for tenant in _candidate_tenants(store, start, end):
        try:
            if store.get_subscription(tenant) is None:
                skipped.append(tenant)
                continue
            if store.get_invoice(tenant, effective) is not None:
                existing.append(tenant)
                continue
            ensure_invoice(store, tenant, effective)
            generated.append(tenant)
        except Exception as exc:  # noqa: BLE001 — one tenant never kills the month
            failed.append((tenant, f"{type(exc).__name__}: {exc}"))
            logger.warning("invoice generation failed for %r: %s", tenant, exc)
    incr("invoice_cron_invoices_total", float(len(generated)))
    incr("invoice_cron_existing_total", float(len(existing)))
    incr("invoice_cron_skipped_no_subscription_total", float(len(skipped)))
    incr("invoice_cron_failed_total", float(len(failed)))
    set_gauge("invoice_cron_last_success_ts", time.time())
    return InvoiceRunSummary(
        period=effective,
        generated=generated,
        existing=existing,
        skipped_no_subscription=skipped,
        failed=failed,
    )


def _bounds(period: str) -> tuple[float, float]:
    from storage.billing import period_bounds

    return period_bounds(period)


def resolve_billing_url() -> str:
    """The metering billing URL, or '' = billing off (the default)."""
    return billing_url()


def store_from_env() -> BillingStore | None:
    """The billing store for the cron, or None when billing is off.

    The no-op guard is a real return, not a logged guess: with no
    SPECPROOF_BILLING_URL there is no store to invoice against, and
    synthesizing one would bill the wrong ledger.
    """
    url = resolve_billing_url()
    if not url:
        return None
    store = build_billing_store(url)
    seed_default_plans(store)
    return store


class InvoiceCron:
    """Generates each closed month's invoices exactly once per process."""

    def __init__(
        self,
        store: BillingStore,
        *,
        now_fn: Callable[[], float] | None = None,
        interval: float | None = None,
        metrics_port: int | None = None,
    ) -> None:
        self.store = store
        self._now_fn = now_fn if now_fn is not None else time.time
        self.interval = float(
            interval
            if interval is not None
            else os.getenv("INVOICE_CRON_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS))
        )
        self.metrics_port = int(
            metrics_port
            if metrics_port is not None
            else os.getenv("INVOICE_CRON_METRICS_PORT", str(DEFAULT_METRICS_PORT))
        )
        self._period: str | None = None
        self._running = False

    def cycle(self, now: float | None = None) -> InvoiceRunSummary | None:
        """Generate when the closed month advanced; None when nothing to do.

        The process-local ``_period`` guard keeps a restarting loop from
        re-walking the same month every tick; a process restart re-walks it
        once, idempotently (the existing invoices come back in ``existing``).
        """
        override = os.getenv("SPECPROOF_INVOICE_PERIOD", "").strip()
        now_ts = now if now is not None else self._now_fn()
        period = override or previous_period_key(now_ts)
        if period == self._period:
            return None
        summary = generate_invoices(self.store, period, now_fn=lambda: now_ts)
        self._period = period
        return summary

    def run_forever(self) -> None:
        """Run the cron loop until stopped by signal."""
        self._running = True
        from observability.metrics_http import serve_metrics_in_thread

        with contextlib.suppress(Exception):
            serve_metrics_in_thread(port=self.metrics_port)
        logger.info(
            "InvoiceCron started (interval=%.1fs, metrics port=%d)",
            self.interval, self.metrics_port,
        )
        while self._running:
            try:
                summary = self.cycle()
                if summary is not None:
                    logger.info(
                        "invoice cron: period %s generated=%d existing=%d "
                        "skipped=%d failed=%d",
                        summary.period,
                        len(summary.generated),
                        len(summary.existing),
                        len(summary.skipped_no_subscription),
                        len(summary.failed),
                    )
            except Exception:  # noqa: BLE001 — a daemon never dies silently
                logger.exception("invoice cron cycle error")
            time.sleep(self.interval)
        logger.info("InvoiceCron stopped")

    def stop(self) -> None:
        """Signal the loop to stop after the current cycle."""
        self._running = False

    @classmethod
    def run_as_process(cls) -> None:
        """Entry point for ``python -m storage.invoice_cron``."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )
        store = store_from_env()
        if store is None:
            logger.info(
                "billing unconfigured (SPECPROOF_BILLING_URL unset); "
                "invoice cron is a no-op"
            )
            return
        cron = cls(store)
        signal.signal(signal.SIGINT, lambda sig, frame: cron.stop())
        signal.signal(signal.SIGTERM, lambda sig, frame: cron.stop())
        cron.run_forever()


if __name__ == "__main__":
    InvoiceCron.run_as_process()
