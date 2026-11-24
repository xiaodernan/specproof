"""Unreachable external stores must fail FAST, not hang the pipeline (#2094).

Measured 2026-11-24: with no local Redis/MinIO, redis-py 8.x's default retry
backoff made a readiness probe take ~49s and the minio SDK sat in a TCP SYN
for minutes — enough to freeze the differential/evidence pipeline and starve
the full unit suite. A store that is down is a fact to record in an EMPTY
snapshot, never a reason to block the caller. These legs pin the fast-fail
bound so a future client change cannot silently reintroduce the stall.
"""
from __future__ import annotations

import time

import pytest


def test_build_redis_client_fails_fast_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a dead loopback port, the probe returns None in a couple seconds."""
    from experiments.external_state import build_redis_client

    # Point at a loopback port with nothing listening; no external dependency.
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "1")  # port 1 is conventionally closed
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)

    t0 = time.perf_counter()
    client = build_redis_client()
    elapsed = time.perf_counter() - t0

    assert client is None, "a dead store must yield 'could not look', not a client"
    assert elapsed < 8.0, f"probe took {elapsed:.1f}s — retry backoff would hang the pipeline"


def test_minio_readiness_probe_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead MinIO endpoint reports not-ready quickly via the bounded client."""
    from storage.minio import MinIOClient, MinIOConfig

    cfg = MinIOConfig(host="127.0.0.1", port=1, secure=False)
    client = MinIOClient(cfg)

    t0 = time.perf_counter()
    ready = client.is_ready()
    elapsed = time.perf_counter() - t0

    assert ready is False
    assert elapsed < 8.0, f"minio readiness took {elapsed:.1f}s — must fail fast"
