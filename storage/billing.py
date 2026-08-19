"""Multi-tenant billing and usage ledger store (industrialization phase 6).

docs/architecture/BILLING_DESIGN.md is the authoritative spec. One
protocol, three interchangeable backends, mirroring storage/identity.py:

* InMemoryBillingStore — development and tests;
* SqliteBillingStore — file-based fallback used by unit tests (no Docker);
* MySqlBillingStore — production (PyMySQL + DictCursor, single-cursor
  execute-then-fetch discipline per CLAUDE.md).

Model (§1): billing_plans (quotas/overage JSON), billing_subscriptions,
usage_ledger (idempotent by unique event_id — replay never double-charges)
and invoices (line_items JSON, total, draft→issued→paid). Timestamps are
epoch seconds with an injectable now_fn clock; every SQL statement is fully
static ('?' placeholders translated to '%s' for PyMySQL) so all values
travel through placeholders (bandit B608-safe).

Metering is opt-in: the module-level BillingWriter registry defaults to
None (SPECPROOF_BILLING_URL unset → zero behavior change). The hooks
(meter_verify_job_start / meter_verify_job_end / meter_craft_job_terminal)
and the TokenBudget usage listener (providers/budget.py) all project
events onto the ledger only when a writer is configured. The production
MySQL DDL is created by infra/mysql/migrations/0007_tenant_billing.sql;
MySqlBillingStore.ensure_schema() emits the same idempotent DDL so both
paths converge on one schema (SQLite owns a DDL variant because it has no
inline-INDEX syntax).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import unquote, urlsplit

import pymysql
from pymysql.cursors import DictCursor

from storage.tenant_scope import current_scope

logger = logging.getLogger(__name__)

#: The seven ledger metrics (BILLING_DESIGN.md §1) — the exact names the
#: design mandates; the consistency test keeps them in sync with the SQL.
METRIC_VALUES: tuple[str, ...] = (
    "job_verify",
    "job_craft",
    "llm_tokens_in",
    "llm_tokens_out",
    "llm_cache_hit_tokens",
    "llm_reasoning_tokens",
    "gate_findings",
)
METRIC_SET: frozenset[str] = frozenset(METRIC_VALUES)

#: The four LLM token classes (one ledger row per class per usage record).
LLM_TOKEN_METRICS: frozenset[str] = frozenset(
    {"llm_tokens_in", "llm_tokens_out", "llm_cache_hit_tokens", "llm_reasoning_tokens"}
)

#: Ledger metric → plan quota key (BILLING_DESIGN.md §1 names the quota
#: fields jobs_verify/jobs_craft while the ledger metrics are job_verify/
#: job_craft; the four LLM classes all draw from the single llm_tokens
#: quota). Metrics without a quota key (gate_findings) are not enforced.
QUOTA_KEY_BY_METRIC: dict[str, str] = {
    "job_verify": "jobs_verify",
    "job_craft": "jobs_craft",
    "llm_tokens_in": "llm_tokens",
    "llm_tokens_out": "llm_tokens",
    "llm_cache_hit_tokens": "llm_tokens",
    "llm_reasoning_tokens": "llm_tokens",
    "gate_findings": "gate_findings",
}

SUBSCRIPTION_STATUS_VALUES: frozenset[str] = frozenset({"active", "cancelled"})
INVOICE_STATUS_VALUES: frozenset[str] = frozenset({"draft", "issued", "paid"})

DEFAULT_CURRENCY = "USD"

#: Seeded plans: free is hard-stop everywhere (empty overage); pro is
#: soft-overage for the metered job/token metrics (BILLING_DESIGN.md §3).
DEFAULT_PLANS: tuple[dict[str, Any], ...] = (
    {
        "id": "free",
        "name": "Free",
        "price_monthly": 0.0,
        "quotas": {
            "jobs_verify": 20.0, "jobs_craft": 2.0, "llm_tokens": 200_000.0,
            "cases": 50.0, "seats": 3.0,
        },
        "overage": {},
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_monthly": 99.0,
        "quotas": {
            "jobs_verify": 500.0, "jobs_craft": 50.0, "llm_tokens": 5_000_000.0,
            "cases": 1_000.0, "seats": 20.0,
        },
        "overage": {
            "job_verify": 0.10, "job_craft": 1.0, "llm_tokens": 0.000002,
        },
    },
)


class BillingStoreError(RuntimeError):
    """Base error for every billing-store failure."""


class DuplicatePlanError(BillingStoreError):
    """A plan with this id already exists."""


class PlanNotFoundError(BillingStoreError):
    """The referenced plan id does not exist."""


class InvoiceExistsError(BillingStoreError):
    """An invoice for this (tenant, period) already exists."""


class QuotaExceededError(BillingStoreError):
    """A subscription quota hard-stop refused the planned usage (§3).

    Carries metric / quota / used / planned so callers can report the
    overrun; api/middleware.py maps it to the stable 429 QUOTA_EXCEEDED.
    """

    def __init__(
        self,
        metric: str,
        quota: float,
        used: float,
        planned: float,
        tenant_id: str = "",
    ) -> None:
        self.metric = metric
        self.quota = quota
        self.used = used
        self.planned = planned
        self.tenant_id = tenant_id
        super().__init__(
            f"quota exceeded for tenant {tenant_id!r}: metric={metric}, "
            f"quota={quota:g}, used={used:g}, planned={planned:g}"
        )


@dataclass(frozen=True)
class Plan:
    id: str
    name: str
    price_monthly: float
    quotas: dict[str, float]
    overage: dict[str, float]


@dataclass(frozen=True)
class Subscription:
    id: str
    tenant_id: str
    plan_id: str
    status: str
    period_start: float
    period_end: float


@dataclass(frozen=True)
class UsageRecord:
    id: int
    tenant_id: str
    event_id: str
    metric: str
    units: float
    unit_label: str
    happened_at: float


@dataclass(frozen=True)
class Invoice:
    id: str
    tenant_id: str
    period: str
    line_items: list[dict[str, Any]]
    total: float
    currency: str
    status: str


@dataclass(frozen=True)
class QuotaDecision:
    """The outcome of one quota pre-flight check (§3)."""

    allowed: bool
    enforced: bool
    quota: float
    used: float
    planned: float
    overage_units: float
    ratio: float


class BillingStore(Protocol):
    """Single source of truth for plan/subscription/ledger/invoice semantics."""

    def ensure_schema(self) -> None: ...
    def close(self) -> None: ...

    def create_plan(
        self,
        plan_id: str,
        name: str,
        price_monthly: float,
        quotas: dict[str, float],
        overage: dict[str, float],
    ) -> Plan: ...
    def get_plan(self, plan_id: str) -> Plan | None: ...
    def list_plans(self) -> list[Plan]: ...

    def upsert_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        status: str,
        period_start: float,
        period_end: float,
    ) -> Subscription: ...
    def get_subscription(self, tenant_id: str) -> Subscription | None: ...
    def list_subscriptions(self) -> list[Subscription]: ...

    def record_usage(
        self,
        event_id: str,
        tenant_id: str,
        metric: str,
        units: float,
        unit_label: str = "",
        happened_at: float | None = None,
    ) -> bool: ...
    def list_usage(
        self, tenant_id: str | None, from_ts: float, to_ts: float,
    ) -> list[UsageRecord]: ...
    def usage_total(
        self, tenant_id: str, metric: str, from_ts: float, to_ts: float,
    ) -> float: ...

    def create_invoice(
        self,
        tenant_id: str,
        period: str,
        line_items: list[dict[str, Any]],
        total: float,
        currency: str,
        status: str,
    ) -> Invoice: ...
    def get_invoice(self, tenant_id: str, period: str) -> Invoice | None: ...
    def list_invoices(self, tenant_id: str) -> list[Invoice]: ...


# ── Validation / parsing helpers ─────────────────────────────────────────────


def _validate_metric(metric: str) -> str:
    if metric not in METRIC_SET:
        raise ValueError(f"unknown metric {metric!r}; expected one of {METRIC_VALUES}")
    return metric


def _validate_subscription_status(status: str) -> str:
    if status not in SUBSCRIPTION_STATUS_VALUES:
        raise ValueError(
            f"unknown subscription status {status!r}; "
            f"expected one of {sorted(SUBSCRIPTION_STATUS_VALUES)}"
        )
    return status


def _validate_invoice_status(status: str) -> str:
    if status not in INVOICE_STATUS_VALUES:
        raise ValueError(
            f"unknown invoice status {status!r}; "
            f"expected one of {sorted(INVOICE_STATUS_VALUES)}"
        )
    return status


def _parse_metric_map(raw: Any) -> dict[str, float]:
    """Parse a quotas/overage column (JSON object or dict) into numbers."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        raw = parsed
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in raw.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def _parse_line_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        raw = parsed
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _month_bounds(year: int, month: int) -> tuple[float, float]:
    """UTC epoch bounds [start, end) of a calendar month."""
    start = datetime(year, month, 1, tzinfo=UTC).timestamp()
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=UTC).timestamp()
    else:
        end = datetime(year, month + 1, 1, tzinfo=UTC).timestamp()
    return start, end


def current_period_key(now: float | None = None) -> str:
    """The 'YYYY-MM' billing period containing the given instant."""
    ts = time.time() if now is None else now
    dt = datetime.fromtimestamp(ts, tz=UTC)
    return f"{dt.year:04d}-{dt.month:02d}"


def period_bounds(period: str) -> tuple[float, float]:
    """UTC epoch bounds [start, end) for a 'YYYY-MM' period string."""
    year_text, month_text = period.split("-", 1)
    return _month_bounds(int(year_text), int(month_text))


# ── Shared portable SQL (the hub the SQL backends read) ──────────────────────
# Fully static statements; every value travels through placeholders. The
# metric literals are kept in sync with METRIC_SET by the consistency test
# in tests/unit/test_billing.py.


_SCHEMA_SQLITE: str = (
    "CREATE TABLE IF NOT EXISTS billing_plans ("
    "id VARCHAR(64) PRIMARY KEY, "
    "name VARCHAR(255) NOT NULL, "
    "price_monthly DOUBLE NOT NULL DEFAULT 0, "
    "quotas TEXT NOT NULL, "
    "overage TEXT NOT NULL)"
    ";"
    "CREATE TABLE IF NOT EXISTS billing_subscriptions ("
    "id VARCHAR(36) PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "plan_id VARCHAR(64) NOT NULL, "
    "status VARCHAR(32) NOT NULL DEFAULT 'active', "
    "period_start DOUBLE NOT NULL, "
    "period_end DOUBLE NOT NULL)"
    ";"
    "CREATE INDEX IF NOT EXISTS idx_billing_subs_tenant "
    "ON billing_subscriptions (tenant_id)"
    ";"
    "CREATE TABLE IF NOT EXISTS usage_ledger ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "event_id VARCHAR(255) NOT NULL UNIQUE, "
    "metric VARCHAR(32) NOT NULL, "
    "units DOUBLE NOT NULL, "
    "unit_label VARCHAR(64) NOT NULL DEFAULT '', "
    "happened_at DOUBLE NOT NULL)"
    ";"
    "CREATE INDEX IF NOT EXISTS idx_usage_tenant_time "
    "ON usage_ledger (tenant_id, happened_at)"
    ";"
    "CREATE INDEX IF NOT EXISTS idx_usage_tenant_metric "
    "ON usage_ledger (tenant_id, metric)"
    ";"
    "CREATE TABLE IF NOT EXISTS invoices ("
    "id VARCHAR(36) PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "period VARCHAR(7) NOT NULL, "
    "line_items TEXT NOT NULL, "
    "total DOUBLE NOT NULL, "
    "currency VARCHAR(8) NOT NULL DEFAULT 'USD', "
    "status VARCHAR(32) NOT NULL DEFAULT 'draft', "
    "UNIQUE (tenant_id, period))"
    ";"
    "CREATE INDEX IF NOT EXISTS idx_invoices_tenant ON invoices (tenant_id)"
)

# MySQL has no CREATE INDEX IF NOT EXISTS; indexes live inline in CREATE
# TABLE so ensure_schema() stays idempotent against the migration-created
# production schema (infra/mysql/migrations/0007_tenant_billing.sql). JSON
# columns hold the plan/invoice payloads exactly like the migration.
_SCHEMA_MYSQL: str = (
    "CREATE TABLE IF NOT EXISTS billing_plans ("
    "id VARCHAR(64) PRIMARY KEY, "
    "name VARCHAR(255) NOT NULL, "
    "price_monthly DOUBLE NOT NULL DEFAULT 0, "
    "quotas JSON NOT NULL, "
    "overage JSON NOT NULL"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ";"
    "CREATE TABLE IF NOT EXISTS billing_subscriptions ("
    "id VARCHAR(36) PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "plan_id VARCHAR(64) NOT NULL, "
    "status VARCHAR(32) NOT NULL DEFAULT 'active', "
    "period_start DOUBLE NOT NULL, "
    "period_end DOUBLE NOT NULL, "
    "INDEX idx_billing_subs_tenant (tenant_id)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ";"
    "CREATE TABLE IF NOT EXISTS usage_ledger ("
    "id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "event_id VARCHAR(255) NOT NULL, "
    "metric VARCHAR(32) NOT NULL, "
    "units DOUBLE NOT NULL, "
    "unit_label VARCHAR(64) NOT NULL DEFAULT '', "
    "happened_at DOUBLE NOT NULL, "
    "UNIQUE KEY uq_usage_event (event_id), "
    "INDEX idx_usage_tenant_time (tenant_id, happened_at), "
    "INDEX idx_usage_tenant_metric (tenant_id, metric)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ";"
    "CREATE TABLE IF NOT EXISTS invoices ("
    "id VARCHAR(36) PRIMARY KEY, "
    "tenant_id VARCHAR(36) NOT NULL, "
    "period VARCHAR(7) NOT NULL, "
    "line_items JSON NOT NULL, "
    "total DOUBLE NOT NULL, "
    "currency VARCHAR(8) NOT NULL DEFAULT 'USD', "
    "status VARCHAR(32) NOT NULL DEFAULT 'draft', "
    "UNIQUE KEY uq_invoices_tenant_period (tenant_id, period), "
    "INDEX idx_invoices_tenant (tenant_id)"
    ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
)

_INSERT_PLAN_SQL: str = (
    "INSERT INTO billing_plans (id, name, price_monthly, quotas, overage) "
    "VALUES (?, ?, ?, ?, ?)"
)
_SELECT_PLAN_SQL: str = "SELECT * FROM billing_plans WHERE id = ?"
_LIST_PLANS_SQL: str = "SELECT * FROM billing_plans ORDER BY id"

_DEACTIVATE_SUBS_SQL: str = (
    "UPDATE billing_subscriptions SET status = 'cancelled' "
    "WHERE tenant_id = ? AND status = 'active'"
)
_INSERT_SUB_SQL: str = (
    "INSERT INTO billing_subscriptions "
    "(id, tenant_id, plan_id, status, period_start, period_end) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
_SELECT_SUB_BY_ID_SQL: str = "SELECT * FROM billing_subscriptions WHERE id = ?"
_SELECT_ACTIVE_SUB_SQL: str = (
    "SELECT * FROM billing_subscriptions "
    "WHERE tenant_id = ? AND status = 'active' "
    "AND period_start <= ? AND period_end >= ? "
    "ORDER BY period_end DESC LIMIT 1"
)
_LIST_SUBS_SQL: str = (
    "SELECT * FROM billing_subscriptions ORDER BY tenant_id, period_start, id"
)

_INSERT_USAGE_SQL: str = (
    "INSERT INTO usage_ledger "
    "(tenant_id, event_id, metric, units, unit_label, happened_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)
_LIST_USAGE_TENANT_SQL: str = (
    "SELECT * FROM usage_ledger "
    "WHERE tenant_id = ? AND happened_at >= ? AND happened_at < ? "
    "ORDER BY happened_at, id"
)
_LIST_USAGE_ALL_SQL: str = (
    "SELECT * FROM usage_ledger "
    "WHERE happened_at >= ? AND happened_at < ? ORDER BY happened_at, id"
)
_USAGE_TOTAL_SQL: str = (
    "SELECT COALESCE(SUM(units), 0) AS total FROM usage_ledger "
    "WHERE tenant_id = ? AND metric = ? AND happened_at >= ? AND happened_at < ?"
)

_INSERT_INVOICE_SQL: str = (
    "INSERT INTO invoices "
    "(id, tenant_id, period, line_items, total, currency, status) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)
_SELECT_INVOICE_SQL: str = (
    "SELECT * FROM invoices WHERE tenant_id = ? AND period = ?"
)
_LIST_INVOICES_SQL: str = (
    "SELECT * FROM invoices WHERE tenant_id = ? ORDER BY period DESC"
)


def _to_mysql(sql: str) -> str:
    """Translate the shared '?' placeholder SQL to PyMySQL's '%s'."""
    return sql.replace("?", "%s")


# ── Row mappers ──────────────────────────────────────────────────────────────


def _row_to_plan(row: Any) -> Plan:
    return Plan(
        id=cast(str, row["id"]),
        name=cast(str, row["name"]),
        price_monthly=float(row["price_monthly"]),
        quotas=_parse_metric_map(row["quotas"]),
        overage=_parse_metric_map(row["overage"]),
    )


def _row_to_subscription(row: Any) -> Subscription:
    return Subscription(
        id=cast(str, row["id"]),
        tenant_id=cast(str, row["tenant_id"]),
        plan_id=cast(str, row["plan_id"]),
        status=cast(str, row["status"]),
        period_start=float(row["period_start"]),
        period_end=float(row["period_end"]),
    )


def _row_to_usage(row: Any) -> UsageRecord:
    return UsageRecord(
        id=int(row["id"]),
        tenant_id=cast(str, row["tenant_id"]),
        event_id=cast(str, row["event_id"]),
        metric=cast(str, row["metric"]),
        units=float(row["units"]),
        unit_label=cast(str, row["unit_label"]),
        happened_at=float(row["happened_at"]),
    )


def _row_to_invoice(row: Any) -> Invoice:
    return Invoice(
        id=cast(str, row["id"]),
        tenant_id=cast(str, row["tenant_id"]),
        period=cast(str, row["period"]),
        line_items=_parse_line_items(row["line_items"]),
        total=float(row["total"]),
        currency=cast(str, row["currency"]),
        status=cast(str, row["status"]),
    )


def _parse_mysql_url(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("mysql", "mysql+pymysql"):
        raise ValueError(f"expected a mysql:// URL, got scheme {parsed.scheme!r}")
    if parsed.hostname is None:
        raise ValueError("MySQL URL must include a host")
    database = (parsed.path or "/").lstrip("/")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username is not None else "",
        "password": unquote(parsed.password) if parsed.password is not None else "",
        "database": database or "specproof",
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


# ── In-memory backend ────────────────────────────────────────────────────────


class InMemoryBillingStore:
    """Thread-safe in-memory backend — development and tests."""

    def __init__(self, *, now_fn: Callable[[], float] | None = None) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.RLock()
        self._plans: dict[str, Plan] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._usage: dict[int, UsageRecord] = {}
        self._event_ids: set[str] = set()
        self._usage_seq = 0
        self._invoices: dict[tuple[str, str], Invoice] = {}

    def ensure_schema(self) -> None:
        """No-op: the in-memory dicts need no schema."""

    def close(self) -> None:
        """No-op: nothing to release."""

    def create_plan(
        self,
        plan_id: str,
        name: str,
        price_monthly: float,
        quotas: dict[str, float],
        overage: dict[str, float],
    ) -> Plan:
        plan = Plan(
            id=plan_id, name=name, price_monthly=float(price_monthly),
            quotas=dict(quotas), overage=dict(overage),
        )
        with self._lock:
            if plan_id in self._plans:
                raise DuplicatePlanError(f"plan {plan_id!r} already exists")
            self._plans[plan_id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        with self._lock:
            return self._plans.get(plan_id)

    def list_plans(self) -> list[Plan]:
        with self._lock:
            return sorted(self._plans.values(), key=lambda p: p.id)

    def upsert_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        status: str,
        period_start: float,
        period_end: float,
    ) -> Subscription:
        import uuid

        if self.get_plan(plan_id) is None:
            raise PlanNotFoundError(f"plan {plan_id!r} does not exist")
        status = _validate_subscription_status(status)
        sub = Subscription(
            id=str(uuid.uuid4()), tenant_id=tenant_id, plan_id=plan_id,
            status=status, period_start=float(period_start),
            period_end=float(period_end),
        )
        with self._lock:
            for existing in self._subscriptions.values():
                if existing.tenant_id == tenant_id and existing.status == "active":
                    self._subscriptions[existing.id] = Subscription(
                        id=existing.id, tenant_id=existing.tenant_id,
                        plan_id=existing.plan_id, status="cancelled",
                        period_start=existing.period_start,
                        period_end=existing.period_end,
                    )
            self._subscriptions[sub.id] = sub
        return sub

    def get_subscription(self, tenant_id: str) -> Subscription | None:
        now = self._now_fn()
        with self._lock:
            active = [
                s for s in self._subscriptions.values()
                if s.tenant_id == tenant_id and s.status == "active"
                and s.period_start <= now <= s.period_end
            ]
        if not active:
            return None
        return max(active, key=lambda s: s.period_end)

    def list_subscriptions(self) -> list[Subscription]:
        with self._lock:
            return sorted(
                self._subscriptions.values(),
                key=lambda s: (s.tenant_id, s.period_start, s.id),
            )

    def record_usage(
        self,
        event_id: str,
        tenant_id: str,
        metric: str,
        units: float,
        unit_label: str = "",
        happened_at: float | None = None,
    ) -> bool:
        metric = _validate_metric(metric)
        units = float(units)
        if units < 0:
            raise ValueError(f"usage units must be >= 0, got {units:g}")
        with self._lock:
            if event_id in self._event_ids:
                return False
            self._event_ids.add(event_id)
            self._usage_seq += 1
            self._usage[self._usage_seq] = UsageRecord(
                id=self._usage_seq, tenant_id=tenant_id, event_id=event_id,
                metric=metric, units=units, unit_label=unit_label,
                happened_at=self._now_fn() if happened_at is None else float(happened_at),
            )
        return True

    def list_usage(
        self, tenant_id: str | None, from_ts: float, to_ts: float,
    ) -> list[UsageRecord]:
        with self._lock:
            rows = [
                r for r in self._usage.values()
                if (tenant_id is None or r.tenant_id == tenant_id)
                and from_ts <= r.happened_at < to_ts
            ]
        return sorted(rows, key=lambda r: (r.happened_at, r.id))

    def usage_total(
        self, tenant_id: str, metric: str, from_ts: float, to_ts: float,
    ) -> float:
        with self._lock:
            return sum(
                r.units for r in self._usage.values()
                if r.tenant_id == tenant_id and r.metric == metric
                and from_ts <= r.happened_at < to_ts
            )

    def create_invoice(
        self,
        tenant_id: str,
        period: str,
        line_items: list[dict[str, Any]],
        total: float,
        currency: str,
        status: str,
    ) -> Invoice:
        import uuid

        status = _validate_invoice_status(status)
        invoice = Invoice(
            id=str(uuid.uuid4()), tenant_id=tenant_id, period=period,
            line_items=[dict(item) for item in line_items], total=float(total),
            currency=currency, status=status,
        )
        with self._lock:
            key = (tenant_id, period)
            if key in self._invoices:
                raise InvoiceExistsError(
                    f"invoice for tenant {tenant_id!r} period {period!r} exists"
                )
            self._invoices[key] = invoice
        return invoice

    def get_invoice(self, tenant_id: str, period: str) -> Invoice | None:
        with self._lock:
            return self._invoices.get((tenant_id, period))

    def list_invoices(self, tenant_id: str) -> list[Invoice]:
        with self._lock:
            rows = [
                i for (_tenant, _period), i in self._invoices.items()
                if _tenant == tenant_id
            ]
        return sorted(rows, key=lambda i: i.period, reverse=True)


# ── SQLite backend ───────────────────────────────────────────────────────────


class SqliteBillingStore:
    """File-based SQLite backend (tests and dev; no Docker required).

    One connection per store instance, serialized by a lock;
    check_same_thread=False plus the lock keeps concurrent threads safe.
    The schema is created in __init__.
    """

    def __init__(
        self, path: str | Path, *, now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._now_fn = now_fn if now_fn is not None else time.time
        self._lock = threading.Lock()
        # isolation_level=None (autocommit): every statement commits
        # immediately, so concurrent store instances on the same file
        # (the metering writer and the query store) always see each
        # other's rows — the API process and the worker may each hold
        # their own connection.
        self._conn = sqlite3.connect(
            str(path), check_same_thread=False, isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA_SQLITE)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create_plan(
        self,
        plan_id: str,
        name: str,
        price_monthly: float,
        quotas: dict[str, float],
        overage: dict[str, float],
    ) -> Plan:
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    _INSERT_PLAN_SQL,
                    (plan_id, name, float(price_monthly),
                     json.dumps(quotas), json.dumps(overage)),
                )
            except sqlite3.IntegrityError as exc:
                raise DuplicatePlanError(
                    f"plan {plan_id!r} already exists"
                ) from exc
        plan = self.get_plan(plan_id)
        if plan is None:
            raise BillingStoreError("plan insert did not persist")
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        with self._lock:
            row = self._conn.execute(_SELECT_PLAN_SQL, (plan_id,)).fetchone()
        return None if row is None else _row_to_plan(row)

    def list_plans(self) -> list[Plan]:
        with self._lock:
            rows = self._conn.execute(_LIST_PLANS_SQL).fetchall()
        return [_row_to_plan(row) for row in rows]

    def upsert_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        status: str,
        period_start: float,
        period_end: float,
    ) -> Subscription:
        import uuid

        if self.get_plan(plan_id) is None:
            raise PlanNotFoundError(f"plan {plan_id!r} does not exist")
        status = _validate_subscription_status(status)
        sub_id = str(uuid.uuid4())
        with self._lock, self._conn:
            self._conn.execute(_DEACTIVATE_SUBS_SQL, (tenant_id,))
            self._conn.execute(
                _INSERT_SUB_SQL,
                (sub_id, tenant_id, plan_id, status,
                 float(period_start), float(period_end)),
            )
            row = self._conn.execute(_SELECT_SUB_BY_ID_SQL, (sub_id,)).fetchone()
        if row is None:
            raise BillingStoreError("subscription insert did not persist")
        return _row_to_subscription(row)

    def get_subscription(self, tenant_id: str) -> Subscription | None:
        now = self._now_fn()
        with self._lock:
            row = self._conn.execute(
                _SELECT_ACTIVE_SUB_SQL, (tenant_id, now, now),
            ).fetchone()
        return None if row is None else _row_to_subscription(row)

    def list_subscriptions(self) -> list[Subscription]:
        with self._lock:
            rows = self._conn.execute(_LIST_SUBS_SQL).fetchall()
        return [_row_to_subscription(row) for row in rows]

    def record_usage(
        self,
        event_id: str,
        tenant_id: str,
        metric: str,
        units: float,
        unit_label: str = "",
        happened_at: float | None = None,
    ) -> bool:
        metric = _validate_metric(metric)
        units = float(units)
        if units < 0:
            raise ValueError(f"usage units must be >= 0, got {units:g}")
        happened = self._now_fn() if happened_at is None else float(happened_at)
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    _INSERT_USAGE_SQL,
                    (tenant_id, event_id, metric, units, unit_label, happened),
                )
            except sqlite3.IntegrityError as exc:
                if "usage_ledger.event_id" in str(exc):
                    return False
                raise BillingStoreError(f"usage insert rejected: {exc}") from exc
        return True

    def list_usage(
        self, tenant_id: str | None, from_ts: float, to_ts: float,
    ) -> list[UsageRecord]:
        with self._lock:
            if tenant_id is None:
                rows = self._conn.execute(
                    _LIST_USAGE_ALL_SQL, (from_ts, to_ts),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    _LIST_USAGE_TENANT_SQL, (tenant_id, from_ts, to_ts),
                ).fetchall()
        return [_row_to_usage(row) for row in rows]

    def usage_total(
        self, tenant_id: str, metric: str, from_ts: float, to_ts: float,
    ) -> float:
        with self._lock:
            row = self._conn.execute(
                _USAGE_TOTAL_SQL, (tenant_id, metric, from_ts, to_ts),
            ).fetchone()
        return 0.0 if row is None else float(row["total"])

    def create_invoice(
        self,
        tenant_id: str,
        period: str,
        line_items: list[dict[str, Any]],
        total: float,
        currency: str,
        status: str,
    ) -> Invoice:
        import uuid

        status = _validate_invoice_status(status)
        invoice_id = str(uuid.uuid4())
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    _INSERT_INVOICE_SQL,
                    (invoice_id, tenant_id, period, json.dumps(line_items),
                     float(total), currency, status),
                )
            except sqlite3.IntegrityError as exc:
                raise InvoiceExistsError(
                    f"invoice for tenant {tenant_id!r} period {period!r} exists"
                ) from exc
        invoice = self.get_invoice(tenant_id, period)
        if invoice is None:
            raise BillingStoreError("invoice insert did not persist")
        return invoice

    def get_invoice(self, tenant_id: str, period: str) -> Invoice | None:
        with self._lock:
            row = self._conn.execute(
                _SELECT_INVOICE_SQL, (tenant_id, period),
            ).fetchone()
        return None if row is None else _row_to_invoice(row)

    def list_invoices(self, tenant_id: str) -> list[Invoice]:
        with self._lock:
            rows = self._conn.execute(
                _LIST_INVOICES_SQL, (tenant_id,),
            ).fetchall()
        return [_row_to_invoice(row) for row in rows]


# ── MySQL backend ────────────────────────────────────────────────────────────


class MySqlBillingStore:
    """Production MySQL backend (PyMySQL + DictCursor).

    One connection per operation via the connection() context manager,
    which commits on success and rolls back on error; every statement uses
    a single cursor execute-then-fetch (CLAUDE.md MySQL discipline).
    """

    def __init__(
        self, url: str | None = None, *, now_fn: Callable[[], float] | None = None,
    ) -> None:
        resolved = url or os.getenv("MYSQL_URL")
        if not resolved:
            raise ValueError(
                "MySqlBillingStore needs a mysql:// URL (argument or MYSQL_URL)"
            )
        self._connect_kwargs = _parse_mysql_url(resolved)
        self._now_fn = now_fn if now_fn is not None else time.time

    def _connect(self) -> pymysql.Connection:
        return pymysql.connect(**self._connect_kwargs)

    @contextmanager
    def connection(self) -> Iterator[pymysql.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """No-op: each operation opens and closes its own connection."""

    def ensure_schema(self) -> None:
        with self.connection() as conn:
            conn.cursor().execute(_SCHEMA_MYSQL)

    def create_plan(
        self,
        plan_id: str,
        name: str,
        price_monthly: float,
        quotas: dict[str, float],
        overage: dict[str, float],
    ) -> Plan:
        with self.connection() as conn:
            try:
                conn.cursor().execute(
                    _to_mysql(_INSERT_PLAN_SQL),
                    (plan_id, name, float(price_monthly),
                     json.dumps(quotas), json.dumps(overage)),
                )
            except pymysql.err.IntegrityError as exc:
                raise DuplicatePlanError(
                    f"plan {plan_id!r} already exists"
                ) from exc
        plan = self.get_plan(plan_id)
        if plan is None:
            raise BillingStoreError("plan insert did not persist")
        return plan

    def get_plan(self, plan_id: str) -> Plan | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_PLAN_SQL), (plan_id,))
            row = cur.fetchone()
        return None if row is None else _row_to_plan(cast(dict[str, Any], row))

    def list_plans(self) -> list[Plan]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_LIST_PLANS_SQL))
            rows = cur.fetchall()
        return [_row_to_plan(cast(dict[str, Any], row)) for row in rows]

    def upsert_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        status: str,
        period_start: float,
        period_end: float,
    ) -> Subscription:
        import uuid

        if self.get_plan(plan_id) is None:
            raise PlanNotFoundError(f"plan {plan_id!r} does not exist")
        status = _validate_subscription_status(status)
        sub_id = str(uuid.uuid4())
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_DEACTIVATE_SUBS_SQL), (tenant_id,))
            cur.execute(
                _to_mysql(_INSERT_SUB_SQL),
                (sub_id, tenant_id, plan_id, status,
                 float(period_start), float(period_end)),
            )
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_SUB_BY_ID_SQL), (sub_id,))
            row = cur.fetchone()
        if row is None:
            raise BillingStoreError("subscription insert did not persist")
        return _row_to_subscription(cast(dict[str, Any], row))

    def get_subscription(self, tenant_id: str) -> Subscription | None:
        now = self._now_fn()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_ACTIVE_SUB_SQL), (tenant_id, now, now))
            row = cur.fetchone()
        return None if row is None else _row_to_subscription(cast(dict[str, Any], row))

    def list_subscriptions(self) -> list[Subscription]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_LIST_SUBS_SQL))
            rows = cur.fetchall()
        return [_row_to_subscription(cast(dict[str, Any], row)) for row in rows]

    def record_usage(
        self,
        event_id: str,
        tenant_id: str,
        metric: str,
        units: float,
        unit_label: str = "",
        happened_at: float | None = None,
    ) -> bool:
        metric = _validate_metric(metric)
        units = float(units)
        if units < 0:
            raise ValueError(f"usage units must be >= 0, got {units:g}")
        happened = self._now_fn() if happened_at is None else float(happened_at)
        with self.connection() as conn:
            try:
                conn.cursor().execute(
                    _to_mysql(_INSERT_USAGE_SQL),
                    (tenant_id, event_id, metric, units, unit_label, happened),
                )
            except pymysql.err.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    return False
                raise BillingStoreError(f"usage insert rejected: {exc}") from exc
        return True

    def list_usage(
        self, tenant_id: str | None, from_ts: float, to_ts: float,
    ) -> list[UsageRecord]:
        with self.connection() as conn:
            cur = conn.cursor()
            if tenant_id is None:
                cur.execute(_to_mysql(_LIST_USAGE_ALL_SQL), (from_ts, to_ts))
            else:
                cur.execute(
                    _to_mysql(_LIST_USAGE_TENANT_SQL),
                    (tenant_id, from_ts, to_ts),
                )
            rows = cur.fetchall()
        return [_row_to_usage(cast(dict[str, Any], row)) for row in rows]

    def usage_total(
        self, tenant_id: str, metric: str, from_ts: float, to_ts: float,
    ) -> float:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                _to_mysql(_USAGE_TOTAL_SQL), (tenant_id, metric, from_ts, to_ts),
            )
            row = cur.fetchone()
        if row is None:
            return 0.0
        return float(cast(dict[str, Any], row).get("total") or 0.0)

    def create_invoice(
        self,
        tenant_id: str,
        period: str,
        line_items: list[dict[str, Any]],
        total: float,
        currency: str,
        status: str,
    ) -> Invoice:
        import uuid

        status = _validate_invoice_status(status)
        invoice_id = str(uuid.uuid4())
        with self.connection() as conn:
            try:
                conn.cursor().execute(
                    _to_mysql(_INSERT_INVOICE_SQL),
                    (invoice_id, tenant_id, period, json.dumps(line_items),
                     float(total), currency, status),
                )
            except pymysql.err.IntegrityError as exc:
                if exc.args and exc.args[0] == 1062:
                    raise InvoiceExistsError(
                        f"invoice for tenant {tenant_id!r} period {period!r} exists"
                    ) from exc
                raise
        invoice = self.get_invoice(tenant_id, period)
        if invoice is None:
            raise BillingStoreError("invoice insert did not persist")
        return invoice

    def get_invoice(self, tenant_id: str, period: str) -> Invoice | None:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_SELECT_INVOICE_SQL), (tenant_id, period))
            row = cur.fetchone()
        return None if row is None else _row_to_invoice(cast(dict[str, Any], row))

    def list_invoices(self, tenant_id: str) -> list[Invoice]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(_to_mysql(_LIST_INVOICES_SQL), (tenant_id,))
            rows = cur.fetchall()
        return [_row_to_invoice(cast(dict[str, Any], row)) for row in rows]


# ── Store factory (SPECPROOF_BILLING_URL, agent_jobs convention) ─────────────


def build_billing_store(url_spec: str) -> BillingStore:
    """Build a backend from a URL spec; fails closed on an unknown scheme.

    * ''            -> InMemoryBillingStore (dev/tests);
    * 'sqlite:<p>'  -> SqliteBillingStore (file path, or ':memory:');
    * 'mysql://...' -> MySqlBillingStore (production).
    """
    if url_spec == "":
        return InMemoryBillingStore()
    if url_spec.startswith("sqlite:"):
        path = url_spec[len("sqlite:"):]
        return SqliteBillingStore(path)
    if url_spec.startswith("mysql://") or url_spec.startswith("mysql+pymysql://"):
        return MySqlBillingStore(url_spec)
    raise ValueError(
        "SPECPROOF_BILLING_URL must be '' (in-memory), 'sqlite:<path>' or "
        f"'mysql://...'; got {url_spec!r}"
    )


def seed_default_plans(store: BillingStore) -> None:
    """Create the free/pro plans when they are missing (idempotent)."""
    for spec in DEFAULT_PLANS:
        plan_id = str(spec["id"])
        if store.get_plan(plan_id) is None:
            store.create_plan(
                plan_id,
                str(spec["name"]),
                float(spec["price_monthly"]),
                {str(k): float(v) for k, v in spec["quotas"].items()},
                {str(k): float(v) for k, v in spec["overage"].items()},
            )


# ── Billing writer (metering facade + quota enforcement) ─────────────────────


class BillingWriter:
    """The configured metering facade the hooks project events through.

    Unconfigured deployments have no writer at all (get_billing_writer()
    returns None) so every hook is a byte-identical no-op. Notifications
    are an in-process list plus a warning log — a production sink (webhook
    / email / ticket) is deferred to the UI phase with the rest of the
    billing surface.
    """

    def __init__(
        self, store: BillingStore, *, now_fn: Callable[[], float] | None = None,
    ) -> None:
        self.store = store
        self._now_fn = now_fn if now_fn is not None else time.time
        self.notifications: list[dict[str, Any]] = []
        self._soft_limit_notified: set[tuple[str, str, str]] = set()

    def record_event(
        self,
        *,
        event_id: str,
        tenant_id: str,
        metric: str,
        units: float,
        unit_label: str = "",
        happened_at: float | None = None,
    ) -> bool:
        """Project one event onto the ledger (idempotent by event_id)."""
        if not tenant_id or not event_id:
            return False
        _validate_metric(metric)
        if float(units) <= 0:
            return False
        return self.store.record_usage(
            event_id, tenant_id, metric, float(units), unit_label, happened_at,
        )

    def meter_verify_job_start(
        self, tenant_id: str, job_id: str, happened_at: float | None = None,
    ) -> bool:
        """Verify pipeline start: one job_verify unit per job (§2)."""
        return self.record_event(
            event_id=f"verify:{tenant_id}:{job_id}:start",
            tenant_id=tenant_id, metric="job_verify", units=1.0,
            unit_label="job", happened_at=happened_at,
        )

    def meter_verify_job_end(
        self,
        tenant_id: str,
        job_id: str,
        findings_count: int,
        verdict: str = "",
        happened_at: float | None = None,
    ) -> int:
        """Verify pipeline end: gate_findings units = confirmed findings."""
        if findings_count <= 0:
            return 0
        created = self.record_event(
            event_id=f"verify:{tenant_id}:{job_id}:findings",
            tenant_id=tenant_id, metric="gate_findings",
            units=float(findings_count), unit_label=verdict or "finding",
            happened_at=happened_at,
        )
        return 1 if created else 0

    def meter_craft_job_terminal(
        self, tenant_id: str, job_id: str, status: str,
        happened_at: float | None = None,
    ) -> bool:
        """SpecCraft terminal state: one job_craft unit per job (§2)."""
        return self.record_event(
            event_id=f"craft:{tenant_id}:{job_id}:terminal",
            tenant_id=tenant_id, metric="job_craft", units=1.0,
            unit_label=status or "craft", happened_at=happened_at,
        )

    def record_llm_usage(
        self, entry: dict[str, Any], tenant_id: str | None = None,
    ) -> list[bool]:
        """Project one TokenBudget usage record onto the four token classes.

        The design names exactly four classes: input, output, KV-cache
        hits and reasoning (cache misses are deliberately not a ledger
        metric). The tenant comes from the request-scoped context when the
        call runs inside the multi-tenant API process; standalone CLI runs
        have no tenant and emit nothing.
        """
        tenant = tenant_id or self._tenant_from_scope()
        if not tenant:
            return []
        label = str(entry.get("label") or "llm")
        timestamp = str(entry.get("timestamp") or "")
        used_after = entry.get("used_after")
        created: list[bool] = []
        classes = (
            ("llm_tokens_in", "prompt_tokens"),
            ("llm_tokens_out", "completion_tokens"),
            ("llm_cache_hit_tokens", "prompt_cache_hit_tokens"),
            ("llm_reasoning_tokens", "reasoning_tokens"),
        )
        for metric, key in classes:
            units = _as_float(entry.get(key))
            if units <= 0:
                continue
            event_id = (
                f"llm:{tenant}:{label}:{timestamp}:{used_after}:{metric}"
            )
            created.append(self.record_event(
                event_id=event_id, tenant_id=tenant, metric=metric,
                units=units, unit_label="token",
            ))
        return created

    @staticmethod
    def _tenant_from_scope() -> str:
        scope = current_scope()
        return scope.tenant_id if scope is not None else ""

    def check_quota(
        self, tenant_id: str, metric: str, planned_units: float = 1.0,
    ) -> QuotaDecision:
        """Pre-flight the planned usage against the subscription quota (§3).

        Hard-stop plans (no overage price for the metric — the default)
        raise QuotaExceededError; soft-overage plans allow the overrun and
        report the excess units for the invoice. Crossing 80% of the quota
        emits one soft-limit notification per (tenant, metric, period).
        A tenant without an active subscription is not quota-enforced
        (rollout-safe fail-open).
        """
        _validate_metric(metric)
        planned = float(planned_units)
        unenforced = QuotaDecision(
            allowed=True, enforced=False, quota=0.0, used=0.0,
            planned=planned, overage_units=0.0, ratio=0.0,
        )
        subscription = self.store.get_subscription(tenant_id)
        if subscription is None:
            return unenforced
        plan = self.store.get_plan(subscription.plan_id)
        if plan is None:
            return unenforced
        quota = float(plan.quotas.get(QUOTA_KEY_BY_METRIC.get(metric, metric), 0.0))
        if quota <= 0:
            return unenforced
        now = self._now_fn()
        dt = datetime.fromtimestamp(now, tz=UTC)
        start, end = _month_bounds(dt.year, dt.month)
        used = self.store.usage_total(tenant_id, metric, start, end)
        ratio = (used + planned) / quota
        overage_units = 0.0
        if ratio >= 1.0:
            if metric in plan.overage:
                overage_units = used + planned - quota
            else:
                raise QuotaExceededError(
                    metric=metric, quota=quota, used=used,
                    planned=planned, tenant_id=tenant_id,
                )
        if ratio >= 0.8:
            self._notify_soft_limit(
                tenant_id, metric, ratio, quota, used, planned,
            )
        return QuotaDecision(
            allowed=True, enforced=True, quota=quota, used=used,
            planned=planned, overage_units=overage_units, ratio=ratio,
        )

    def _notify_soft_limit(
        self,
        tenant_id: str,
        metric: str,
        ratio: float,
        quota: float,
        used: float,
        planned: float,
    ) -> None:
        period = current_period_key(self._now_fn())
        key = (tenant_id, metric, period)
        if key in self._soft_limit_notified:
            return
        self._soft_limit_notified.add(key)
        event = {
            "type": "soft_limit",
            "tenant_id": tenant_id,
            "metric": metric,
            "ratio": round(ratio, 4),
            "quota": quota,
            "used": used,
            "planned": planned,
            "period": period,
            "happened_at": self._now_fn(),
        }
        self.notifications.append(event)
        logger.warning("billing soft limit reached: %s", event)


def ensure_invoice(
    store: BillingStore,
    tenant_id: str,
    period: str | None = None,
    *,
    now_fn: Callable[[], float] | None = None,
) -> Invoice:
    """Generate (or return) the monthly draft invoice for a period (§4).

    The monthly cron calls this at period start; the invoices endpoint
    calls it on demand. line_items = plan base + per-metric usage with
    quota/overage split; the four LLM token classes aggregate into one
    llm_tokens line against the plan's llm_tokens quota. total is derived
    from the line items (Σ amount, rounded to cents) so the reconciliation
    invariant total == Σ line_items always holds.
    """
    if period is not None:
        effective = period
    elif now_fn is not None:
        effective = current_period_key(now_fn())
    else:
        effective = current_period_key()
    existing = store.get_invoice(tenant_id, effective)
    if existing is not None:
        return existing
    start, end = period_bounds(effective)
    subscription = store.get_subscription(tenant_id)
    plan = store.get_plan(subscription.plan_id) if subscription is not None else None
    base_price = plan.price_monthly if plan is not None else 0.0
    line_items: list[dict[str, Any]] = [
        {
            "metric": "plan", "units": 1, "unit_price": base_price,
            "amount": round(base_price, 4),
        },
    ]
    raw: dict[str, float] = {}
    for row in store.list_usage(tenant_id, start, end):
        raw[row.metric] = raw.get(row.metric, 0.0) + row.units
    totals: dict[str, float] = {}
    llm_total = 0.0
    for metric, units in raw.items():
        if metric in LLM_TOKEN_METRICS:
            llm_total += units
        else:
            totals[metric] = units
    if llm_total > 0:
        totals["llm_tokens"] = llm_total
    quotas = plan.quotas if plan is not None else {}
    overage = plan.overage if plan is not None else {}
    for metric in sorted(totals):
        units = totals[metric]
        quota = float(quotas.get(QUOTA_KEY_BY_METRIC.get(metric, metric), 0.0))
        over = max(0.0, units - quota) if quota > 0 else 0.0
        price = float(overage.get(metric, 0.0))
        line_items.append({
            "metric": metric, "units": units, "quota": quota,
            "overage_units": over, "unit_price": price,
            "amount": round(over * price, 4),
        })
    total = round(sum(float(item["amount"]) for item in line_items), 2)
    return store.create_invoice(
        tenant_id, effective, line_items, total, DEFAULT_CURRENCY, "draft",
    )


# ── Writer registry + hook API (opt-in; default off) ─────────────────────────

_writer: BillingWriter | None = None
_writer_url: str = ""


def billing_url() -> str:
    """The configured billing URL ('' = billing disabled, the default)."""
    return os.getenv("SPECPROOF_BILLING_URL", "").strip()


def get_billing_writer() -> BillingWriter | None:
    """The cached writer for the current configuration, or None (off)."""
    global _writer, _writer_url
    url = billing_url()
    if _writer is None or _writer_url != url:
        _writer_url = url
        _writer = None
        if url:
            store = build_billing_store(url)
            seed_default_plans(store)
            _writer = BillingWriter(store)
        _sync_usage_listener()
    return _writer


def reset_billing_writer() -> None:
    """Drop the cached writer and unregister the LLM usage listener."""
    global _writer, _writer_url
    _writer = None
    _writer_url = ""
    _sync_usage_listener()


def _sync_usage_listener() -> None:
    from providers.budget import clear_usage_listener, set_usage_listener

    if _writer is None:
        clear_usage_listener()
    else:
        set_usage_listener(_forward_llm_usage)


def _forward_llm_usage(entry: dict[str, Any]) -> None:
    writer = _writer
    if writer is not None:
        writer.record_llm_usage(entry)


def meter_verify_job_start(
    tenant_id: str, job_id: str, happened_at: float | None = None,
) -> bool:
    """Verify pipeline start hook — no-op unless billing is configured."""
    writer = get_billing_writer()
    if writer is None or not tenant_id:
        return False
    try:
        return writer.meter_verify_job_start(tenant_id, job_id, happened_at)
    except Exception:  # noqa: BLE001 — metering must never break the pipeline
        logger.warning("billing meter event dropped (verify start)", exc_info=True)
        return False


def meter_verify_job_end(
    tenant_id: str,
    job_id: str,
    findings_count: int,
    verdict: str = "",
    happened_at: float | None = None,
) -> int:
    """Verify pipeline end hook — no-op unless billing is configured."""
    writer = get_billing_writer()
    if writer is None or not tenant_id or findings_count <= 0:
        return 0
    try:
        return writer.meter_verify_job_end(
            tenant_id, job_id, findings_count, verdict, happened_at,
        )
    except Exception:  # noqa: BLE001 — metering must never break the pipeline
        logger.warning("billing meter event dropped (verify end)", exc_info=True)
        return 0


def meter_craft_job_terminal(
    tenant_id: str, job_id: str, status: str, happened_at: float | None = None,
) -> bool:
    """SpecCraft terminal-state hook — no-op unless billing is configured."""
    writer = get_billing_writer()
    if writer is None or not tenant_id:
        return False
    try:
        return writer.meter_craft_job_terminal(tenant_id, job_id, status, happened_at)
    except Exception:  # noqa: BLE001 — metering must never break the pipeline
        logger.warning("billing meter event dropped (craft terminal)", exc_info=True)
        return False
