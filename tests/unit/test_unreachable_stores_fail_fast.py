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


def test_minio_reachable_store_still_reports_ready() -> None:
    """The bounded client must not break the REACHABLE path (#2094 boundary).

    A real S3 ListBuckets XML from a local mock must still answer ready=True —
    the 1s timeout / retries=False only make an unreachable store fail fast.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from storage.minio import MinIOClient, MinIOConfig

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListAllMyBucketsResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        '<Buckets><Bucket><Name>specproof-reports</Name>'
        '<CreationDate>2024-01-01T00:00:00.000Z</CreationDate></Bucket></Buckets>'
        '<Owner><ID>x</ID><DisplayName>x</DisplayName></Owner>'
        '</ListAllMyBucketsResult>'
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = xml.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_HEAD(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        client = MinIOClient(MinIOConfig(host="127.0.0.1", port=port, secure=False))
        assert client.is_ready() is True
    finally:
        srv.shutdown()
