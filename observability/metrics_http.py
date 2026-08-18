"""Process-local Prometheus /metrics HTTP endpoint (stdlib only).

The worker and the outbox relay register metrics in their own in-process
registry (observability.metrics) but run no web framework. This module
gives them a minimal ThreadingHTTPServer serving the same text exposition
the API exposes at GET /metrics, so Prometheus can scrape them directly.

Bind address: METRICS_BIND_HOST overrides; otherwise containers bind
0.0.0.0 (Prometheus scrapes across the same compose network) and local
host processes bind 127.0.0.1.
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from observability.metrics import render_text


class _MetricsHandler(BaseHTTPRequestHandler):
    """Serve GET /metrics (text exposition) and GET /health (liveness)."""

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path == "/metrics":
            body = render_text().encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/plain; version=0.0.4; charset=utf-8"
            )
        elif self.path == "/health":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        else:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence per-request access logging (Prometheus scrapes every 15s)."""


def _resolve_bind_host() -> str:
    """Bind address for the metrics endpoint.

    Explicit METRICS_BIND_HOST wins. Otherwise: inside a container bind
    0.0.0.0 (Prometheus scrapes across the compose network; the port is
    never published to the host), and on a local host bind 127.0.0.1.
    """
    explicit = os.getenv("METRICS_BIND_HOST")
    if explicit:
        return explicit
    if os.path.exists("/.dockerenv"):
        # 容器网络内 metrics 端口需对外可刮取: Prometheus 在同 compose 网络
        # 跨容器抓取, 端口不发布到宿主机; 因此容器内默认绑定全网卡。
        return "0.0.0.0"  # nosec B104
    return "127.0.0.1"


def serve_metrics_in_thread(
    host: str | None = None,
    port: int = 9100,
) -> ThreadingHTTPServer:
    """Start the /metrics server in a daemon thread; returns the server.

    host=None resolves via _resolve_bind_host() (container/local aware,
    METRICS_BIND_HOST override). The returned server can be shut down
    with server.shutdown() in tests; the daemon thread dies with the
    process, so production code can call this and forget about it.
    """
    if host is None:
        host = _resolve_bind_host()
    server = ThreadingHTTPServer((host, port), _MetricsHandler)
    thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="metrics-http"
    )
    thread.start()
    return server
