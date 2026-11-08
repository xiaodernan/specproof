"""Durations and TTLs must not ride the wall clock.

2026-11-08 (see ledger #1520): on this Windows host the wall clock advances in
~15.6 ms ticks, and can jump backwards/forwards when the NTP client snaps it.
Any "- started" computed with ``time.time()`` therefore reads bogus numbers
after a snap — the duration metric reads 0 or a huge outlier, the SLO
denominator stretches, an OIDC discovery cache ages past its TTL, uptime reads
negative. ``time.monotonic()`` is the correct primitive: non-decreasing,
immune to wall-clock snaps, strictly ordered.

This gate pins the three sites that were migrated (and would silently lie on
the next regression):

- ``agent/worker.py`` — the job-level duration gauge and the depth-labelled
  histogram must derive from ``started = time.monotonic()``;
- ``observability/metrics.py`` — the ``/metrics`` exposition's ``uptime_seconds``
  is process uptime, not wall-clock distance since module import;
- ``api/identity/oidc.py`` — the discovery-document TTL is a lifetime in
  seconds from the last fetch, not wall-clock distance since import/process
  start.

A site that legitimately needs the wall clock (real timestamps for the
database, e.g. ``agent/worker.py``'s ``reclaim_reclaim_recovery_lag_seconds``,
which compares a *process* clock against a *DB* ``NOW()`` heartbeat and is
documented as approximate) is deliberately not covered here.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _text(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def test_worker_job_durations_ride_the_monotonic_clock() -> None:
    source = _text("agent/worker.py")
    assert "started = time.monotonic()" in source
    assert "time.monotonic() - started" in source
    assert "time.time() - started" not in source


def test_process_uptime_rides_the_monotonic_clock() -> None:
    source = _text("observability/metrics.py")
    assert "_started_at = time.monotonic()" in source
    assert "uptime_seconds" in source
    assert "time.monotonic() - _started_at" in source
    assert "time.time() - _started_at" not in source


def test_oidc_discovery_ttl_rides_the_monotonic_clock() -> None:
    source = _text("api/identity/oidc.py")
    assert "time.monotonic() - self._discovery_at" in source
    assert "self._discovery_at = time.monotonic()" in source
    assert "time.time() - self._discovery_at" not in source
    assert "self._discovery_at = time.time()" not in source
