"""#284 — the metrics port belongs to one process, and the OS now says so.

``serve_metrics_in_thread`` is the endpoint all three listeners hand to
Prometheus (``agent/worker.py``, ``storage/outbox_relay.py``,
``storage/invoice_cron.py``). #272 measured that a Windows host refuses nothing
when a second process opens the same port and wrote that off as a platform
artifact — "the deployment plane (Linux containers) refuses it, which is the
case the production handler was written for". Measured again here, on the plane
``scripts/start_local.ps1`` actually runs, the consequence is not cosmetic:

  two processes, one 127.0.0.1 metrics port (probe ``.scratch/m276_winbind_parent.py``)
    PARENT bound 62964, own GET returns parent's exposition
    CHILD  bound port 62964 without OSError
    READ 0..3: the port answers parent_marker=True child_marker=False

So the second process's ``specproof_*`` series are unreachable while its own
registry keeps counting into a socket nobody can scrape, and the first owner's
numbers are served under the second process's name. The same probe shape now
runs as a shipped leg (L02), so the claim cannot rot back into a comment.

The fix is in ``observability/metrics_http.py``: bind through a subclass that,
where the platform offers it, clears ``allow_reuse_address`` and sets
``SO_EXCLUSIVEADDRUSE``. The socket-option matrix was measured on this host, not
recalled from documentation (``.scratch/m276_option_matrix.py``); for each shape,
the live collision / a rebind after serve+close / a rebind after a lingered scrape:

  SO_REUSEADDR (before the fix)     STOLE IT / ok / ok
  exclusive, reuse cleared          refused 10048 / ok / ok   <- shipped
  both options set                  10022 on every bind
  neither option                    refused 10048 / ok / ok

The third row is why L03 exists: forgetting to clear ``allow_reuse_address``
does not soften the guard, it makes every bind fail, and the fail-closed
relay/worker would then die at startup with no metrics endpoint at all.

Case map:
  L01 a live listener refuses a second bind, and the port still answers its owner
  L02 a second PROCESS is refused too (the reading above, shipped as a leg)
  L03 the released port can be reopened: the guard costs restarts nothing
  L04 the endpoint module builds its server through the ownership-checking class
      and never calls the raw HTTP server constructor
Out-of-band (``storage/invoice_cron.py`` and ``storage/outbox_relay.py`` each
get their runtime leg in their own file, where the harness already exists):
  the cron's startup line says NOT serving for a REAL refusal, not an injected
  ``OSError(98)``, and the relay's loop never starts when the port is held.
"""

from __future__ import annotations

import ast
import errno
import http.client
import socket
import subprocess
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from observability.metrics import incr, render_text
from observability.metrics_http import serve_metrics_in_thread

ROOT = Path(__file__).resolve().parents[2]
METRICS_HTTP = ROOT / "observability" / "metrics_http.py"

#: A metric name only this file emits, so a scrape reading can tell whose
#: exposition answered.
OWNER_MARKER = "specproof_metrics_port_owner_marker_total"


def _free_port() -> int:
    """Ask the OS for a port nothing holds, then hand that number over."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def _bind(port: int) -> ThreadingHTTPServer:
    """Bind the shipped endpoint, or fail with the OS's own reason."""
    try:
        return serve_metrics_in_thread(host="127.0.0.1", port=port)
    except OSError as exc:
        raise AssertionError(
            f"the owner must be able to open port {port}, but the OS refused it "
            f"({type(exc).__name__}: {getattr(exc, 'winerror', None) or exc.errno}). "
            "L01/L02/L03 measure the refusal of a SECOND bind, so the first one "
            "has to succeed for any of them to mean anything."
        ) from exc


def _get(port: int, needle: str) -> bool:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/metrics")
    try:
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
    finally:
        conn.close()
    assert needle in render_text(), (
        f"{needle} is not in this process's own registry, so the scrape reading "
        "below could not distinguish owners even if the port answered"
    )
    return needle in body


def _code(exc: OSError) -> int:
    return int(getattr(exc, "winerror", None) or exc.errno or 0)


def test_L01_a_live_listener_refuses_a_second_bind_and_keeps_ansuring_its_owner() -> None:
    port = _free_port()
    first = _bind(port)
    try:
        incr(OWNER_MARKER)
        assert _get(port, OWNER_MARKER), (
            f"port {port} must answer the process that opened it before any "
            "collision is attempted — L01 measured nothing if the owner is unreadable"
        )
        with pytest.raises(OSError) as refused:
            serve_metrics_in_thread(host="127.0.0.1", port=port)
        exc = refused.value
        assert _code(exc) == errno.EADDRINUSE, (
            f"the second bind on {port} must be refused BY THE PORT BEING HELD, got "
            f"{type(exc).__name__} code={_code(exc)} (EADDRINUSE is {errno.EADDRINUSE} "
            "on this platform). Any other refusal — an unroutable address, a "
            "setsockopt conflict — would leave this leg green for the wrong reason."
        )
        assert _get(port, OWNER_MARKER), (
            f"after refusing the second bind, port {port} stopped answering its "
            "owner: the guard must reject a squatter, not close the socket"
        )
    finally:
        first.shutdown()
        first.server_close()


_CHILD = """
import sys, time, socket
from observability.metrics_http import serve_metrics_in_thread
port = int(sys.argv[1])
try:
    server = serve_metrics_in_thread(host="127.0.0.1", port=port)
except OSError as exc:
    print("REFUSED", int(getattr(exc, "winerror", None) or exc.errno or 0), flush=True)
    raise SystemExit(1)
print("BOUND", port, flush=True)
time.sleep(2)
server.shutdown()
server.server_close()
print("RELEASED", flush=True)
"""


def test_L02_a_second_process_cannot_share_the_metrics_port() -> None:
    """The stolen-port reading, across a process boundary.

    L01 could still be answered by one interpreter keeping two sockets apart in
    memory; the deployment case is two processes. The child reports the OS's
    refusal code so an unrelated bind error cannot pass as the collision.
    """
    port = _free_port()
    owner = _bind(port)
    try:
        proc = subprocess.run(
            [sys.executable, "-u", "-c", _CHILD, str(port)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=90,
        )
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        assert lines, (
            f"the child printed nothing (exit {proc.returncode}); stderr: "
            f"{proc.stderr.strip()[-400:]}"
        )
        refusal = [line for line in lines if line.startswith("REFUSED")]
        assert refusal, (
            f"the child bound metrics port {port} while another process was already "
            f"answering it: {lines}. This is the defect #284 fixes — the scrape keeps "
            "reading the first owner and the second process's gauges are unreachable."
        )
        code = int(refusal[0].split()[1])
        assert code == errno.EADDRINUSE, (
            f"the child was refused with code {code}, not EADDRINUSE "
            f"({errno.EADDRINUSE}) — the refusal must be about the port being held"
        )
    finally:
        owner.shutdown()
        owner.server_close()


def test_L03_a_released_metrics_port_can_be_reopened_three_times() -> None:
    """The cost side: refusing a squatter must not refuse a restart.

    A relay or worker that restarts under an active scrape used to lean on
    ``SO_REUSEADDR``. If the exclusive bind also blocked that (the matrix's
    "both options" row fails every bind with 10022), the guard would take the
    endpoint down for the whole deployment, and this leg — which binds, scrapes
    and reopens the SAME port — goes red.
    """
    port = _free_port()
    for attempt in (1, 2, 3):
        server = _bind(port)
        try:
            incr(OWNER_MARKER)
            assert _get(port, OWNER_MARKER), (
                f"attempt {attempt} on port {port} bound but did not answer /metrics"
            )
        finally:
            server.shutdown()
            server.server_close()


def test_L04_the_endpoint_refuses_a_stolen_port_by_construction_not_by_caller() -> None:
    """Whoever calls ``serve_metrics_in_thread`` gets the ownership check.

    The three listeners differ on purpose in what they DO with the refusal (the
    cron discloses and continues, the relay and worker let it stop the process),
    so the guarantee cannot live in their code. It lives here, and a refactor
    that re-inlines ``ThreadingHTTPServer(...)`` silently puts it back to
    "anyone may bind, nobody is served".
    """
    tree = ast.parse(METRICS_HTTP.read_text("utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    def _called_name(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    raw = [f"{_called_name(node)}:{node.lineno}" for node in calls
           if _called_name(node) in {"HTTPServer", "ThreadingHTTPServer"}]
    assert not raw, (
        f"observability/metrics_http.py builds {raw}: a raw HTTP server inherits "
        "HTTPServer's allow_reuse_address and accepts a port another process is "
        "already answering. Construct _MetricsServer instead."
    )
    built = [f"{_called_name(node)}:{node.lineno}" for node in calls
             if _called_name(node) == "_MetricsServer"]
    assert len(built) == 1, (
        f"exactly one construction of the ownership-checking server expected, got "
        f"{built} — serve_metrics_in_thread must be the only place it is built"
    )

    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    server_cls = next((c for c in classes if c.name == "_MetricsServer"), None)
    assert server_cls is not None, "_MetricsServer is gone from the module"
    bases = [getattr(b, "id", getattr(b, "attr", "")) for b in server_cls.bases]
    assert "ThreadingHTTPServer" in bases, (
        f"_MetricsServer must still BE the threaded server, bases were {bases}"
    )
    bind_fn = next((f for f in server_cls.body
                    if isinstance(f, ast.FunctionDef) and f.name == "server_bind"), None)
    assert bind_fn is not None, (
        "_MetricsServer no longer overrides server_bind: the options would be set "
        "after the socket is already bound"
    )
    body_src = ast.unparse(bind_fn)
    assert "SO_EXCLUSIVEADDRUSE" in body_src, (
        f"server_bind does not ask for exclusive use, it reads: {body_src}"
    )
    assert "allow_reuse_address" in body_src, (
        f"server_bind leaves SO_REUSEADDR armed, which conflicts with the exclusive "
        f"option on Windows (measured: every bind fails with 10022): {body_src}"
    )
    guards = [node for node in ast.walk(bind_fn) if isinstance(node, ast.If)]
    assert guards, (
        "the exclusive option is set unconditionally: POSIX platforms do not have "
        "SO_EXCLUSIVEADDRUSE and the container deployment would crash on import-time bind"
    )
