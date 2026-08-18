"""Unit tests for the process-local Prometheus /metrics endpoint.

Covers observability/metrics_http.py (worker / outbox-relay sidecar
endpoint) and the histogram rendering added to observability/metrics.py.
"""

from __future__ import annotations

import http.client
import os

import pytest

from observability.metrics import incr, observe_duration, render_text
from observability.metrics_http import _resolve_bind_host, serve_metrics_in_thread


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, body


def test_metrics_endpoint_serves_registry_text() -> None:
    server = serve_metrics_in_thread(host="127.0.0.1", port=0)
    port = int(server.server_address[1])
    incr("jobs_completed_total")
    try:
        status, body = _get(port, "/metrics")
        assert status == 200
        assert "specproof_up" in body
        assert "specproof_jobs_completed_total" in body
    finally:
        server.shutdown()


def test_metrics_endpoint_health_and_404() -> None:
    server = serve_metrics_in_thread(host="127.0.0.1", port=0)
    port = int(server.server_address[1])
    try:
        status, body = _get(port, "/health")
        assert status == 200
        assert body == "ok\n"
        status, _ = _get(port, "/other")
        assert status == 404
    finally:
        server.shutdown()


def test_bind_host_defaults_to_loopback_on_local_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("METRICS_BIND_HOST", raising=False)
    monkeypatch.setattr(os.path, "exists", lambda path: False)
    assert _resolve_bind_host() == "127.0.0.1"


def test_bind_host_defaults_to_all_interfaces_in_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("METRICS_BIND_HOST", raising=False)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/.dockerenv")
    # 断言容器分支的预期绑定行为: metrics 端口需可被 Prometheus 跨容器刮取。
    assert _resolve_bind_host() == "0.0.0.0"  # nosec B104


def test_bind_host_env_override_wins_in_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("METRICS_BIND_HOST", "10.1.2.3")
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/.dockerenv")
    assert _resolve_bind_host() == "10.1.2.3"


def test_histogram_renders_prometheus_exposition() -> None:
    observe_duration("jobs_duration_seconds", 120.0)
    text = render_text()
    assert "# TYPE specproof_jobs_duration_seconds histogram" in text
    # 120s: bucket 60 不累计, bucket 120 及以上 (含 +Inf) 全部累计
    assert 'specproof_jobs_duration_seconds_bucket{le="60"} 0' in text
    assert 'specproof_jobs_duration_seconds_bucket{le="120"} 1' in text
    assert 'specproof_jobs_duration_seconds_bucket{le="+Inf"} 1' in text
    assert "specproof_jobs_duration_seconds_sum 120.0" in text
    assert "specproof_jobs_duration_seconds_count 1" in text
