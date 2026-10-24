"""#446 — the waiver lifecycle corners the existing gate does not reach.

`agent/waiver.py` is a strict four-state machine (requested →
approved / rejected / expired) with a pure validity gate.
``test_waiver.py`` already covers the happy lifecycle, the active/expired
window, immutability, UTC-naive handling and strict serialization.

What it does not reach:

* ``expire`` **exactly at** the deadline — the boundary is ``now >= deadline``,
  so expiring at the deadline instant must succeed (only strictly-before is
  refused);
* illegal transitions **from** ``expired`` (approve, reject);
* ``reject`` from ``approved``;
* a blank ``approved_by`` handed to ``approve()``;
* ``from_dict`` fail-closed branches: non-object / empty payload, a
  non-string ``valid_until``, non-string identity fields, blank optional
  fields;
* the canonical microsecond rendering of ``valid_until``;
* a **non-UTC aware** ``now`` reaching ``waiver_check`` (the deadline is
  compared in UTC, so the zone must be converted first);
* the defensive branch that keeps an approved waiver without a deadline
  from ever reading as ``active``.

The module is unchanged by this file: these are behaviour pins, not fixes.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from agent.waiver import FindingWaiver, WaiverError, WaiverStateError, waiver_check

NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
DEADLINE = NOW + timedelta(hours=1)


def _requested() -> FindingWaiver:
    return FindingWaiver(finding_id="F1", reason="r", requested_by="alice")


def _approved() -> FindingWaiver:
    return _requested().approve(
        approved_by="bob", valid_until=DEADLINE, policy_ref="p"
    )


# ── The expire boundary ─────────────────────────────────────────────────


def test_expire_exactly_at_the_deadline_succeeds() -> None:
    # The gate is "now >= deadline"; only strictly-before is refused.
    expired = _approved().expire(now=DEADLINE)
    assert expired.state == "expired"


def test_expire_one_second_before_the_deadline_is_refused() -> None:
    with pytest.raises(WaiverStateError, match="still active"):
        _approved().expire(now=DEADLINE - timedelta(seconds=1))


def test_expire_preserves_the_approval_binding() -> None:
    waiver = _approved()
    expired = waiver.expire(now=DEADLINE + timedelta(minutes=1))
    assert expired.state == "expired"
    assert expired.approved_by == "bob"
    assert expired.valid_until == waiver.valid_until
    assert expired.policy_ref == "p"
    assert expired.finding_id == waiver.finding_id


# ── Illegal transitions from every non-requested state ──────────────────


def test_expired_waiver_cannot_be_approved_or_rejected() -> None:
    expired = _approved().expire(now=DEADLINE + timedelta(hours=1))
    with pytest.raises(WaiverStateError, match="cannot approve"):
        expired.approve(approved_by="carol", valid_until=DEADLINE + timedelta(days=1))
    with pytest.raises(WaiverStateError, match="cannot reject"):
        expired.reject()


def test_approved_waiver_cannot_be_rejected() -> None:
    with pytest.raises(WaiverStateError, match="cannot reject"):
        _approved().reject()


# ── approve() input validation ──────────────────────────────────────────


def test_approve_rejects_a_blank_approver_and_strips_a_real_one() -> None:
    with pytest.raises(WaiverError, match="approved_by"):
        _requested().approve(approved_by="   ", valid_until=DEADLINE)
    with pytest.raises(WaiverError, match="approved_by"):
        _requested().approve(approved_by="", valid_until=DEADLINE)  # type: ignore[arg-type]
    approved = _requested().approve(approved_by="  bob  ", valid_until=DEADLINE)
    assert approved.approved_by == "bob"


# ── from_dict fail-closed branches ──────────────────────────────────────


@pytest.mark.parametrize("raw", [[], {}, "not-a-waiver", 42, None])
def test_from_dict_rejects_non_object_and_empty_payloads(raw: Any) -> None:
    with pytest.raises(WaiverError, match="non-empty waiver object"):
        FindingWaiver.from_dict(raw)  # type: ignore[arg-type]


def test_from_dict_rejects_non_string_valid_until() -> None:
    good = _approved().to_dict()
    for bad in (123, ["2026-08-20T13:00:00Z"], {"until": "x"}):
        with pytest.raises(WaiverError, match="valid_until"):
            FindingWaiver.from_dict({**good, "valid_until": bad})


@pytest.mark.parametrize("field", ["finding_id", "reason", "requested_by"])
def test_from_dict_rejects_non_string_identity_fields(field: str) -> None:
    payload: dict[str, Any] = {
        "finding_id": "F1",
        "reason": "r",
        "requested_by": "a",
        "state": "requested",
    }
    payload[field] = 7
    with pytest.raises(WaiverError, match=field):
        FindingWaiver.from_dict(payload)


@pytest.mark.parametrize("field", ["approved_by", "policy_ref"])
def test_from_dict_rejects_blank_optional_fields(field: str) -> None:
    with pytest.raises(WaiverError, match=field):
        FindingWaiver.from_dict({**_approved().to_dict(), field: "   "})


# ── Canonical serialization ─────────────────────────────────────────────


def test_to_dict_renders_a_microsecond_deadline() -> None:
    stamp = datetime(2026, 8, 20, 13, 0, 0, 123456, tzinfo=UTC)
    waiver = _requested().approve(approved_by="bob", valid_until=stamp)
    assert waiver.to_dict()["valid_until"] == "2026-08-20T13:00:00.123456Z"
    # and that rendering round-trips back to the same instant.
    restored = FindingWaiver.from_dict(waiver.to_dict())
    assert restored.valid_until == stamp


def test_rejected_waiver_roundtrips_through_dict() -> None:
    rejected = _requested().reject()
    data = rejected.to_dict()
    assert data["state"] == "rejected"
    assert data["approved_by"] is None
    assert data["valid_until"] is None
    assert FindingWaiver.from_dict(data) == rejected


# ── Timezone conversion in the validity gate ────────────────────────────


def test_waiver_check_converts_a_non_utc_aware_now() -> None:
    waiver = _approved()
    # 22:00 in UTC+9 is 13:00 UTC — exactly the deadline, so expired.
    at_deadline = datetime(2026, 8, 20, 22, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    assert waiver_check(waiver, at_deadline) == "expired"
    # 21:00 in UTC+9 is 12:00 UTC — an hour before the deadline.
    before = datetime(2026, 8, 20, 21, 0, 0, tzinfo=timezone(timedelta(hours=9)))
    assert waiver_check(waiver, before) == "active"


def test_an_expired_waiver_never_reads_active_even_before_its_deadline() -> None:
    # State wins over the clock: once expired, an earlier `now` cannot revive it.
    expired = _approved().expire(now=DEADLINE + timedelta(hours=1))
    assert waiver_check(expired, NOW) == "expired"


def test_an_approved_waiver_without_a_deadline_is_never_active() -> None:
    # Unreachable through the constructor (approved requires valid_until), but
    # the gate defends it: an exemption without a deadline must not read active.
    waiver = _requested().approve(approved_by="bob", valid_until=DEADLINE)
    object.__setattr__(waiver, "valid_until", None)
    assert waiver_check(waiver, NOW) == "expired"
