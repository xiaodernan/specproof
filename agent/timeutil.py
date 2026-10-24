"""Datetime helpers shared by the policy and waiver domains.

``as_utc`` and ``iso_utc`` were byte-identical copies in
``agent/policy_dsl.py`` and ``agent/waiver.py`` (#447). Two copies of one
normalisation rule is one rule waiting to drift, so they now live here and
both domains import them.
"""
from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC; naive values are assumed UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    """Canonical ISO-8601 UTC rendering used by serialization and digests."""
    utc = as_utc(value)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")
