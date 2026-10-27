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

import ast
import errno
import functools
import http.client
import importlib.util
import logging
import re
import socket
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from observability import metrics_http
from observability.metrics import incr
from storage.billing import SqliteBillingStore, period_bounds, seed_default_plans
from storage.invoice_cron import DEFAULT_METRICS_PORT, InvoiceCron
from tests.unit.port_probe import free_port

ROOT = Path(__file__).resolve().parents[2]

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

    # #475: the free-port probe has ONE owner — tests/unit/port_probe.py.
    declared = free_port()
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


# ─────────────────── the exempt number, occupied for real (#450) ───────────────────
#
# #427 closed the roster side and named what it left: its L2–L4 occupy the numbers
# ``infra/prometheus/prometheus.yml`` declares, and 9103 is deliberately NOT declared
# there (#232's ``_UNROSTERED_LISTENERS`` exempts it and L15 keeps that honest). So the
# sentence whose whole subject is a socket was still only ever compared:
# RUNBOOK.md:44-46 promises 「指标端点 `INVOICE_CRON_METRICS_PORT` (默认 9103) 上的
# /metrics 目前没有任何抓取作业读它」, and every leg above handed the endpoint a
# kernel-chosen number. Measured first with ``.scratch/m450_census.py`` and
# ``.scratch/m450_probe.py``:
#
#   the default path (no argument, no knob) reaches a socket at ('127.0.0.1', 9103)
#   and answers /metrics with this process's registry; a real generation run moves
#   specproof_invoice_cron_invoices_total from absent to 1 on that wire;
#   the deploy plane claims nothing at 9103 — compose's mapping numbers are
#   [3307, 5673, 6380, 15673] plus the roster's [8000, 8889, 9090, 9100, 9101, 15692].
#
# Case map for this block:
#   E1 the exempt number is occupied by the process's own default path and answers the
#      path #232 owns as the scrape default, with this run's registry on the wire
#   E2 the collision fate at that number: a live listener holds it, the cron acquires
#      no socket, says NOT serving, and keeps invoicing
#   E3 the family the cron module emits really moves on that endpoint, per the run that
#      earned the count — with the counters that must NOT move charged as controls
#   E4 no deploy carrier claims the number, and the predicate is driven from both sides
#      with planted rows so the 「0 hits」 is evidence
#
# Boundary: E1 and E3 need 9103 free and say so out loud (``pytest.skip`` naming the
# incumbent) when another process answers it on the plane running the suite — a
# certified-elsewhere claim is not a certified-here one. E2 and E4 measure on every
# plane: E2 takes the number itself, and E4 never binds at all. The population E4 reads
# is compose ``ports:`` mappings plus roster targets; ``expose:`` entries are not in it
# because they declare an in-network container port, which cannot collide with a bind on
# the host — and #232 L15's ``_module_carriers`` owns the 「谁起这个进程」 half.

GATE_232 = ROOT / "tests" / "unit" / "test_listen_port_knobs_bind_the_scrape_roster.py"
OPS_DOCS = ("docs/operations/RUNBOOK.md", "docs/operations/OBSERVABILITY.md")
CRON_MODULE = "storage/invoice_cron.py"
CRON_KNOB = "INVOICE_CRON_METRICS_PORT"

#: Registered by these legs and nowhere else. A read of the exempt number that comes
#: back without it is not reading THIS process's registry, which is what lets E1 tell
#: its own socket from an incumbent answering the same documented number.
MARKER = "invoice_cron_metrics_leg_exempt_marker_total"

#: 2026-10-05T00:00:00Z, so ``cycle()`` bills the closed month 2026-09 without reading
#: the wall clock. Same anchor tests/unit/test_invoice_cron.py pins its cases on.
_OCT = 1_791_158_400.0
_PERIOD = "2026-09"

#: An endpoint path as an operator doc writes it: leading slash, lower-case, no dots
#: and not the tail of a longer word. That is what excludes ``storage/invoice_cron.py``
#: and ``infra/prometheus/prometheus.yml`` from being read as promised paths.
_PATH_TOKEN = re.compile(r"(?<![\w./\-])(/[a-z][a-z0-9_]*)(?![\w./\-])")
_SAMPLE_LINE = re.compile(r"^specproof_(\w+) (\S+)$", re.M)
_TYPE_LINE = re.compile(r"^# TYPE specproof_(\w+) (\w+)$", re.M)


@functools.cache
def _gate232() -> Any:
    """#232's readers, loaded once.

    The exempt legs ask the same parser the rostered legs ask: a second local yaml
    reader would be the drift #232's own L14 exists to catch.
    """
    spec = importlib.util.spec_from_file_location("gate232_for_exempt_legs", GATE_232)
    assert spec is not None and spec.loader is not None, f"cannot load {GATE_232}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["gate232_for_exempt_legs"] = module
    spec.loader.exec_module(module)
    return module


def _scrape_default_path() -> str:
    """The path a scrape job uses when its entry declares no ``metrics_path``."""
    return str(_gate232().DEFAULT_METRICS_PATH)


def _exempt_is_free() -> bool:
    """Whether this plane will hand the exempt number to a new listener right now."""
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", DEFAULT_METRICS_PORT))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def _recording(opened: list[Any], refusals: list[OSError]) -> Callable[..., Any]:
    """The REAL endpoint, wrapped so a leg can tell a bound socket from a refusal.

    ``run_forever`` throws the server object away, so nothing downstream can ask which
    socket the process ended up holding; this records what the OS answered.
    """
    real = metrics_http.serve_metrics_in_thread

    def _serve(host: str | None = None, port: int = 9100) -> Any:
        try:
            server = real(host=host, port=int(port))
        except OSError as exc:
            refusals.append(exc)
            raise
        opened.append(server)
        return server

    return _serve


def _close_all(opened: list[Any]) -> None:
    for server in opened:
        server.shutdown()
        server.server_close()


def _doc_path_claims(knob: str) -> dict[str, set[str]]:
    """Per operator doc: every endpoint-path token written on a line naming ``knob``."""
    out: dict[str, set[str]] = {}
    for rel in OPS_DOCS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        tokens = {
            match.group(1)
            for line in text.splitlines()
            if knob in line
            for match in _PATH_TOKEN.finditer(line)
        }
        if tokens:
            out[rel] = tokens
    return out


def _emitted_names() -> dict[str, str]:
    """Every metric name the cron module emits, with the kind the call declares.

    Read off ``storage/invoice_cron.py`` itself, so E3 charges the family the process
    actually produces rather than a list this file retypes.
    """
    tree = ast.parse((ROOT / CRON_MODULE).read_text(encoding="utf-8"))
    kinds = {"incr": "counter", "set_gauge": "gauge", "observe_duration": "histogram"}
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        kind = kinds.get(node.func.id)
        if kind is None or not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        name = node.args[0].value
        if isinstance(name, str):
            assert out.get(name, kind) == kind, f"{name} is emitted as two kinds"
            out[name] = kind
    assert len(out) >= 4, f"{CRON_MODULE} emits only {sorted(out)} — the scan lost the module"
    return out


def _samples(body: str) -> dict[str, float]:
    return {m.group(1): float(m.group(2)) for m in _SAMPLE_LINE.finditer(body)}


def _types(body: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _TYPE_LINE.finditer(body)}


def _claims_the_number(
    port: int, roster: dict[str, Any], mappings: list[dict[str, str]]
) -> list[str]:
    """Which deploy declarations occupy ``port`` — roster targets and compose mappings.

    Driven three ways by E4: against the shipped population (expected empty), against
    planted rows naming the exempt number (expected to fire), and against a planted row
    naming a different number (expected to stay silent). A predicate that only ever sees
    the shipped files cannot show it would refuse.
    """
    needle = str(port)
    out: list[str] = []
    for job, info in sorted(roster.items()):
        if int(info["port"]) == port:
            out.append(f"名册作业 {job} 抓 {info['host']}:{needle}")
    for row in mappings:
        if needle in (row["left"], row["right"]):
            out.append(f"{row['service']} 映射 {row['left']}:{row['right']}")
    return out


def test_E1_the_exempt_number_is_occupied_and_answers_the_promised_path(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The first leg in the repository to hold 9103, through the process's own default.

    No ``metrics_port`` argument and no env knob — this is the shape ``python -m
    storage.invoice_cron`` takes on a host — so the number being occupied is the number
    the module's literal declares. Measured before this leg: the socket ends up at
    ``('127.0.0.1', 9103)`` and answers the scrape default with this process's registry.
    """
    monkeypatch.delenv(CRON_KNOB, raising=False)
    monkeypatch.delenv("SPECPROOF_INVOICE_PERIOD", raising=False)
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    if not _exempt_is_free():
        pytest.skip(
            f"another process already answers 127.0.0.1:{DEFAULT_METRICS_PORT}, so this plane "
            "cannot certify that the CRON holds it (E2 and E4 still measure here)"
        )
    opened: list[Any] = []
    refusals: list[OSError] = []
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _recording(opened, refusals))
    incr(MARKER)
    path = _scrape_default_path()
    try:
        with caplog.at_level(logging.INFO, logger="storage.invoice_cron"):
            _run_one_cycle(InvoiceCron(store, interval=0.0))
        assert not refusals, (
            f"the exempt number probed free seconds ago and the cron's bind was refused by "
            f"{refusals} — the leg cannot tell a stolen port from a lost race"
        )
        assert opened, "run_forever never reached a socket on the number the module declares"
        server = opened[0]
        occupied_port = int(server.server_address[1])
        occupied_address = str(server.server_address[0])
        assert occupied_port == DEFAULT_METRICS_PORT, (
            f"the process declares {DEFAULT_METRICS_PORT} and the socket it holds answers "
            f"{occupied_port}: RUNBOOK:44 points an operator at a number nothing binds"
        )
        assert occupied_address == "127.0.0.1", (
            f"METRICS_BIND_HOST=127.0.0.1 resolves and the endpoint is asked for it, yet the "
            f"exempt socket is bound to {occupied_address!r} — the address half of the promise "
            "never reaches a bind"
        )
        status, body = _get(occupied_port, path)
        assert status == 200, (
            f"the exempt number is occupied but answers {status} at {path}; the roster's remedy "
            f"for this exemption is one new job line with no metrics_path, which would scrape "
            f"{body[:120]!r}"
        )
        assert f"specproof_{MARKER} " in body, (
            f"this process occupies {occupied_port} yet its own marker is not on the wire — the "
            f"read is not this registry: {body[:120]!r}"
        )
        claims = _doc_path_claims(CRON_KNOB)
        assert claims, (
            f"no operator doc names an endpoint path on a line naming {CRON_KNOB}, so E1's "
            "premise that a reader is promised a path needs re-deriving from the shipped docs"
        )
        for rel, tokens in sorted(claims.items()):
            assert tokens == {path}, (
                f"{rel} promises {sorted(tokens)} for {CRON_KNOB} while the scrape default is "
                f"{path!r} (#232's DEFAULT_METRICS_PATH) — the exempt endpoint answers a path "
                "the reader was not told about"
            )
        scraped = [
            job
            for job, info in sorted(_gate232()._roster().items())
            if int(info["port"]) == occupied_port
        ]
        assert not scraped, (
            f"{occupied_port} is now scraped by {scraped}: this leg certifies an UNREAD "
            "endpoint, and an un-armed process cannot answer a live job — move the knob into "
            "#232's _LISTEN_PORT_KNOBS instead of reading it here"
        )
    finally:
        _close_all(opened)


def test_E2_a_live_holder_of_the_exempt_number_is_disclosed_not_fatal(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """RUNBOOK:46's promise, charged at the documented number rather than any number.

    ``test_a_real_port_holder_makes_the_cron_say_not_serving`` above holds whatever port the
    OS handed out, so it proves the refusal arm of the code but not the sentence the operator
    reads about 9103. This leg takes the number itself first, then proves by counting what the
    endpoint recorded that the cron acquired no socket of its own.
    """
    monkeypatch.delenv(CRON_KNOB, raising=False)
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    opened: list[Any] = []
    refusals: list[OSError] = []
    recorder = _recording(opened, refusals)
    holder: Any = None
    try:
        holder = recorder(port=DEFAULT_METRICS_PORT)
    except OSError as taken:
        refusals.clear()
        print(f"[#450] E2 holder: an incumbent already answers {DEFAULT_METRICS_PORT}: {taken!r}")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", recorder)
    bound_before = len(opened)
    refused_before = len(refusals)
    try:
        status, body = _get(DEFAULT_METRICS_PORT, _scrape_default_path())
        assert status == 200, (
            f"the exempt number refused a bind but answers {_scrape_default_path()} with "
            f"{status}: {body[:120]!r} — the refusal is not a live listener, so this leg is "
            "measuring an OS-level conflict rather than a port owner"
        )
        with caplog.at_level(logging.INFO, logger="storage.invoice_cron"):
            cycles = _run_one_cycle(InvoiceCron(store, interval=0.0))
        assert len(opened) == bound_before, (
            f"the cron acquired a socket on {DEFAULT_METRICS_PORT} while a listener was "
            f"answering it ({opened[bound_before:]!r}) — #284's exclusive bind is gone, so the "
            "startup line and the wire are different processes"
        )
        assert len(refusals) == refused_before + 1, (
            f"the cron's bind at the exempt number must be the one refusal this leg counts "
            f"(got {refusals[refused_before:]!r})"
        )
        claim = _startup_claim(caplog, DEFAULT_METRICS_PORT)
        assert "NOT serving" in claim, (
            f"9103 is answered by somebody else and the line an operator reads is {claim!r}"
        )
        assert claim.index("NOT serving (") + len("NOT serving (") < len(claim) - 1, (
            f"the refusal at the exempt number must carry the OS's reason: {claim!r}"
        )
        assert cycles == 1, (
            "losing the exempt port must not stop invoicing — nothing scrapes it, which is the "
            "reason #232's L15 exempts it at all"
        )
    finally:
        if holder is not None:
            holder.shutdown()
            holder.server_close()


def test_E3_a_real_run_moves_the_cron_family_on_the_exempt_endpoint(
    store: SqliteBillingStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint exists to carry the process's numbers, so this reads them off the wire.

    ``test_metrics_scrape_leg_serves_every_emitted_name.py`` registers names by hand on a
    kernel port and proves servability. This leg runs the production cycle — a subscribed
    tenant, a usage row, ``ensure_invoice`` — against the number the module declares, and
    charges the delta to the run that earned it, with the counters that must NOT move held
    as controls so a constant cannot pass for a count.
    """
    monkeypatch.delenv(CRON_KNOB, raising=False)
    monkeypatch.delenv("SPECPROOF_INVOICE_PERIOD", raising=False)
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    if not _exempt_is_free():
        pytest.skip(
            f"another process answers 127.0.0.1:{DEFAULT_METRICS_PORT}, so the counters read "
            "here would not be this run's"
        )
    store.upsert_subscription("tenant-a", "pro", "active", 0.0, 4_000_000_000.0)
    start, _end = period_bounds(_PERIOD)
    assert store.record_usage(
        "verify:exempt-leg", "tenant-a", "job_verify", 3.0, "job", start + 60.0
    )
    opened: list[Any] = []
    refusals: list[OSError] = []
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _recording(opened, refusals))
    path = _scrape_default_path()
    cron = InvoiceCron(store, interval=0.0, now_fn=lambda: _OCT)
    real_cycle = cron.cycle
    readings: list[dict[str, float]] = []
    summaries: list[Any] = []
    failures: list[BaseException] = []

    def _cycle(now: float | None = None) -> None:
        # The bind happens before the loop body, so this is the earliest moment a scrape
        # can read the registry: the before-half has to be taken from inside the cycle.
        # run_forever wraps the body in ``except Exception`` and keeps looping, so a red
        # premise here would be swallowed into a log line and the drive would never end:
        # collect it, stop in every path, and re-charge it outside the loop.
        try:
            status, body = _get(DEFAULT_METRICS_PORT, path)
            assert status == 200, f"the exempt endpoint answered {status} before the run"
            readings.append(_samples(body))
            summary = real_cycle(now)
            if summary is not None:
                summaries.append(summary)
        except BaseException as exc:  # noqa: BLE001 — re-raised below, never logged away
            failures.append(exc)
        cron.stop()

    cron.cycle = _cycle  # type: ignore[method-assign]
    try:
        cron.run_forever()
        assert not failures, (
            f"the leg's own premise failed inside the cycle run_forever swallows: {failures!r}"
        )
        assert readings, "the cycle never scraped the exempt endpoint it was running under"
        assert not refusals, f"the exempt bind was refused: {refusals!r}"
        assert summaries and summaries[0].generated == ["tenant-a"], (
            f"the run this leg counts invoices must have generated the tenant it seeded, got "
            f"{summaries}"
        )
        status, body = _get(DEFAULT_METRICS_PORT, path)
        assert status == 200, f"the exempt endpoint answered {status} after the run"
        after, types_after = _samples(body), _types(body)
    finally:
        _close_all(opened)
    before = readings[0]
    emitted = _emitted_names()
    missing = [name for name in emitted if name not in after]
    assert not missing, (
        f"{CRON_MODULE} emits {sorted(emitted)} and these never reached the exempt endpoint: "
        f"{missing} — the family the docs point at is not the family the wire carries"
    )
    wrong_type = [
        (name, types_after[name], emitted[name])
        for name in sorted(emitted)
        if types_after[name] != emitted[name]
    ]
    assert not wrong_type, (
        f"the exempt endpoint declares the wrong exposition type for {wrong_type} "
        "(name, served, emitted-by-code)"
    )
    counters = {name for name, kind in emitted.items() if kind == "counter"}
    assert counters, f"{CRON_MODULE} emits no counter at all: {sorted(emitted)}"
    moved = {name: after[name] - before.get(name, 0.0) for name in sorted(counters)}
    assert moved.get("invoice_cron_invoices_total") == 1.0, (
        f"one seeded tenant generated one invoice, and the endpoint's count moved {moved} — "
        "a run that does not reach the wire is a run nobody can see"
    )
    unmoved = {
        name: value for name, value in moved.items() if name != "invoice_cron_invoices_total"
    }
    assert all(value == 0.0 for value in unmoved.values()), (
        f"this run created no existing invoice, skipped no tenant and failed no tenant, yet "
        f"these counters moved on the wire: {unmoved} — the delta is not this run's"
    )
    assert after.get("invoice_cron_last_success_ts", 0.0) > 0.0, (
        "the gauge that tells a scrape the cron is alive is missing or zero at the exempt "
        f"endpoint: {after.get('invoice_cron_last_success_ts')!r}"
    )


def test_E4_no_deploy_carrier_claims_the_exempt_number_and_the_predicate_refuses() -> None:
    """The other half of 「没人抓它」 : nobody else was handed the number either.

    #232's L15 proves no job scrapes the exempt port and no deploy file starts the module.
    Neither reads compose's published ports, so a host mapping could take 9103 for another
    service while every existing gate stayed green — and on the host plane that is exactly
    where this cron would be started. The census is floored, and the predicate is driven
    from both sides with planted rows: an absence claim that has never refused anything is
    only evidence while the same scan still fires on a row written to be caught.
    """
    roster = _gate232()._roster()
    mappings = _gate232()._all_mappings()
    assert len(roster) >= 5, f"the roster census collapsed to {sorted(roster)}"
    assert len(mappings) >= 10, f"the compose mapping census collapsed to {len(mappings)} rows"
    claims = _claims_the_number(DEFAULT_METRICS_PORT, roster, mappings)
    assert claims == [], (
        f"{DEFAULT_METRICS_PORT} is claimed in the deploy plane ({claims}) while the docs call "
        "it the cron's exempt port — either the exemption moves or the docs do"
    )
    port = DEFAULT_METRICS_PORT
    neighbour = port + 1
    exempt_row = {"service": "node-exporter", "left": str(port), "right": "9101"}
    other_row = {"service": "node-exporter", "left": str(neighbour), "right": "9101"}
    exempt_job = {"planted": {"host": "node-exporter", "port": port, "path": "/metrics"}}
    fired = _claims_the_number(port, roster, [exempt_row])
    assert fired, (
        f"a compose mapping of {port} for another service read as no claim — the 「0 hits」 "
        "above would then be a census that cannot fire, not an absence"
    )
    scraped = _claims_the_number(port, exempt_job, mappings)
    assert scraped, (
        f"a roster job scraping {port} read as no claim, so E1's 「live AND unread」 clause "
        "is being carried by an empty predicate"
    )
    silent = _claims_the_number(port, roster, [other_row])
    assert not silent, (
        f"a mapping of {neighbour} fired the census for {port}: the predicate is not "
        f"comparing the number it was handed ({silent})"
    )
    print(
        f"[#450] E4 census: {len(roster)} jobs / ports "
        f"{sorted({int(i['port']) for i in roster.values()})} | {len(mappings)} compose "
        f"mappings | claims at {port}: {claims} | planted refusals: "
        f"{len(fired)}+{len(scraped)} fired, {len(silent)} silent"
    )
