"""Continuous Repair Queue — first slice (计划书 §19.5).

CI failures, Dependabot alerts, Sentry issues and security-scan findings
are unified into one controlled repair queue. Every ticket carries a
priority (severity), an SLA, a budget and an independent acceptance
status; pure policy functions decide what an agent may auto-process, what
is escalated to humans and what is deferred by per-source rate limits.

Honest scope (first slice):

- The four sources are the 计划书-listed CI/Dependabot/Sentry/scan lanes;
  production alerts and user tickets are later slices of the same queue.
- Policies are pure: they never mutate tickets, timers or global state.
  Callers own status transitions (pending -> in_progress -> done /
  escalated); the plan functions only classify and order.
- Rate limits deny by default: a source without an entry in the limits
  mapping has capacity zero, so a forgotten lane can never flood the
  queue by accident.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class TicketSource(StrEnum):
    """The external channel that filed the ticket."""

    CI = "ci"
    DEPENDABOT = "dependabot"
    SENTRY = "sentry"
    SCAN = "scan"


class Severity(StrEnum):
    """Ticket severity, ordered CRITICAL > HIGH > MEDIUM > LOW."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketStatus(StrEnum):
    """Lifecycle state of a ticket (transitions owned by the caller)."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ESCALATED = "escalated"


_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}


@dataclass(frozen=True)
class RepairTicket:
    """One repair task: who filed it, how urgent, how much it may cost."""

    ticket_id: str
    source: TicketSource
    severity: Severity
    sla_hours: int
    budget: float
    status: TicketStatus = TicketStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class DispatchPlan:
    """Queue policy outcome: dispatch now, defer, or escalate to humans."""

    auto: tuple[RepairTicket, ...]
    escalate: tuple[RepairTicket, ...]
    deferred: tuple[RepairTicket, ...]


def _priority_key(ticket: RepairTicket) -> tuple[int, int, datetime, str]:
    return (
        -_SEVERITY_RANK[ticket.severity],
        ticket.sla_hours,
        ticket.created_at,
        ticket.ticket_id,
    )


def priority_order(tickets: Iterable[RepairTicket]) -> list[RepairTicket]:
    """Order pending tickets: severity desc, shorter SLA first, FIFO.

    Tickets in any other status are not queueable and are dropped from
    the result.
    """
    pending = [ticket for ticket in tickets if ticket.status is TicketStatus.PENDING]
    return sorted(pending, key=_priority_key)


def is_auto_eligible(
    ticket: RepairTicket,
    *,
    severity_cap: Severity = Severity.LOW,
    budget_cap: float | None = None,
) -> bool:
    """Low-risk threshold: may an agent auto-process this ticket?

    Eligible when severity is at or below the cap (default LOW) and, when
    a budget cap is configured, the ticket budget stays within it. A cap
    of None leaves the budget unconstrained.
    """
    severity_ok = _SEVERITY_RANK[ticket.severity] <= _SEVERITY_RANK[severity_cap]
    budget_ok = budget_cap is None or ticket.budget <= budget_cap
    return severity_ok and budget_ok


def apply_rate_limits(
    ordered: Iterable[RepairTicket],
    limits: Mapping[TicketSource, int],
) -> list[RepairTicket]:
    """Keep the first N tickets per source in the given order.

    The input must already be priority-ordered; a source missing from
    limits has capacity zero (deny by default) and non-positive caps deny
    the whole lane.
    """
    used: dict[TicketSource, int] = {}
    allowed: list[RepairTicket] = []
    for ticket in ordered:
        capacity = limits.get(ticket.source, 0)
        if used.get(ticket.source, 0) < capacity:
            used[ticket.source] = used.get(ticket.source, 0) + 1
            allowed.append(ticket)
    return allowed


def plan_dispatch(
    tickets: Iterable[RepairTicket],
    *,
    limits: Mapping[TicketSource, int],
    severity_cap: Severity = Severity.LOW,
    budget_cap: float | None = None,
) -> DispatchPlan:
    """Classify the queue: auto (dispatch now), escalate, deferred.

    Pending tickets are priority-ordered; tickets above the low-risk
    threshold are escalated to humans; the rest are auto candidates that
    pass through the per-source rate limits — candidates left over by the
    limits are deferred, not dropped.
    """
    ordered = priority_order(tickets)
    auto_candidates = [
        ticket
        for ticket in ordered
        if is_auto_eligible(
            ticket, severity_cap=severity_cap, budget_cap=budget_cap
        )
    ]
    candidate_ids = {ticket.ticket_id for ticket in auto_candidates}
    escalate = [ticket for ticket in ordered if ticket.ticket_id not in candidate_ids]
    auto = apply_rate_limits(auto_candidates, limits)
    auto_ids = {ticket.ticket_id for ticket in auto}
    deferred = [ticket for ticket in auto_candidates if ticket.ticket_id not in auto_ids]
    return DispatchPlan(auto=tuple(auto), escalate=tuple(escalate), deferred=tuple(deferred))


__all__ = [
    "DispatchPlan",
    "RepairTicket",
    "Severity",
    "TicketSource",
    "TicketStatus",
    "apply_rate_limits",
    "is_auto_eligible",
    "plan_dispatch",
    "priority_order",
]
