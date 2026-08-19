"""Unit tests for agent.waiver — the FindingWaiver lifecycle and validity gate.

No network, no external services: every case is a pure function call over
frozen dataclass transitions. Covers requested → approved/rejected/expired,
the active/expired boundary around valid_until, immutability, UTC
normalization and strict serialization.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent.waiver import (
    FindingWaiver,
    WaiverError,
    WaiverStateError,
    waiver_check,
)

NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _requested() -> FindingWaiver:
    return FindingWaiver(
        finding_id="FIND-AUTH-01",
        reason="legacy annotation path, low residual risk",
        requested_by="alice",
    )


def _approved() -> FindingWaiver:
    return _requested().approve(
        approved_by="bob",
        valid_until=NOW + timedelta(hours=1),
        policy_ref="allow-auth-waivers",
    )


# ── Lifecycle ───────────────────────────────────────────────────────────


def test_requested_waiver_is_pending() -> None:
    waiver = _requested()
    assert waiver.state == "requested"
    assert waiver_check(waiver, NOW) == "pending"


def test_approve_binds_approver_deadline_and_policy_ref() -> None:
    waiver = _approved()
    assert waiver.state == "approved"
    assert waiver.approved_by == "bob"
    assert waiver.valid_until == NOW + timedelta(hours=1)
    assert waiver.policy_ref == "allow-auth-waivers"


def test_active_until_deadline_then_expired() -> None:
    waiver = _approved()
    assert waiver_check(waiver, NOW) == "active"
    assert waiver_check(waiver, NOW + timedelta(minutes=59)) == "active"
    assert waiver_check(waiver, NOW + timedelta(hours=1)) == "expired"
    assert waiver_check(waiver, NOW + timedelta(days=1)) == "expired"


def test_expire_transition_and_idempotence() -> None:
    waiver = _approved()
    with pytest.raises(WaiverStateError, match="still active"):
        waiver.expire(now=NOW)
    expired = waiver.expire(now=NOW + timedelta(hours=2))
    assert expired.state == "expired"
    assert expired.approved_by == "bob"
    assert expired.valid_until == waiver.valid_until
    assert expired.expire(now=NOW + timedelta(hours=3)) is expired
    assert waiver_check(expired, NOW) == "expired"


def test_reject_is_terminal() -> None:
    waiver = _requested()
    rejected = waiver.reject()
    assert rejected.state == "rejected"
    assert waiver_check(rejected, NOW) == "rejected"
    with pytest.raises(WaiverStateError):
        rejected.reject()
    with pytest.raises(WaiverStateError):
        rejected.approve(approved_by="bob", valid_until=NOW + timedelta(hours=1))
    with pytest.raises(WaiverStateError):
        rejected.expire(now=NOW)


def test_approve_twice_fails() -> None:
    waiver = _approved()
    with pytest.raises(WaiverStateError):
        waiver.approve(approved_by="carol", valid_until=NOW + timedelta(days=1))


def test_requested_can_expire_without_approval() -> None:
    expired = _requested().expire(now=NOW)
    assert expired.state == "expired"
    assert expired.approved_by is None
    assert waiver_check(expired, NOW) == "expired"


# ── Time handling ───────────────────────────────────────────────────────


def test_naive_datetimes_treated_as_utc() -> None:
    deadline = (NOW + timedelta(hours=1)).replace(tzinfo=None)
    waiver = _requested().approve(approved_by="bob", valid_until=deadline)
    assert waiver.valid_until == NOW + timedelta(hours=1)
    assert waiver_check(waiver, NOW.replace(tzinfo=None)) == "active"
    assert waiver_check(waiver, NOW + timedelta(hours=2)) == "expired"


# ── Construction and serialization validation ───────────────────────────


def test_approved_requires_approver_and_deadline() -> None:
    with pytest.raises(WaiverError, match="approved_by"):
        FindingWaiver(
            finding_id="FIND-1",
            reason="r",
            requested_by="a",
            state="approved",
            valid_until=NOW + timedelta(hours=1),
        )
    with pytest.raises(WaiverError, match="valid_until"):
        FindingWaiver(
            finding_id="FIND-1",
            reason="r",
            requested_by="a",
            state="approved",
            approved_by="bob",
        )


def test_construction_validates_fields() -> None:
    with pytest.raises(WaiverError, match="finding_id"):
        FindingWaiver(finding_id="  ", reason="r", requested_by="a")
    with pytest.raises(WaiverError, match="reason"):
        FindingWaiver(finding_id="FIND-1", reason="", requested_by="a")
    with pytest.raises(WaiverError, match="requested_by"):
        FindingWaiver(finding_id="FIND-1", reason="r", requested_by="  ")
    with pytest.raises(WaiverError, match="state"):
        FindingWaiver(  # type: ignore[arg-type]
            finding_id="FIND-1", reason="r", requested_by="a", state="granted"
        )
    with pytest.raises(WaiverError, match="policy_ref"):
        FindingWaiver(finding_id="FIND-1", reason="r", requested_by="a", policy_ref="  ")


def test_transitions_return_new_instances() -> None:
    requested = _requested()
    approved = requested.approve(approved_by="bob", valid_until=NOW + timedelta(hours=1))
    assert approved is not requested
    assert requested.state == "requested"
    rejected = _requested().reject()
    assert rejected is not requested


def test_to_dict_roundtrip() -> None:
    waiver = _approved()
    data = waiver.to_dict()
    assert data == {
        "finding_id": "FIND-AUTH-01",
        "state": "approved",
        "reason": "legacy annotation path, low residual risk",
        "requested_by": "alice",
        "approved_by": "bob",
        "valid_until": (NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy_ref": "allow-auth-waivers",
    }
    restored = FindingWaiver.from_dict(data)
    assert restored == waiver
    assert FindingWaiver.from_dict(restored.to_dict()) == restored


def test_from_dict_fails_closed() -> None:
    good = _approved().to_dict()
    with pytest.raises(WaiverError, match="unknown waiver field"):
        FindingWaiver.from_dict({**good, "granted_by": "eve"})
    with pytest.raises(WaiverError, match="missing required"):
        FindingWaiver.from_dict(
            {"finding_id": "FIND-1", "reason": "r", "requested_by": "a"}
        )
    with pytest.raises(WaiverError, match="state"):
        FindingWaiver.from_dict({**good, "state": "granted"})
    with pytest.raises(WaiverError, match="valid_until"):
        FindingWaiver.from_dict({**good, "valid_until": "yesterday"})


def test_waiver_check_rejects_non_waiver() -> None:
    with pytest.raises(WaiverError):
        waiver_check("not a waiver", NOW)  # type: ignore[arg-type]
