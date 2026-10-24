"""#427 — the scrape roster's port numbers had never been occupied.

``infra/prometheus/prometheus.yml`` is a list of promises about sockets: ``worker:9100``
says a process answers its metrics path on 9100. Measured before this file existed
(``.scratch/m427_census.py``, over ``git ls-files``):

  9100 (worker)         named by 14 tracked files   bound by 0
  9101 (outbox-relay)   named by 13 tracked files   bound by 0
  9103 (invoice cron)   named by  8 tracked files   bound by 0

Every real bind in the repository hands the endpoint a kernel-chosen number — nine
``serve_metrics_in_thread(port=0)`` calls across the test tree, plus three production
sites whose port comes from an env knob that no test ever exercises at a socket. The
numbers themselves were only ever *compared*: #232's L3 checks the code's literal
default against the yaml's literal, L4 against compose's. Those are real pieces of
evidence, but nobody ever asked the OS whether the promised number is one this
endpoint occupies, answers at the promised path, and publishes the promised family.

The same blind spot covers the other half of a bind. Every ``server_address`` read in
the tree takes index ``[1]`` — the port — and none takes index ``[0]``, so the address
occupied has never been witnessed either. ``_resolve_bind_host()`` is compared to
``"127.0.0.1"`` / ``"0.0.0.0"`` as a *return value* (the
``test_bind_host_*`` cases in tests/unit/test_metrics_http.py), and no leg asks what
the socket ended up bound to.
Delete the ``host = _resolve_bind_host()`` line and the server binds every interface
while every existing gate stays green — a fail-open listener on a host run, and the
exact promise the roster depends on inside the container.

Case map (used by .scratch/m427_arms.py):
  L1 the bound population is every job the roster scrapes from OUR endpoint, floored,
     distinct, and disjoint from the third-party numbers
  L2 each rostered number is occupied and answers the roster's OWN path with our
     exposition — and with the marker this run registered when the bind is ours
  L3 the number handed in and the address handed in are the ones the socket occupies
     (kernel-chosen port, so this leg does not depend on who holds 9100)
  L4 both directions of the branch L2 takes when the OS refuses: our own endpoint
     holding the number reads as answered, a foreign exporter is charged
  L5 the endpoint's signature default is measured against the roster, and the module
     discloses the collision only while it exists
  L6 census: no tracked test occupies a number the roster declares for somebody else
  L7 the path handed to a rostered bind comes from the roster entry, not a retype
  L8 the census predicate, driven from both sides with planted rows and then with the
     shipped population

Honest boundary: the roster targets are compose service DNS names (``worker``,
``outbox-relay``); this plane is a host, so the legs address 127.0.0.1 and certify the
*number*, the *path* and the *exposition*, not the container's name resolution. When
something else already answers a rostered number — a ``start_local.ps1`` stack running
while the suite executes — L2/L4 read that incumbent's exposition instead of this
process's, which is what a scrape would see; they then cannot charge this run's marker
and say so. L3/L5/L6/L7 never bind a rostered number, so the plane-independent half of
the claim keeps being measured on every plane.

Landing this file also moved #232's classifier: its subscript branch labelled
``port=int(info["port"])`` a read of a knob named ``port``, which would have made
#232's tests/** exemption refuse the leg that occupies rostered numbers. The charge is
about the process environment, and #232's L2b now pins that in both directions.
"""

from __future__ import annotations

import ast
import errno
import functools
import http.client
import importlib.util
import inspect
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

from observability import metrics_http
from observability.metrics import incr, render_text
from observability.metrics_http import _resolve_bind_host, serve_metrics_in_thread

ROOT = Path(__file__).resolve().parents[2]
GATE_232 = ROOT / "tests" / "unit" / "test_listen_port_knobs_bind_the_scrape_roster.py"
GATE_220 = ROOT / "tests" / "unit" / "test_scrape_roster_binds_the_liveness_probes.py"
OWN_SOURCE = Path(__file__).resolve()

#: A metric name only this file emits, so a scrape read can tell whether the
#: exposition came from this process's registry or from somebody else's.
MARKER_PREFIX = "specproof_roster_leg"
#: Never registered anywhere: if this appears on the wire, the read is not reading
#: a registry at all.
ABSENT_MARKER = "specproof_roster_leg_absent_marker_total"

#: The phrase L5 requires in observability/metrics_http.py while its signature
#: default lands on a port the roster scrapes. English because the module docstring
#: is English; the sentence it quotes is the reader-facing disclosure itself.
_COLLISION_PHRASE = "omitting port="

#: A compose service name whose /metrics socket belongs to uvicorn, not to the
#: stdlib endpoint this file exercises.
_API_SERVER = "api/server.py"

_BIND_TIMEOUT = 5


# ──────────────────────── the roster, read from the gates that own it ────────────────────
@functools.cache
def _load(rel: Path, tag: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"sp_{tag}", rel)
    assert spec is not None and spec.loader is not None, f"cannot load {rel}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"sp_{tag}"] = module
    spec.loader.exec_module(module)
    return module


def _gate_232() -> Any:
    return _load(GATE_232, "gate232_for427")


def _roster() -> dict[str, dict[str, Any]]:
    """job -> host / port / path, through #232's own parser.

    Re-using that reader is the point: two parsers over one yaml drift, and #232's
    L14 exists to catch the drift. A second local parse would let this file keep
    binding a number the roster no longer declares.
    """
    return cast("dict[str, dict[str, Any]]", _gate_232()._roster())


def _our_endpoint_jobs() -> dict[str, dict[str, Any]]:
    """Jobs the roster scrapes that OUR stdlib endpoint serves.

    Derived from #232's knob table — a listen port read by a process of ours — and
    restricted to jobs the roster actually scrapes. ``api`` is excluded even though it
    serves ``specproof_*``: its socket belongs to uvicorn, and occupying that number
    from a test would certify our endpoint against somebody else's promise. L1 refuses
    if that exclusion stops being justified.
    """
    jobs = _roster()
    out = {job: jobs[job] for job in _gate_232()._LISTEN_PORT_KNOBS.values()}
    assert out, "_LISTEN_PORT_KNOBS declares no job at all"
    for job in out:
        assert job in jobs, f"the knob table serves {job!r}, which the roster does not scrape"
    return out


def _third_party_numbers() -> dict[str, int]:
    jobs = _roster()
    ours = set(_our_endpoint_jobs())
    out = {job: int(info["port"]) for job, info in jobs.items() if job not in ours}
    assert len(out) >= 3, f"third-party roster parse collapsed: {out}"
    assert _gate_232()._PATH_SOURCES["api"][0] == _API_SERVER, (
        f"api is no longer attributed to {_API_SERVER}, so this file's exclusion of "
        "it needs re-deriving instead of inheriting"
    )
    return out


def _family_prefix(job: str) -> str:
    """The metric family #220 declares this job publishes, without retyping it."""
    gate = _load(GATE_220, "gate220_for427")
    prefixes = [prefix for prefix, owners in gate._FAMILY_OWNERS.items() if job in owners]
    assert prefixes, f"#220 declares no metric family served by {job}"
    assert len(prefixes) == 1, f"{job} maps to several families: {sorted(prefixes)}"
    return cast("str", prefixes[0])


# ───────────────────────────────── bind machinery ─────────────────────────────────
def _free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    return port


def _code(exc: OSError) -> int:
    return int(getattr(exc, "winerror", None) or exc.errno or 0)


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=_BIND_TIMEOUT)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8")
    finally:
        conn.close()


@dataclass
class _Answered:
    """What the roster's promise looks like from this host.

    ``bound`` — this process occupies the number, so the read-back fields are what the
    OS gave the socket and this run's marker must be on the wire. ``incumbent`` — the
    OS refused because something already answers it (#284 made a live collision
    refuse), so the body is that holder's exposition: the promise holds, this
    process's registry is not what a scrape reads, and the leg says which it got.
    """

    port: int
    path: str
    kind: str
    body: str
    server: ThreadingHTTPServer | None = None
    occupied_port: int | None = None
    occupied_address: str | None = None

    def release(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()


def _occupy(port: int, path: str) -> _Answered:
    """Hand ``port`` to the endpoint the way the shipped call sites do — port only.

    Production calls ``serve_metrics_in_thread(port=int(os.getenv(...)))`` and lets the
    module resolve the address, so no leg here passes a host; L3 and L5 say which half
    of that shape is being certified.
    """
    try:
        server = serve_metrics_in_thread(port=port)
    except OSError as exc:
        code = _code(exc)
        assert code == errno.EADDRINUSE, (
            f"binding the roster's port {port} failed with code {code}, not "
            f"EADDRINUSE ({errno.EADDRINUSE}): {exc!r}. A refusal for any other reason "
            "— an unroutable address, a socket-option conflict — says nothing about "
            "whether the number is occupied."
        )
        status, body = _get(port, path)
        assert status == 200, (
            f"port {port} refused a bind, so something answers it, yet GET {path} "
            f"returned {status}. The roster's promise is not 'a socket holds the "
            "number' but 'that number serves the metrics path'."
        )
        return _Answered(port, path, "incumbent", body)
    assert server is not None
    status, body = _get(port, path)
    assert status == 200, (
        f"this process bound {port} and the roster scrapes {path} there, but the "
        f"endpoint answered {status}: {body[:120]!r}"
    )
    return _Answered(
        port,
        path,
        "bound",
        body,
        server,
        int(server.server_address[1]),
        str(server.server_address[0]),
    )


def _require_our_exposition(read: _Answered, marker: str, family: str) -> None:
    """Charge the body with the family the roster expects from that number."""
    assert f"# TYPE {family}" in read.body, (
        f"GET {read.path} on {read.port} ({read.kind}) published no family the roster "
        f"declares for that job ({family!r}): {read.body[:120]!r}. #220 says this job "
        "is the provider of that family; an alert rule reading it is silent from here."
    )
    assert ABSENT_MARKER not in read.body, (
        f"{ABSENT_MARKER} is registered nowhere, yet it came back from {read.port} — "
        "the read is not reading a registry"
    )
    if read.kind == "bound":
        assert marker in render_text(), (
            f"{marker} is missing from this process's own registry, so the wire read "
            "could not tell our exposition from a constant"
        )
        assert f"{marker} " in read.body, (
            f"this process occupies {read.port} yet its own marker never reached the "
            f"wire: {read.body[:160]!r}"
        )


# ─────────────────────────── a holder that is not ours ───────────────────────────
class _ForeignHandler(BaseHTTPRequestHandler):
    """A live 200 on the metrics path whose body is somebody else's format."""

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        body = b"# HELP node_exporter_build_info A foreign exporter.\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence: this fixture is not the subject of any read."""


def _serve_foreign(port: int) -> ThreadingHTTPServer:
    """Run the foreign holder the way the shipped endpoint runs: serve_forever in a thread.

    Measured the hard way — a bare ``ThreadingHTTPServer(...)`` that is never
    ``serve_forever``-ed answers nothing (only the listen backlog accepts the connect,
    so the read times out) and then deadlocks in teardown: ``BaseServer.shutdown()``
    waits on the ``__is_shut_down`` event, which only that loop ever sets, so the
    suite hangs with no failure to read. The thread is what makes both halves work.
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _ForeignHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="foreign-metrics").start()
    return server


# ───────────────────────────────────────── legs ─────────────────────────────────────────
def test_L1_the_bound_population_is_our_endpoint_jobs_and_no_others() -> None:
    """Who this file may occupy a number for, read from the two roster gates.

    A floor, not a loop: if either parse collapses to nothing, every leg below would
    pass on an empty population and the file would still report a clean roster.
    """
    ours = _our_endpoint_jobs()
    assert len(ours) >= 2, f"our endpoint serves only {sorted(ours)} roster jobs"
    ports = {job: int(info["port"]) for job, info in ours.items()}
    assert len(set(ports.values())) == len(ports), (
        f"two jobs scraped by name share one number {ports} — whichever process "
        "binds it first, one job reads the other's metrics"
    )
    third = _third_party_numbers()
    clash = {job: port for job, port in third.items() if port in set(ports.values())}
    assert not clash, (
        f"our endpoint's numbers collide with third-party jobs {clash}: a leg here "
        "would then be certifying somebody else's socket"
    )
    markers = {f"{MARKER_PREFIX}_{job.replace('-', '_')}_marker_total" for job in ours}
    assert len(markers) == len(ours), f"per-job markers collapse: {sorted(markers)}"


def test_L2_a_rostered_number_is_occupied_and_answers_its_own_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first leg in this repository that binds a number the roster declares.

    The number comes from ``infra/prometheus/prometheus.yml`` through #232's parser,
    the path from the same entry, the family from #220's owner table — none of them
    copied into this file.
    """
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    ours = _our_endpoint_jobs()
    for job, info in sorted(ours.items()):
        marker = f"{MARKER_PREFIX}_{job.replace('-', '_')}_marker_total"
        incr(marker[len("specproof_") :])
        read = _occupy(int(info["port"]), str(info["path"]))
        try:
            _require_our_exposition(read, marker, _family_prefix(job))
            if read.kind == "bound":
                assert f"# TYPE {marker} counter" in read.body, (
                    f"{job}: the counter this run registered did not reach {job}'s "
                    f"scrape port with its TYPE line: {read.body[:160]!r}"
                )
                assert read.occupied_port == int(info["port"]), (
                    f"{job}: the roster declares {info['port']}, the endpoint was asked "
                    f"for it, and the socket occupies {read.occupied_port} — Prometheus "
                    "scrapes the declared number and finds nothing"
                )
                assert read.occupied_address == _resolve_bind_host(), (
                    f"{job}: the endpoint bound {read.occupied_address!r} while "
                    f"_resolve_bind_host() answers {_resolve_bind_host()!r}, so the "
                    "address half of the promise never reaches the socket"
                )
        finally:
            read.release()


def test_L3_the_handed_in_number_and_address_are_the_ones_occupied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plane-independent half: nothing here depends on who holds 9100.

    A kernel-chosen number, a knob-supplied address, both halves read back off the
    socket. This is the leg that dies when the endpoint stops honouring what it is
    handed — ``host = _resolve_bind_host()`` removed, the ``port`` dropped, or a ``0``
    substituted for either — on every platform the suite runs on.
    """
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    numbers = {int(info["port"]) for info in _roster().values()}
    port = _free_port()
    assert port not in numbers, f"the OS handed out a rostered number: {port}"
    read = _occupy(port, "/metrics")
    try:
        assert read.kind == "bound", (
            f"a freshly released number {port} came back as {read.kind}; the "
            "read-back assertions below would certify nothing"
        )
        assert read.occupied_port == port, (
            f"asked the endpoint for {port}, it occupies {read.occupied_port} — the "
            "port argument is not the number the socket holds"
        )
        assert read.occupied_address == "127.0.0.1", (
            f"METRICS_BIND_HOST=127.0.0.1 is set and the resolver returns it, yet the "
            f"socket is bound to {read.occupied_address!r}: the knob is compared as a "
            "return value in tests/unit/test_metrics_http.py but never reaches a bind"
        )
    finally:
        read.release()


def test_L4_a_held_number_is_answered_by_us_or_it_is_charged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both directions of the branch L2 takes when the OS refuses.

    That branch is a promise about a socket this file may not own, so it needs its own
    witness. Driven with our own endpoint holding a rostered number it must read as
    answered; driven with a foreign exporter on the same path it must be charged.
    Without the first the branch is unreachable prose; without the second it accepts
    any 200.
    """
    monkeypatch.setenv("METRICS_BIND_HOST", "127.0.0.1")
    ours = _our_endpoint_jobs()
    job, info = sorted(ours.items())[0]
    marker = f"{MARKER_PREFIX}_{job.replace('-', '_')}_marker_total"
    incr(marker[len("specproof_") :])
    family = _family_prefix(job)

    try:
        owner = serve_metrics_in_thread(port=int(info["port"]))
    except OSError as exc:
        assert _code(exc) == errno.EADDRINUSE, exc
        # Somebody else already answers it on this host, so the refusal branch is
        # witnessed by the world rather than by a fixture. The charge that still
        # belongs to this leg is that the number serves OUR exposition.
        _require_our_exposition(_occupy(int(info["port"]), str(info["path"])), marker, family)
    else:
        try:
            held = _occupy(int(info["port"]), str(info["path"]))
            try:
                assert held.kind == "incumbent", (
                    f"the endpoint let a second listener take {info['port']} while "
                    "another was answering it — #284's exclusive bind has stopped "
                    "refusing, and the read below is the squatter's"
                )
                _require_our_exposition(held, marker, family)
            finally:
                held.release()
        finally:
            owner.shutdown()
            owner.server_close()

    foreign_port = _free_port()
    foreign = _serve_foreign(foreign_port)
    try:
        status, body = _get(foreign_port, "/metrics")
        assert status == 200, f"the foreign fixture itself did not answer: {status}"
        with pytest.raises(AssertionError) as charged:
            _require_our_exposition(
                _Answered(foreign_port, "/metrics", "incumbent", body), marker, family
            )
        assert family in str(charged.value), (
            f"the charge does not name the family it looked for: {charged.value}"
        )
    finally:
        foreign.shutdown()
        foreign.server_close()


def test_L5_the_endpoints_default_is_measured_against_the_roster_and_disclosed() -> None:
    """The signature default is a number, and a shipped call site may omit the keyword.

    ``serve_metrics_in_thread()`` without ``port=`` is what a new listener gets.
    Measured against the roster rather than against a literal: the default and
    ``worker:9100`` are the same number today, so a caller that forgets the keyword
    silently claims a scrape endpoint. If either value moves, the module's sentence has
    to move with it rather than stay behind as a story about a collision nobody can
    cause any more.
    """
    default = inspect.signature(serve_metrics_in_thread).parameters["port"].default
    assert isinstance(default, int), f"the endpoint's port default is {default!r}"
    jobs = {job: int(info["port"]) for job, info in _roster().items()}
    collides = sorted(job for job, port in jobs.items() if port == default)
    doc = inspect.getdoc(metrics_http) or ""
    if collides:
        assert _COLLISION_PHRASE in doc, (
            f"serve_metrics_in_thread's own default {default} is the port the roster "
            f"scrapes for {collides}, so a caller that omits the keyword claims a "
            f"scrape endpoint. The module docstring does not say {_COLLISION_PHRASE!r}."
        )
        for job in collides:
            assert job in doc, (
                f"the disclosure must name the job whose number the default collides "
                f"with ({job!r}); the docstring ends: {doc[-220:]!r}"
            )
    else:
        assert _COLLISION_PHRASE not in doc, (
            f"the default {default} matches no rostered port any more, so the "
            "collision sentence is stale — delete it instead of warning about a "
            "collision nobody can cause"
        )


def _test_files() -> list[str]:
    """Tracked test files — the population L6's census reads, and the one L8 drives."""
    listing = subprocess.run(
        ["git", "ls-files", "tests"], cwd=ROOT, capture_output=True, check=True, timeout=180
    ).stdout.decode("utf-8")
    files = [line for line in listing.splitlines() if line.endswith(".py")]
    assert len(files) > 100, f"test census collapsed: {len(files)} files"
    return files


def _constant_port_rows(files: list[str]) -> list[tuple[str, int, int]]:
    """``(file, line, port)`` for every literal port a tracked test hands the endpoint.

    Feed the parser the bytes, not a hand-decoded string: a tracked test file starts
    with a UTF-8 BOM (tests/unit/test_eval_resume_reuses_measured_cases.py), which
    Python's own source decoder accepts while ``read_bytes().decode("utf-8")`` keeps it
    as U+FEFF and raises SyntaxError. A census that dies on one file's encoding reports
    nothing about the other 442.
    """
    rows: list[tuple[str, int, int]] = []
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_bytes())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name != "serve_metrics_in_thread":
                continue
            for keyword in node.keywords:
                if keyword.arg != "port":
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    rows.append((rel, node.lineno, value.value))
    return rows


def _refused(
    rows: list[tuple[str, int, int]], *, third: set[int], ours: set[int]
) -> tuple[list[tuple[str, int, int]], list[tuple[str, int, int]]]:
    """The two refusals L6 makes, over one row parse: whose number, and whether it is fixed.

    Shared with L8 so the planted rows drive the predicate the shipped census drives —
    an absence claim nobody has watched refuse anything is a green that means nothing.
    """
    occupied = [row for row in rows if row[2] in third]
    stray = [row for row in rows if row[2] != 0 and row[2] not in ours]
    return occupied, stray


def test_L6_no_tracked_test_occupies_a_number_the_roster_declares_for_others() -> None:
    """A bind of ``prometheus:9090`` from our own suite would green-light a lie.

    Census over the tracked test tree keyed on the call shape: every constant port
    handed to the endpoint must be 0 (kernel-chosen) or a number the roster scrapes
    from our endpoint. The floor keeps an empty scan from reading as clean; L8 drives
    the same predicate with planted rows, because nothing in the tree today gives it
    anything to refuse.
    """
    third = set(_third_party_numbers().values())
    ours = {int(info["port"]) for info in _our_endpoint_jobs().values()}
    rows = _constant_port_rows(_test_files())
    assert len(rows) >= 5, (
        f"the census saw only {rows}; an empty scan cannot certify that "
        "nobody occupies a third-party number"
    )
    occupied, stray = _refused(rows, third=third, ours=ours)
    assert not occupied, (
        f"these test binds land on a number the roster declares for a process this repo "
        f"does not write ({sorted(_third_party_numbers().items())}): {occupied}. A scrape "
        "promise about node_exporter, RabbitMQ or Prometheus cannot be witnessed by "
        "occupying the port ourselves — that is a green that means the opposite."
    )
    assert not stray, (
        f"a test binds a fixed port that is neither kernel-chosen nor one of our "
        f"rostered numbers: {stray}. A number outside the roster still collides with "
        "whatever else runs on the plane and makes the suite depend on the host."
    )


def test_L7_a_rostered_bind_is_given_the_rosters_own_path() -> None:
    """``/metrics`` in this file would be a copy, and a copy can go stale.

    If the yaml ever declares another ``metrics_path`` for the worker, the leg has to
    scrape that one; a leg hard-coded to ``/metrics`` keeps passing while every real
    scrape 404s, which is exactly the failure #220's R10 was written against. That is
    not a hypothetical here: the roster the legs read already carries more than one
    path, so the field is load-bearing in this very file.

    The claim is read off the syntax tree, not off a text search. ``ast.unparse``
    re-quotes ``info["path"]`` as ``info['path']``, so a byte needle for the source's
    own spelling is green on a leg that still derives and red on nothing; the shape —
    a subscript keyed by the literal ``path``, on the entry the loop pulls from #232's
    parser — is what carries.
    """
    tree = ast.parse(OWN_SOURCE.read_bytes())
    legs = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_L2")
    ]
    assert len(legs) == 1, f"expected exactly one L2 leg at module level, found {len(legs)}"
    leg = legs[0]

    hard_coded = [
        node.value
        for node in ast.walk(leg)
        if isinstance(node, ast.Constant) and node.value == "/metrics"
    ]
    assert not hard_coded, (
        "L2 carries a hard-coded metrics path, so a roster that changes its "
        "metrics_path keeps reading green here and 404s in the deployment"
    )
    assert any(
        isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_our_endpoint_jobs"
        for node in ast.walk(leg)
    ), (
        "L2 no longer pulls the entries it binds from #232's roster parser, so the "
        "port and path it scrapes could be a local table that drifts from the yaml"
    )

    def _unwrap(node: ast.expr) -> ast.expr:
        """Strip the coercions a call site wraps a derived value in (str/int/fspath)."""
        while isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
            node = node.args[0]
        return node

    calls = [
        node
        for node in ast.walk(leg)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_occupy"
    ]
    assert calls, "L2 makes no _occupy call, so there is no rostered bind left to audit"
    for call in calls:
        assert len(call.args) >= 2, f"L2 calls _occupy without a path argument: {ast.dump(call)}"
        path_arg = _unwrap(call.args[1])
        assert isinstance(path_arg, ast.Subscript), (
            f"L2 hands _occupy a path that is not read off the roster entry "
            f"({ast.dump(path_arg)}); a literal or a local table is a copy that can go "
            "stale while every real scrape 404s"
        )
        key = path_arg.slice
        assert isinstance(key, ast.Constant) and key.value == "path", (
            f"L2 scrapes {ast.dump(key)} from the roster entry instead of its 'path', "
            f"so the leg is not reading the path the roster declares: {ast.dump(call)}"
        )

    paths = {str(info["path"]) for info in _roster().values()}
    assert len(paths) >= 2, (
        f"the roster carries one metrics path for every job ({paths}), so this leg's "
        "claim that the path must be derived would be guarding a field nobody varies"
    )
    declared = {str(info["path"]) for info in _our_endpoint_jobs().values()}
    assert declared, "no rostered path to compare against"


# ───────────────────────────────────────────── L8 ─────────────────────────────────────────────
def test_L8_the_census_charge_refuses_a_foreign_number_and_accepts_ours() -> None:
    """L6 certifies an absence, so its predicate has to be watched refusing something.

    Nothing in the tracked tree today hands the endpoint another process's number or an
    off-roster fixed one, so both of L6's asserts run against an empty result by default:
    a mutation that blinds the census — a dropped keyword match, a flipped comparison —
    reports exactly the green the honest reading reports. The planted rows drive the very
    function L6 trusts, from both sides: the number the roster declares for somebody else
    comes back charged, our own rostered number and the kernel-chosen ``0`` come back
    clean, and a fixed number outside the roster is caught by the second refusal only.
    The shipped census then goes through the same call, which is what ties the planted
    behaviour to the population that carries the promise.
    """
    third_map = _third_party_numbers()
    third = set(third_map.values())
    ours = {int(info["port"]) for info in _our_endpoint_jobs().values()}
    assert third and ours and not third & ours, (
        f"a planted row only means something while the two populations stay disjoint: "
        f"third={sorted(third)}, ours={sorted(ours)}"
    )
    foreign = sorted(third)[0]
    rostered = sorted(ours)[0]
    planted = [
        ("planted_foreign_row.py", 1, foreign),
        ("planted_our_row.py", 2, rostered),
        ("planted_kernel_row.py", 3, 0),
    ]
    occupied, stray = _refused(planted, third=third, ours=ours)
    assert occupied == [planted[0]], (
        f"the charge did not single out the row that binds {foreign}, the number the "
        f"roster declares for a process this repo does not write: occupied={occupied}, "
        f"stray={stray}"
    )
    assert stray == [planted[0]], (
        "a third party's number is by definition not one of ours, so the stray refusal "
        f"names it too ({stray}) — but nothing else may sit in that list"
    )
    accepted = _refused(planted[1:], third=third, ours=ours)
    assert accepted == ([], []), (
        f"the leg's own binds are charged ({accepted[0]}, {accepted[1]}): a rostered "
        "number of ours and the kernel-chosen 0 are the two shapes L6 must accept, "
        "because L2 and L4 occupy exactly those"
    )
    off = _free_port()
    assert off not in third | ours, f"the OS handed out a rostered number: {off}"
    off_row = ("planted_offroster_row.py", 4, off)
    occupied_off, stray_off = _refused([off_row], third=third, ours=ours)
    assert occupied_off == [] and stray_off == [off_row], (
        f"a fixed number that belongs to nobody is not caught by the second refusal "
        f"alone: occupied={occupied_off}, stray={stray_off}"
    )
    rows = _constant_port_rows(_test_files())
    shipped = _refused(rows, third=third, ours=ours)
    assert shipped == ([], []), (
        f"the shipped census drives the same predicate to a refusal L6 did not report: {shipped}"
    )
