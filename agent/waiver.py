"""Finding waiver state machine (工业化指南 阶段 3, ``finding_waivers`` 领域对象).

A waiver is the explicit, time-boxed human decision that one finding does
not block the merge. The lifecycle is a strict four-state machine::

    requested ──approve──▶ approved ──(now ≥ valid_until)──▶ expired
        │                     │
        ├──────reject──────▶ rejected
        └──────expire──────▶ expired

Every transition returns a NEW frozen instance; state is never mutated in
place, so waiver history stays reproducible and audit-friendly. Approval
binds the approver, the validity deadline and the policy rule that allowed
the waiver (``policy_ref`` — the ``allow_waiver`` action in
``agent/policy_dsl.py``).

``waiver_check(waiver, now)`` is the pure validity gate. For an
approved waiver it is strictly ``active``/``expired`` around
``valid_until`` (active while ``now < valid_until``; at or after
the deadline it is expired). Non-granting states are reported honestly as
``pending`` (requested) / ``rejected`` — they never exempt a
finding. Naive datetimes are treated as UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

WaiverState = Literal["requested", "approved", "rejected", "expired"]
WaiverCheck = Literal["active", "expired", "pending", "rejected"]

#: The four lifecycle states; unknown states fail closed.
WAIVER_STATES: frozenset[str] = frozenset({"requested", "approved", "rejected", "expired"})

_WAIVER_FIELDS: frozenset[str] = frozenset(
    {
        "finding_id",
        "state",
        "reason",
        "requested_by",
        "approved_by",
        "valid_until",
        "policy_ref",
    }
)


class WaiverError(ValueError):
    """FindingWaiver construction or serialization was rejected."""


class WaiverStateError(WaiverError):
    """Illegal state transition for a waiver."""


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC; naive values are assumed UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    """Canonical ISO-8601 UTC rendering used by serialization."""
    utc = _as_utc(value)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class FindingWaiver:
    """One finding waiver with a strict requested→approved/rejected/expired lifecycle."""

    finding_id: str
    reason: str
    requested_by: str
    state: WaiverState = "requested"
    approved_by: str | None = None
    valid_until: datetime | None = None
    policy_ref: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("finding_id", "reason", "requested_by"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise WaiverError(f"{field_name} must be a non-empty string")
            object.__setattr__(self, field_name, value.strip())
        if self.state not in WAIVER_STATES:
            raise WaiverError(
                f"unknown waiver state {self.state!r}; expected one of {sorted(WAIVER_STATES)}"
            )
        if self.approved_by is not None:
            stripped_approver = self.approved_by.strip()
            if not stripped_approver:
                raise WaiverError("approved_by must be a non-empty string when set")
            object.__setattr__(self, "approved_by", stripped_approver)
        if self.valid_until is not None:
            object.__setattr__(self, "valid_until", _as_utc(self.valid_until))
        if self.state == "approved" and (
            self.approved_by is None or self.valid_until is None
        ):
            raise WaiverError(
                "an approved waiver must record approved_by and valid_until"
            )
        if self.policy_ref is not None:
            stripped_ref = self.policy_ref.strip()
            if not stripped_ref:
                raise WaiverError("policy_ref must be a non-empty string when set")
            object.__setattr__(self, "policy_ref", stripped_ref)

    def approve(
        self,
        *,
        approved_by: str,
        valid_until: datetime,
        policy_ref: str | None = None,
    ) -> FindingWaiver:
        """requested → approved, binding approver, deadline and policy ref."""
        if self.state != "requested":
            raise WaiverStateError(
                f"cannot approve waiver {self.finding_id} in state {self.state!r}; "
                "only a 'requested' waiver can be approved"
            )
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise WaiverError("approved_by must be a non-empty string")
        return FindingWaiver(
            finding_id=self.finding_id,
            reason=self.reason,
            requested_by=self.requested_by,
            state="approved",
            approved_by=approved_by,
            valid_until=valid_until,
            policy_ref=policy_ref,
        )

    def reject(self) -> FindingWaiver:
        """requested → rejected (terminal)."""
        if self.state != "requested":
            raise WaiverStateError(
                f"cannot reject waiver {self.finding_id} in state {self.state!r}; "
                "only a 'requested' waiver can be rejected"
            )
        return FindingWaiver(
            finding_id=self.finding_id,
            reason=self.reason,
            requested_by=self.requested_by,
            state="rejected",
        )

    def expire(self, *, now: datetime) -> FindingWaiver:
        """requested/approved → expired; idempotent once expired."""
        if self.state == "rejected":
            raise WaiverStateError(f"cannot expire waiver {self.finding_id}: it was rejected")
        if self.state == "expired":
            return self
        if self.state == "approved":
            deadline = self.valid_until
            assert deadline is not None  # construction invariant for approved waivers
            if _as_utc(now) < deadline:
                raise WaiverStateError(
                    f"waiver {self.finding_id} is still active until {_iso_utc(deadline)}"
                )
        return FindingWaiver(
            finding_id=self.finding_id,
            reason=self.reason,
            requested_by=self.requested_by,
            state="expired",
            approved_by=self.approved_by,
            valid_until=self.valid_until,
            policy_ref=self.policy_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        """Canonical serialization (fixed key order) for persistence/evidence."""
        return {
            "finding_id": self.finding_id,
            "state": self.state,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "approved_by": self.approved_by,
            "valid_until": _iso_utc(self.valid_until) if self.valid_until is not None else None,
            "policy_ref": self.policy_ref,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> FindingWaiver:
        """Strict deserialization; unknown fields or values fail closed."""
        if not isinstance(raw, dict) or not raw:
            raise WaiverError("expected a non-empty waiver object")
        unknown = sorted(set(raw) - _WAIVER_FIELDS)
        if unknown:
            raise WaiverError(f"unknown waiver field(s) {unknown}")
        missing = [
            field for field in ("finding_id", "reason", "requested_by", "state") if field not in raw
        ]
        if missing:
            raise WaiverError(f"missing required waiver field(s) {missing}")
        state = raw["state"]
        if state not in WAIVER_STATES:
            raise WaiverError(
                f"unknown waiver state {state!r}; expected one of {sorted(WAIVER_STATES)}"
            )
        valid_until_raw = raw.get("valid_until")
        valid_until: datetime | None = None
        if valid_until_raw is not None:
            if not isinstance(valid_until_raw, str):
                raise WaiverError("valid_until must be an ISO-8601 string")
            try:
                valid_until = _as_utc(datetime.fromisoformat(valid_until_raw))
            except ValueError as exc:
                raise WaiverError(f"invalid valid_until {valid_until_raw!r}: {exc}") from exc
        return cls(
            finding_id=raw["finding_id"],
            reason=raw["reason"],
            requested_by=raw["requested_by"],
            state=state,
            approved_by=raw.get("approved_by"),
            valid_until=valid_until,
            policy_ref=raw.get("policy_ref"),
        )


def waiver_check(waiver: FindingWaiver, now: datetime) -> WaiverCheck:
    """Validity gate: active/expired around valid_until; pending/rejected never grant."""
    if not isinstance(waiver, FindingWaiver):
        raise WaiverError("waiver_check expects a FindingWaiver instance")
    if waiver.state == "requested":
        return "pending"
    if waiver.state == "rejected":
        return "rejected"
    if waiver.state == "expired":
        return "expired"
    deadline = waiver.valid_until
    if deadline is None:
        # Unreachable for approved waivers (construction invariant), but an
        # exemption without a deadline must never be treated as active.
        return "expired"
    return "active" if _as_utc(now) < deadline else "expired"
