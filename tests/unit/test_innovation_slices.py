"""Unit tests for the innovation first slices (计划书 §19.4-19.6).

Covers the pure kernels only: impact ordering for the digital twin, queue
policy functions for the repair queue, and the sanitization round-trip for
rejection learning. Every fixture is built in memory — no network, no
Docker, no external services.

Security note: key-shaped fixture material is built at runtime by string
concatenation so this file (scanned by tests/security/test_no_key_leak.py)
never contains a committed key literal.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from experiments.innovation.digital_twin import (
    RepositoryTwin,
    build_from_symbol_index,
    impact_estimate,
)
from experiments.innovation.rejection_learning import (
    RejectionRecord,
    build_eval_case,
    build_eval_cases,
    extract_rules,
    sanitize_record,
)
from experiments.innovation.repair_queue import (
    RepairTicket,
    Severity,
    TicketSource,
    TicketStatus,
    apply_rate_limits,
    is_auto_eligible,
    plan_dispatch,
    priority_order,
)
from retrieval.symbols import RepoIndex, SymbolIndexer

# ---------------------------------------------------------------------------
# digital twin fixtures
# ---------------------------------------------------------------------------

_ORDERS_SERVICE = '''\
class OrderService:
    def place_order(self, amount: int) -> None:
        charge(amount)
        db_save("orders", amount)

def create_order(amount: int) -> None:
    db_save("orders", amount)
'''

_PAYMENTS_GATEWAY = '''\
class PaymentLedger:
    entries: list[int] = []

    def add(self, entry: int) -> None:
        self.entries.append(entry)

def charge(amount: int) -> None:
    db_save("payments", amount)
'''

_DB_REPOSITORY = '''\
def db_save(table: str, amount: int) -> None:
    _ledger.append((table, amount))

_ledger: list[tuple[str, int]] = []
'''

_MIGRATION = '''\
def upgrade() -> None:
    db_save("schema", 0)
'''

_WEB_API = '''\
from src.orders.service import create_order

def list_orders() -> None:
    create_order(10)
'''


def _build_index(codeowners: str | None = None) -> RepoIndex:
    files: dict[str, str] = {
        "src/orders/service.py": _ORDERS_SERVICE,
        "src/payments/gateway.py": _PAYMENTS_GATEWAY,
        "src/db/repository.py": _DB_REPOSITORY,
        "src/migrations/0001_schema.py": _MIGRATION,
        "web/api.py": _WEB_API,
    }
    if codeowners is not None:
        files["CODEOWNERS"] = codeowners
    return SymbolIndexer.index_files(files)


class TestDigitalTwin:
    """§19.4: twin construction and impact estimation by graph distance."""

    def test_modules_and_dependency_edges(self) -> None:
        twin = build_from_symbol_index(_build_index())
        assert set(twin.modules) == {
            "src/db",
            "src/migrations",
            "src/orders",
            "src/payments",
            "web",
        }
        expected_edges = {
            ("src/orders", "src/payments", "charge"),
            ("src/orders", "src/db", "db_save"),
            ("src/payments", "src/db", "db_save"),
            ("src/migrations", "src/db", "db_save"),
            ("web", "src/orders", "create_order"),
        }
        got_edges = {(edge.source, edge.target, edge.via) for edge in twin.dependencies}
        assert got_edges == expected_edges

    def test_migrations_and_api_surface(self) -> None:
        twin = build_from_symbol_index(_build_index())
        assert [(m.module, m.path) for m in twin.migrations] == [
            ("src/migrations", "src/migrations/0001_schema.py"),
        ]
        api_surface = {(entry.module, entry.symbol) for entry in twin.apis}
        assert api_surface == {
            ("src/db", "db_save"),
            ("src/migrations", "upgrade"),
            ("src/orders", "create_order"),
            ("src/payments", "charge"),
            ("web", "list_orders"),
        }

    def test_owners_from_codeowners_last_match_wins(self) -> None:
        twin = build_from_symbol_index(
            _build_index("* @platform\nsrc/orders @orders-team\n")
        )
        assert twin.owners["src/orders"] == "orders-team"
        assert twin.owners["src/payments"] == "platform"

    def test_owners_derived_fallback(self) -> None:
        twin = build_from_symbol_index(_build_index())
        assert twin.owners["src/orders"] == "orders"
        assert twin.owners["web"] == "web"

    def test_explicit_owners_override(self) -> None:
        twin = build_from_symbol_index(
            _build_index(), owners={"src/orders": "checkout-squad"},
        )
        assert twin.owners["src/orders"] == "checkout-squad"
        assert twin.owners["src/payments"] == "payments"

    def test_risk_scores_bounded_and_migration_weighted(self) -> None:
        twin = build_from_symbol_index(_build_index())
        for score in twin.risk_scores.values():
            assert 0.0 <= score <= 1.0
        assert twin.risk_scores["src/db"] == pytest.approx(0.075)
        assert twin.risk_scores["src/migrations"] == pytest.approx(0.325)
        assert twin.risk_scores["src/migrations"] > twin.risk_scores["src/db"]

    def test_impact_sorted_by_graph_distance_downstream_only(self) -> None:
        twin = build_from_symbol_index(_build_index())
        impacted = impact_estimate(twin, ["src/payments/gateway.py"])
        assert [(entry.module, entry.distance) for entry in impacted] == [
            ("src/payments", 0),
            ("src/orders", 1),
            ("web", 2),
        ]
        assert "src/db" not in {entry.module for entry in impacted}
        assert impacted[1].reason == "depends on src/payments"

    def test_impact_multi_path_and_risk_tiebreak(self) -> None:
        twin = build_from_symbol_index(_build_index())
        impacted = impact_estimate(
            twin, ["src/payments/gateway.py", "src/db/repository.py"],
        )
        assert [(entry.module, entry.distance) for entry in impacted] == [
            ("src/db", 0),
            ("src/payments", 0),
            ("src/migrations", 1),
            ("src/orders", 1),
            ("web", 2),
        ]
        assert impacted[0].reason == "changed: src/db/repository.py"

    def test_impact_ignores_unknown_paths(self) -> None:
        twin = build_from_symbol_index(_build_index())
        assert impact_estimate(twin, ["docs/readme.md"]) == []

    def test_impact_on_empty_twin(self) -> None:
        twin = RepositoryTwin({}, (), (), (), {}, {})
        assert impact_estimate(twin, ["src/anything.py"]) == []


# ---------------------------------------------------------------------------
# repair queue fixtures
# ---------------------------------------------------------------------------


def _ticket(
    ticket_id: str,
    source: TicketSource,
    severity: Severity,
    sla_hours: int,
    budget: float,
    created_at: datetime,
    status: TicketStatus = TicketStatus.PENDING,
) -> RepairTicket:
    return RepairTicket(ticket_id, source, severity, sla_hours, budget, status, created_at)


def _ticket_set() -> list[RepairTicket]:
    return [
        _ticket(
            "T-1", TicketSource.CI, Severity.MEDIUM, 48, 5.0,
            datetime(2025, 1, 1, tzinfo=UTC),
        ),
        _ticket(
            "T-2", TicketSource.DEPENDABOT, Severity.CRITICAL, 24, 3.0,
            datetime(2025, 1, 2, tzinfo=UTC),
        ),
        _ticket(
            "T-3", TicketSource.SENTRY, Severity.HIGH, 24, 4.0,
            datetime(2025, 1, 1, 12, tzinfo=UTC),
        ),
        _ticket(
            "T-4", TicketSource.SCAN, Severity.LOW, 96, 1.0,
            datetime(2025, 1, 3, tzinfo=UTC),
        ),
        _ticket(
            "T-5", TicketSource.SCAN, Severity.LOW, 24, 2.0,
            datetime(2025, 1, 4, tzinfo=UTC),
        ),
        _ticket(
            "T-6", TicketSource.CI, Severity.LOW, 24, 0.5,
            datetime(2025, 1, 1, 6, tzinfo=UTC),
            TicketStatus.DONE,
        ),
    ]


class TestRepairQueue:
    """§19.5: priority ordering, rate limits and the low-risk threshold."""

    def test_priority_order_severity_then_sla(self) -> None:
        assert [t.ticket_id for t in priority_order(_ticket_set())] == [
            "T-2", "T-3", "T-1", "T-5", "T-4",
        ]

    def test_priority_order_drops_non_pending(self) -> None:
        ordered = priority_order(_ticket_set())
        assert all(ticket.ticket_id != "T-6" for ticket in ordered)

    def test_priority_order_fifo_tiebreak(self) -> None:
        early = _ticket(
            "E", TicketSource.SCAN, Severity.LOW, 24, 1.0,
            datetime(2025, 1, 1, tzinfo=UTC),
        )
        late = _ticket(
            "L", TicketSource.SCAN, Severity.LOW, 24, 1.0,
            datetime(2025, 1, 2, tzinfo=UTC),
        )
        assert [t.ticket_id for t in priority_order([late, early])] == ["E", "L"]

    def test_auto_eligibility_low_risk_threshold(self) -> None:
        by_id = {ticket.ticket_id: ticket for ticket in _ticket_set()}
        assert is_auto_eligible(by_id["T-4"])
        assert is_auto_eligible(by_id["T-5"])
        assert not is_auto_eligible(by_id["T-1"])
        assert not is_auto_eligible(by_id["T-2"])
        assert not is_auto_eligible(by_id["T-3"])

    def test_auto_eligibility_budget_and_severity_caps(self) -> None:
        by_id = {ticket.ticket_id: ticket for ticket in _ticket_set()}
        assert not is_auto_eligible(by_id["T-5"], budget_cap=1.0)
        assert is_auto_eligible(by_id["T-4"], budget_cap=1.0)
        assert is_auto_eligible(by_id["T-1"], severity_cap=Severity.MEDIUM)

    def test_rate_limit_per_source(self) -> None:
        limits = {
            TicketSource.CI: 1,
            TicketSource.DEPENDABOT: 1,
            TicketSource.SENTRY: 1,
            TicketSource.SCAN: 1,
        }
        allowed = apply_rate_limits(priority_order(_ticket_set()), limits)
        assert [t.ticket_id for t in allowed] == ["T-2", "T-3", "T-1", "T-5"]

    def test_rate_limit_missing_source_denies_by_default(self) -> None:
        allowed = apply_rate_limits(
            priority_order(_ticket_set()), {TicketSource.CI: 1},
        )
        assert [t.ticket_id for t in allowed] == ["T-1"]

    def test_plan_dispatch_splits_auto_escalate_deferred(self) -> None:
        limits = {
            TicketSource.CI: 1,
            TicketSource.DEPENDABOT: 1,
            TicketSource.SENTRY: 1,
            TicketSource.SCAN: 1,
        }
        plan = plan_dispatch(_ticket_set(), limits=limits)
        assert [t.ticket_id for t in plan.auto] == ["T-5"]
        assert [t.ticket_id for t in plan.deferred] == ["T-4"]
        assert [t.ticket_id for t in plan.escalate] == ["T-2", "T-3", "T-1"]


# ---------------------------------------------------------------------------
# rejection learning fixtures
# ---------------------------------------------------------------------------


def _rejection_records() -> list[RejectionRecord]:
    return [
        RejectionRecord(
            reason="reviewer: CI failed, token ghp_" + "a" * 36 + " was logged",
            wrong_assumption="UserRepository.save always flushes the user_session",
            valid_fix_path="call db.commit() before returning",
        ),
        RejectionRecord(
            reason="reviewer: CI failed, token ghp_" + "a" * 36 + " was logged",
            wrong_assumption="UserRepository.save always flushes the user_session",
            valid_fix_path="call db.commit() before returning",
        ),
        RejectionRecord(
            reason="specproof blocked: Bearer abcdefghijklmnopqrstuvwxyz12345 in headers",
            wrong_assumption="UserRepository.save always flushes the user_session",
            valid_fix_path="flush explicitly and verify the row",
        ),
        RejectionRecord(
            reason="human fix accepted",
            wrong_assumption="",
            valid_fix_path="not applicable",
        ),
    ]


class TestRejectionLearning:
    """§19.6: sanitization round-trip, rule extraction and eval-case hooks."""

    def test_sanitize_strips_secrets_and_identifiers(self) -> None:
        record = RejectionRecord(
            reason=(
                "build failed: token ghp_" + "a" * 36
                + " and Bearer abcdefghijklmnopqrstuvwxyz12345"
            ),
            wrong_assumption="UserRepository.save always flushes the user_session",
            valid_fix_path="jdbc:mysql://admin:secretpass@db.example:3306/app was removed",
        )
        sane = sanitize_record(record)
        assert sane.sanitized
        assert not record.sanitized
        assert "ghp_" not in sane.reason
        assert "Bearer abc" not in sane.reason
        assert "[REDACTED:github_token]" in sane.reason
        assert "[REDACTED:bearer_token]" in sane.reason
        assert "UserRepository" not in sane.wrong_assumption
        assert "user_session" not in sane.wrong_assumption
        assert "[IDENT]" in sane.wrong_assumption
        assert "always flushes" in sane.wrong_assumption
        assert "secretpass" not in sane.valid_fix_path
        assert "[REDACTED:jdbc_credentials]" in sane.valid_fix_path

    def test_sanitize_round_trip_via_repo_redaction(self) -> None:
        # The llm-key pattern lives in providers/redaction.py; the fake key
        # is assembled at runtime so no key-shaped literal is committed.
        fake_key = "s" + "k" + "-" + "a" * 24
        record = RejectionRecord(
            reason="leaked config: key=" + fake_key,
            wrong_assumption="config loading is safe",
            valid_fix_path="move the key to the environment",
        )
        sane = sanitize_record(record)
        assert fake_key not in sane.reason
        assert "[REDACTED:llm_api_key]" in sane.reason
        assert sane.wrong_assumption == "config loading is safe"

    def test_sanitize_is_idempotent(self) -> None:
        record = _rejection_records()[0]
        once = sanitize_record(record)
        assert sanitize_record(once) == once

    def test_extract_rules_groups_and_orders_by_hits(self) -> None:
        rules = extract_rules(_rejection_records())
        assert len(rules) == 2
        assert [rule.hits for rule in rules] == [2, 1]
        assert rules[0].pattern == "[ident].save always flushes the [ident]"
        assert rules[0].guidance == "call db.commit() before returning"
        assert rules[1].guidance == "flush explicitly and verify the row"
        assert "UserRepository" not in rules[0].pattern
        assert "ghp_" not in rules[0].pattern

    def test_extract_rules_skips_empty_assumptions(self) -> None:
        rules = extract_rules(_rejection_records())
        assert all(rule.pattern for rule in rules)

    def test_eval_case_generation_sanitized_and_deterministic(self) -> None:
        record = _rejection_records()[2]
        case = build_eval_case(record)
        assert set(case) == {
            "id", "scenario", "rejection_reason", "expected_fix_path", "source",
        }
        assert case["source"] == "rejection_learning"
        assert len(case["id"]) == 12
        assert "UserRepository" not in case["scenario"]
        assert "Bearer" not in case["rejection_reason"]
        assert case == build_eval_case(record)
        assert case["scenario"] == sanitize_record(record).wrong_assumption

    def test_eval_cases_skip_empty_scenarios(self) -> None:
        cases = build_eval_cases(_rejection_records())
        assert len(cases) == 3
        joined = " | ".join(str(value) for value in cases)
        assert "UserRepository" not in joined
        assert "ghp_" not in joined
