"""Stress Smoke's targeted lane regression — the CLI was always broken for
`--target` and silently produced 100% errors because it appended a literal "/"
to the target. This test catches that (and any similar regression) without
jeopardising CI: it runs the script against a loopback HTTP server in a child
process, keeps the scope tiny so the gate stays fast.

It does **not** assert anything about capacity, throughput, or production
fitness. It only pins the targeted lane's URL composition.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

# The host plane has exactly one owner for "give me a port nobody holds":
# tests/unit/port_probe.py::free_port (#475). This module must not grow a
# second occupancy probe — the deploy gate pins that rule.
from tests.unit.port_probe import free_port as _free_port

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "stress_smoke.py"

_SERVER_SNIPPET = """
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', '15')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, fmt, *a):
        pass

server = HTTPServer(('127.0.0.1', int(sys.argv[1])), H)
server.serve_forever()
"""


@pytest.mark.slow
def test_target_lane_regression():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-u", "-c", _SERVER_SNIPPET, str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail("scratch server exited early")
            # hit it with a bare urllib request so we know it bound
            try:
                import urllib.request
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.05)
        else:
            pytest.fail("scratch server never came up")

        env = dict(os.environ)
        # clear any proxy vars that interfere, if any are set in the shell
        for k in list(env):
            if "proxy" in k.lower():
                env.pop(k)

        result = subprocess.run(
            [
                sys.executable, "-u", str(SCRIPT),
                "--target", f"http://127.0.0.1:{port}/health",
                "--concurrency", "2", "--per-thread", "2", "--rounds", "1", "--warmup", "0",
                "--timeout", "5",
            ],
            env=env, capture_output=True, text=True, timeout=30,
        )
        out = (result.stdout or "") + (result.stderr or "")
        assert "err=0.00%" in out or "err=0%" in out, out
        assert "BUDGET-BLOWN" not in out, out
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
