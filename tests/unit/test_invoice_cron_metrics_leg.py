"""#272 — the invoice cron's metrics port as behaviour, not as a declaration.

#268 taught the structural gate to read shape B (``self.metrics_port`` assigned
from a ternary over ``os.getenv``). Reading is not running: before this file
nothing in the repository ever passed ``metrics_port`` to ``InvoiceCron``, so the
port an operator sets and the socket the process opens were only ever asserted to
be spelled the same way. These legs drive ``run_forever`` through exactly one
cycle and ask what binds, what answers, and what the process says when the OS
refuses.

Two facts measured on this host shape the legs:

* ``serve_metrics_in_thread`` really does raise ``OSError`` when the OS refuses a
  bind — an unroutable TEST-NET-3 address gets here (``10049`` on Windows,
  ``EADDRNOTAVAIL`` on Linux), so the failure path needs no invented error class.
* On Windows a second bind to an already-listening 127.0.0.1 port USED to succeed
  (``SO_REUSEADDR`` means "may share" there), which is why the refusal leg below
  injects the ``OSError`` the Linux deployment plane raises. #284 measured the
  consequence and fixed the endpoint: the bind now refuses a held port on both
  planes, so ``test_a_real_port_holder_makes_the_cron_say_not_serving`` drives the
  same branch with two live sockets and no invented error at all. The injected
  leg stays, because it pins the reason text the container plane produces.
* The answering leg first asks the OS for a free port on a throwaway socket,
  closes that socket, and hands the number it was given to ``InvoiceCron`` — so
  the port the cron declares cannot be one something else already holds.
"""

from __future__ import annotations

import errno
import http.client
import logging
import re
import socket
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from observability import metrics_http
from storage.billing import SqliteBillingStore, seed_default_plans
from storage.invoice_cron import DEFAULT_METRICS_PORT, InvoiceCron

#: The refusal the Linux deployment plane raises when the scrape port is taken.
_EADDRINUSE = OSError(98, "Address already in use")


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SqliteBillingStore]:
    billing = SqliteBillingStore(tmp_path / "billing.db")
    seed_default_plans(billing)
    yield billing
    billing.close()


def _stub(body: Callable[[int], None]) -> Callable[..., None]:
    """A stand-in metrics server that records the port it was asked to open."""

    def _serve(host: str | None = None, port: int = 9100) -> None:
        body(int(port))

    return _serve


def _refusing(body: Callable[[], OSError]) -> Callable[..., None]:
    def _serve(host: str | None = None, port: int = 9100) -> None:
        raise body()

    return _serve


def _run_one_cycle(cron: InvoiceCron) -> int:
    """Run ``run_forever`` for exactly one loop body and return the cycle count.

    The loop stops when ``_running`` flips, and ``cycle()`` is its only body, so
    stopping from inside the cycle makes the drive deterministic — no killer
    thread, no sleeping on the 3600s interval.
    """
    cycles: list[int] = []

    def _cycle(now: float | None = None) -> None:
        cycles.append(1)
        cron.stop()

    cron.cycle = _cycle  # type: ignore[method-assign]
    cron.run_forever()
    return len(cycles)


def _startup_claim(caplog: pytest.LogCaptureFixture, port: int) -> str:
    """The one startup line that names ``port``, or a failure that counts them."""
    claims = [
        rec.getMessage()
        for rec in caplog.records
        if re.search(rf"metrics port={port}\b", rec.getMessage())
    ]
    assert len(claims) == 1, f"the startup line must name port {port} exactly once, got {claims}"
    return claims[0]


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    conn.close()
    return resp.status, body


def test_injected_metrics_port_reaches_the_metrics_server(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub(seen.append))
    cycles = _run_one_cycle(InvoiceCron(store, interval=0.0, metrics_port=9999))
    assert seen == [9999], (
        f"shape B must carry the injected port to the server: it opened {seen}. "
        f"Anything but the injected number means the constructor ternary picked "
        f"the env/default branch while a caller was holding a port."
    )
    assert cycles == 1


def test_the_env_knob_sets_the_served_port(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    monkeypatch.delenv("INVOICE_CRON_METRICS_PORT", raising=False)
    monkeypatch.setenv("INVOICE_CRON_METRICS_PORT", "9555")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub(seen.append))
    _run_one_cycle(InvoiceCron(store, interval=0.0))
    assert seen == [9555], (
        f"the operator knob is the whole point of the port: with INVOICE_CRON_METRICS_PORT=9555 "
        f"and no injected argument the server opened {seen}"
    )


def test_the_served_default_is_the_module_constant_not_a_copy(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[int] = []
    monkeypatch.delenv("INVOICE_CRON_METRICS_PORT", raising=False)
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub(seen.append))
    _run_one_cycle(InvoiceCron(store, interval=0.0))
    assert seen == [DEFAULT_METRICS_PORT], (
        f"with the knob unset the server must open DEFAULT_METRICS_PORT ({DEFAULT_METRICS_PORT}), "
        f"got {seen} — compared against the imported constant, so a hand-typed copy in this "
        f"file could not make it pass"
    )


def test_the_port_the_cron_declares_really_answers_metrics(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The strongest form: no stub, an OS-assigned free port, and an HTTP read."""
    opened: list[Any] = []
    real = metrics_http.serve_metrics_in_thread

    def _capture(host: str | None = None, port: int = 9100) -> Any:
        server = real(host=host, port=port)
        opened.append(server)
        return server

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    declared = int(probe.getsockname()[1])
    probe.close()
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _capture)
    try:
        _run_one_cycle(InvoiceCron(store, interval=0.0, metrics_port=declared))
        assert opened, f"run_forever never opened a metrics server on the declared port {declared}"
        served = int(opened[0].server_address[1])
        assert served == declared, (
            f"the process declared port {declared} but opened {served} — the knob and the "
            f"socket are the same promise only if these numbers match"
        )
        status, body = _get(served, "/metrics")
        assert status == 200, f"the declared port answered {status}, not 200"
        assert "specproof_up" in body, f"/metrics on the declared port served {body[:80]!r}"
    finally:
        for server in opened:
            server.shutdown()
            server.server_close()


def test_a_refused_bind_is_disclosed_and_the_loop_survives(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    port = 9411
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _refusing(lambda: _EADDRINUSE))
    with caplog.at_level(logging.INFO, logger="storage.invoice_cron"):
        cycles = _run_one_cycle(InvoiceCron(store, interval=0.0, metrics_port=port))
    claim = _startup_claim(caplog, port)
    assert "NOT serving" in claim, (
        f"a refused metrics bind has to be said in the sentence that names the port, "
        f"otherwise the operator reads a scrape target that does not exist: {claim!r}"
    )
    assert "Address already in use" in claim, (
        f"the disclosure must carry the OS's reason, not a marker: {claim!r}"
    )
    assert cycles == 1, (
        "a metrics bind failure must not stop the billing loop that is the process's job"
    )


def test_a_successful_bind_claims_serving_and_not_the_failure(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The other arm of the same sentence, so the disclosure cannot be a constant."""
    port = 9412
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub(lambda p: None))
    with caplog.at_level(logging.INFO, logger="storage.invoice_cron"):
        _run_one_cycle(InvoiceCron(store, interval=0.0, metrics_port=port))
    claim = _startup_claim(caplog, port)
    assert ": serving" in claim, f"a bound metrics server must be claimed as serving: {claim!r}"
    assert "NOT serving" not in claim, f"the refusal wording leaked into the success arm: {claim!r}"


def test_a_real_port_holder_makes_the_cron_say_not_serving(
    store: SqliteBillingStore, caplog: pytest.LogCaptureFixture
) -> None:
    """#284 — the refusal arm, produced by the OS holding the port.

    ``test_a_refused_bind_is_disclosed_and_the_loop_survives`` injects the Linux
    container's ``OSError(98)`` because on this host a second bind to a live port
    used to succeed quietly. #284 made the endpoint refuse a stolen port, so the
    disclosure branch can now be driven by a real collision instead of a
    transcription of another platform's errno. The reason text is the OS's own
    (localized on Windows), so the leg charges the claim and a non-empty reason,
    not a spelling.
    """
    owner = metrics_http.serve_metrics_in_thread(host="127.0.0.1", port=0)
    held = int(owner.server_address[1])
    try:
        with caplog.at_level(logging.INFO, logger="storage.invoice_cron"):
            cycles = _run_one_cycle(InvoiceCron(store, interval=0.0, metrics_port=held))
        claim = _startup_claim(caplog, held)
        assert "NOT serving" in claim, (
            f"another process answers port {held}, yet the cron's startup line reads "
            f"{claim!r}. Its own gauges are unreachable from that moment and the line "
            "is the only place the process says what it opened."
        )
        assert claim.index("NOT serving (") + len("NOT serving (") < len(claim) - 1, (
            f"the refusal must carry the OS's reason inside the parentheses: {claim!r}"
        )
        assert cycles == 1, (
            "a refused metrics port must still not stop the billing loop — the cron's "
            "port is in no scrape roster, so continuing is the honest half of this shape"
        )
    finally:
        owner.shutdown()
        owner.server_close()


def test_the_real_server_raises_oserror_when_the_os_refuses_the_bind() -> None:
    """Why the handler catches OSError: the refusal is the OS's, not a fixture's.

    This leg refuses for the address reason (``EADDRNOTAVAIL``); the port-held
    refusal — the case an operator actually hits — is ``test_L01`` in
    ``tests/unit/test_metrics_port_ownership_leg.py``, and the disclosure it
    produces in this process is the leg above. #284: before that, nothing in the
    repository could make a bind fail for the collision reason on this host.
    """
    with pytest.raises(OSError) as refused:
        metrics_http.serve_metrics_in_thread(host="203.0.113.42", port=0)
    exc = refused.value
    code = int(getattr(exc, "winerror", None) or exc.errno or 0)
    # The code, not merely "an errno": #284's arm battery measured that arming
    # SO_EXCLUSIVEADDRUSE while SO_REUSEADDR is still set makes THIS call fail too
    # — with 10022 (invalid option), not 10049. A leg that accepted any errno
    # would then stay green while the endpoint refuses every bind, which is the
    # fail-closed outage #284's L03 exists to catch.
    assert code == errno.EADDRNOTAVAIL, (
        "an unroutable TEST-NET-3 bind must be refused BY THE ADDRESS "
        f"(EADDRNOTAVAIL is {errno.EADDRNOTAVAIL} here), got {type(exc).__name__} "
        f"code={code} ({exc!r}) — any other code means the socket options, not the "
        "address, ended this bind"
    )


def test_a_non_bind_defect_is_not_swallowed(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the OS's bind refusals are recoverable; a broken call site is not."""

    def _blow(host: str | None = None, port: int = 9100) -> None:
        raise RuntimeError("metrics handler is misconfigured")

    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _blow)
    with pytest.raises(RuntimeError, match="misconfigured"):
        _run_one_cycle(InvoiceCron(store, interval=0.0))
