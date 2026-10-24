"""Process-local Prometheus /metrics HTTP endpoint (stdlib only).

The worker and the outbox relay register metrics in their own in-process
registry (observability.metrics) but run no web framework. This module
gives them a minimal ThreadingHTTPServer serving the same text exposition
the API exposes at GET /metrics, so Prometheus can scrape them directly.

Bind address: METRICS_BIND_HOST overrides; otherwise containers bind
0.0.0.0 (Prometheus scrapes across the same compose network) and local
host processes bind 127.0.0.1.

Port: the signature default is the number the scrape roster declares for the
worker job (infra/prometheus/prometheus.yml), so a listener created by
omitting port= takes over the endpoint Prometheus scrapes for that job; pass
the keyword. tests/unit/test_scrape_roster_ports_answer_their_own_numbers.py
L5 re-measures this default against the roster and refuses this paragraph once
the two numbers stop colliding.
"""

from __future__ import annotations

import os
import socket
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
        # container-wide bind; the port is never published to the host
        return "0.0.0.0"  # nosec B104
    return "127.0.0.1"


class _MetricsServer(ThreadingHTTPServer):
    """A metrics endpoint that only reports a port it actually owns.

    ``HTTPServer`` sets ``allow_reuse_address``, and on Windows ``SO_REUSEADDR``
    means "this address may be shared": a second process binds a port another
    process is already answering on, its thread serves nothing, and every scrape
    keeps returning the first owner's exposition. The caller sees no error, so a
    startup line saying the metrics port is serving is a lie about a socket
    nobody can reach. ``SO_EXCLUSIVEADDRUSE`` makes a live collision fail with
    ``OSError`` the way POSIX bind already does, so returning from the
    constructor means this process holds the port.

    Measured on a Windows host (the plane ``scripts/start_local.ps1`` runs):
    exclusive + no reuse refuses a live listener with 10048, still rebinds the
    same port right after a served request, and still rebinds after a scrape
    whose connection lingered — so the fail-closed relay/worker do not die on
    restart. Setting both options instead fails every bind with 10022.
    """

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve_metrics_in_thread(
    host: str | None = None,
    port: int = 9100,
) -> ThreadingHTTPServer:
    """Start the /metrics server in a daemon thread; returns the server.

    host=None resolves via _resolve_bind_host() (container/local aware,
    METRICS_BIND_HOST override). The returned server can be shut down
    with server.shutdown() in tests; the daemon thread dies with the
    process, so production code can call this and forget about it.

    Raises OSError when the port is already being answered by another process.
    """
    if host is None:
        host = _resolve_bind_host()
    server = _MetricsServer((host, port), _MetricsHandler)
    thread = threading.Thread(
        target=server.serve_forever, daemon=True, name="metrics-http"
    )
    thread.start()
    return server
