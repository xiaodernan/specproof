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
  L6 census: this file is the single owner of the verdict on what a TEST may bind. It
     resolves every ``serve_metrics_in_thread`` port expression in ``git ls-files tests``
     to a provenance (env / fixed / default / blind / roster / free) and refuses four
     moving shapes: an environment read, a number from nowhere readable, a number the
     roster declares for a third party, and a number the roster scrapes for nobody
  L7 the path handed to a rostered bind comes from the roster entry, not a retype
  L8 the owner's predicate, driven from both sides — 13 planted sources with exact
     bucket expectations, then the shipped population — plus the parity clause that
     #232's exempt rows and this census enumerate the same binds

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

The ownership moved here in the same arc. #232's L2 used to judge its own tests/**
carve-out with that literal classifier, and measured on the shipped tree it is blind four
times over — the two ``port=_free_port()`` binds and this file's two
``port=int(info["port"])`` binds all read as ``other`` (``.scratch/m451_parity.log``,
13 exempt rows vs 13 rows carrying a ``port=`` keyword), so a test that reached a scrape
number through a name was invisible to the one gate that carved tests out. L2 now loads
this gate and asks it: a row the two censuses enumerate differently reds, a shallow
``env:`` charge this census does not confirm reds, and an owner verdict of ``env`` or
``blind`` reds. One predicate, judged once, referenced from the carve-out that depends on
it. The shipped read is 9 ``fixed(0)`` + 2 ``free`` + 2 ``roster`` with no refusal
(``.scratch/m451_census_check.log``).

The resolver is file-local by construction, and that is the safe direction: a number fed
in from another module's constant has no readable source here, so it lands ``blind`` and
gets refused rather than waved through. Every shape the resolver treats as admissible is
named in L8's planted list, and a shape it cannot read is a red the next author has to
resolve by hand.
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


# ─────────────────────── the one predicate that judges every test bind ───────────────────────
#: The call the census keys on: the only function in this repo that opens a scrape socket.
_METRICS_CALL = "serve_metrics_in_thread"

#: Calls whose result IS the roster. A ``["port"]`` read off a name bound from one of them
#: is a number the roster declares for our endpoint, so it is the same number L2 occupies.
_ROSTER_CALLS = frozenset({"_our_endpoint_jobs", "_roster", "_gate_232", "_gate232"})

#: Where a handed-in number comes from, sharpest charge first. ``env`` would move the
#: endpoint with whatever the host's process environment says; ``fixed`` carries a number
#: that then has to be checked against the roster; ``default`` is the signature's own
#: number, which a call without ``port=`` takes; ``blind`` is a number no census can read;
#: ``roster`` and ``free`` are the two provenances that do not move anybody's endpoint.
_PROVENANCE_ORDER = ("env", "fixed", "default", "blind", "roster", "free")

#: Provenances that carry a checkable number.
_NUMERIC_KINDS = frozenset({"fixed", "default"})


@dataclass(frozen=True)
class PortSite:
    """One test's bind of the metrics endpoint, and the provenance of its number."""

    file: str
    line: int
    kind: str
    detail: str
    numbers: frozenset[int] = frozenset()

    def tag(self) -> str:
        return f"{self.file}:{self.line} {self.kind} ({self.detail})"


def _call_name(node: ast.Call) -> str | None:
    """The bare callee of ``f(...)`` or ``mod.f(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _unwrap(node: ast.expr) -> ast.expr:
    """Strip the coercions and container reads a call site wraps a derived number in.

    ``int(info["port"])`` is still a roster read, and ``sorted(...)[-1]`` still arrives from
    the same place; charging the wrapper instead of what it wraps would make the census
    refuse its own legs.
    """
    while True:
        if isinstance(node, ast.Call) and not node.keywords and len(node.args) <= 1:
            name = _call_name(node)
            if name in {"int", "str", "fspath", "sorted"}:
                if node.args:
                    node = node.args[0]
                    continue
                break
            if name in {"values", "items", "keys"} and isinstance(node.func, ast.Attribute):
                node = node.func.value
                continue
            break
        if isinstance(node, ast.Attribute) and node.attr in {"values", "items", "keys"}:
            node = node.value
            continue
        break
    return node


def _binding_names(node: ast.expr) -> list[str]:
    """Names an assignment or loop target binds, unpacking the tuple spellings legs use."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [child.id for child in node.elts if isinstance(child, ast.Name)]
    return []


def _function_bodies(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }


def _parameter_names(fn: ast.FunctionDef) -> list[str]:
    return [arg.arg for arg in [*fn.args.posonlyargs, *fn.args.args]]


def _probe_helpers(tree: ast.Module) -> set[str]:
    """File-local functions that ask the kernel for a number instead of naming one.

    Both halves are required: a function that binds ``0`` and never reads the socket back
    hands out a number it does not know, and one that reads ``getsockname`` without ever
    binding 0 read somebody else's socket. Either alone would let a leg that really picked
    a fixed number certify itself as kernel-chosen.
    """
    out: set[str] = set()
    for name, fn in _function_bodies(tree).items():
        binds_zero = any(
            isinstance(node, ast.Call)
            and _call_name(node) == "bind"
            and any(
                isinstance(sub, ast.Constant) and sub.value == 0
                for arg in node.args
                for sub in ast.walk(arg)
            )
            for node in ast.walk(fn)
        )
        reads_back = any(
            isinstance(node, ast.Attribute) and node.attr == "getsockname"
            for node in ast.walk(fn)
        )
        if binds_zero and reads_back:
            out.add(name)
    return out


def _roster_holders(tree: ast.Module) -> set[str]:
    """Names this file binds from the roster parser, transitively.

    ``for info in _our_endpoint_jobs().values()`` binds ``info``; ``ours = _roster()`` then
    ``for job, info in sorted(ours.items())`` binds ``info`` through ``ours``. Run to a
    fixpoint because the second spelling only becomes readable after the first.
    """
    out: set[str] = set()

    def from_roster(node: ast.expr) -> bool:
        inner = _unwrap(node)
        if isinstance(inner, ast.Call):
            return _call_name(inner) in _ROSTER_CALLS
        return isinstance(inner, ast.Name) and inner.id in out

    for _round in range(4):
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and from_roster(node.iter):
                names = _binding_names(node.target)
            elif isinstance(node, ast.Assign) and from_roster(node.value):
                names = [name for target in node.targets for name in _binding_names(target)]
            else:
                continue
            for name in names:
                if name not in out:
                    out.add(name)
                    found = True
        if not found:
            break
    return out


def _fold_int(node: ast.expr) -> int | None:
    """Fold the arithmetic spellings a port can be written with; None means unreadable."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(
        node.value, bool
    ):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _fold_int(node.operand)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp):
        left, right = _fold_int(node.left), _fold_int(node.right)
        if left is None or right is None or right == 0:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
    return None


@functools.cache
def _port_context(tree: ast.Module) -> dict[str, Any]:
    """Everything a name lookup needs about one file, computed once per file.

    The first version of this resolver rebuilt it per site and resolved a scope by walking
    the whole tree each time: the census over 458 tracked test files cost 24.9s, more than
    every socket leg in this file together (``.scratch/m451_timing.log``). One pass, and
    scopes read off line ranges, brings the same verdicts in 0.41s.
    """
    functions = _function_bodies(tree)
    spans = [
        (fn.lineno, fn.end_lineno or fn.lineno, fn.name) for fn in functions.values()
    ]

    def scope_of(node: ast.AST) -> str | None:
        """The innermost function whose line range contains ``node``; None at module level."""
        line = getattr(node, "lineno", -1)
        best: tuple[int, str] | None = None
        for start, stop, name in spans:
            if start <= line <= stop and (best is None or stop - start < best[0]):
                best = (stop - start, name)
        return best[1] if best else None

    calls_by_name: dict[str, list[ast.Call]] = {}
    bindings: list[tuple[str | None, str, ast.expr, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = _call_name(node)
            if called is not None:
                calls_by_name.setdefault(called, []).append(node)
        # ``ast.comprehension`` carries no lineno, so ``scope_of`` on it fell through to
        # module level: every ``for job, port in …`` target became a source any function
        # could reach by the fallback below. The target node sits on the comprehension's
        # own line, so asking it names the function that actually owns the binding.
        keyed = node.target if isinstance(node, ast.comprehension) else node
        holder = scope_of(keyed)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for name in _binding_names(target):
                    if node.value is not None:
                        bindings.append((holder, name, node.value, scope_of(node.value)))
        elif isinstance(node, (ast.For, ast.comprehension)):
            iterable = node.iter
            for name in _binding_names(node.target):
                bindings.append((holder, name, iterable, holder))

    local: dict[tuple[str | None, str], list[tuple[ast.expr, str | None]]] = {}
    for scope, name, value, value_scope in bindings:
        local.setdefault((scope, name), []).append((value, value_scope))
    params: dict[tuple[str, str], list[tuple[ast.expr, str | None]]] = {}
    for name, fn in functions.items():
        for position, arg in enumerate(_parameter_names(fn)):
            for call in calls_by_name.get(name, []):
                call_scope = scope_of(call)
                if position < len(call.args):
                    params.setdefault((name, arg), []).append((call.args[position], call_scope))
                for keyword in call.keywords:
                    if keyword.arg == arg:
                        params.setdefault((name, arg), []).append((keyword.value, call_scope))
    return {
        "tree": tree,
        "scope_of": scope_of,
        "functions": functions,
        "helpers": _probe_helpers(tree),
        "roster": _roster_holders(tree),
        "local": local,
        "params": params,
    }


def _sources_of(
    ctx: dict[str, Any], name: str, scope: str | None
) -> list[tuple[str, ast.expr, str | None]]:
    """Where one name's value can arrive from, inside the scope that reads it.

    A file-global scan of ``port`` is wrong: this repo's legs reuse one parameter name in
    several helpers, so reading ``_occupy``'s parameter wandered into ``_get``'s call sites
    and reported ``blind`` for four sites that are each perfectly readable. A parameter
    reads only its own function's call sites, a local only assignments in that function,
    and a name the function never binds reads module level — Python's own scoping, which is
    what makes the verdict per site rather than per file.
    """
    out: list[tuple[str, ast.expr, str | None]] = []
    params: dict = ctx["params"]
    local: dict = ctx["local"]
    if scope is not None:
        for value, value_scope in params.get((scope, name), ()):
            out.append((f"param:{scope}/{name}", value, value_scope))
    for value, value_scope in local.get((scope, name), ()):
        out.append((f"local:{scope}/{name}", value, value_scope))
    if out or scope is None:
        return out
    for value, value_scope in local.get((None, name), ()):
        out.append((f"global:{name}", value, value_scope))
    return out


def _is_env_read(node: ast.expr) -> str | None:
    """The knob name if this expression reaches the process environment, else None."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_name(sub) == "getenv":
            first = sub.args[0] if sub.args else None
            return str(first.value) if isinstance(first, ast.Constant) else "?"
        if (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.slice, ast.Constant)
            and isinstance(sub.slice.value, str)
            and (
                (isinstance(sub.value, ast.Attribute) and sub.value.attr == "environ")
                or (isinstance(sub.value, ast.Name) and sub.value.id == "environ")
            )
        ):
            return str(sub.slice.value)
    return None


def _resolve_port(
    node: ast.expr,
    scope: str | None,
    ctx: dict[str, Any],
    path: frozenset[str] = frozenset(),
    depth: int = 0,
) -> list[tuple[str, str, frozenset[int]]]:
    """Every verdict the expression can reach, one per readable source.

    Multiple sources is the honest answer, not an ambiguity: a helper parameter fed both a
    kernel probe and a literal really can move the endpoint with the literal, so the caller
    charges the sharpest of them and lists every number that kind reached.
    """
    node = _unwrap(node)
    if depth > 8:
        return []
    knob = _is_env_read(node)
    if knob is not None:
        return [("env", knob, frozenset())]
    helpers: set[str] = ctx["helpers"]
    if scope in helpers and any(
        isinstance(sub, ast.Attribute) and sub.attr == "getsockname" for sub in ast.walk(node)
    ):
        return [("free", scope or "", frozenset())]
    folded = _fold_int(node)
    if folded is not None:
        return [("fixed", str(folded), frozenset({folded}))]
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        base = node.value
        base_name = base.id if isinstance(base, ast.Name) else None
        if node.slice.value == "port" and base_name in ctx["roster"]:
            return [("roster", f"{base_name}['port']", frozenset())]
        return [("blind", f"subscript on {ast.unparse(base)!r}", frozenset())]
    if isinstance(node, ast.Call):
        name = _call_name(node) or ""
        body = ctx["functions"].get(name)
        if body is None:
            return [("blind", f"call {name}() outside this file", frozenset())]
        if f"call:{name}" in path:
            return []
        returns = [
            row.value for row in ast.walk(body) if isinstance(row, ast.Return) and row.value
        ]
        out = [
            verdict
            for value in returns
            for verdict in _resolve_port(value, name, ctx, path | {f"call:{name}"}, depth + 1)
        ]
        return out or [("blind", f"{name}() returns nothing readable", frozenset())]
    if isinstance(node, ast.Name):
        out = [
            verdict
            for key, value, value_scope in _sources_of(ctx, node.id, scope)
            if key not in path
            for verdict in _resolve_port(value, value_scope, ctx, path | {key}, depth + 1)
        ]
        return out or [("blind", f"name {node.id} has no readable source here", frozenset())]
    return [("blind", f"{type(node).__name__} is not a nameable port", frozenset())]


def _port_provenance(
    tree: ast.Module, expr: ast.expr, scope: str | None
) -> tuple[str, str, frozenset[int]]:
    """One charge per site: the sharpest verdict, with every number that kind reached.

    Reporting only the first verdict let a site fed both ``0`` and a third party's number
    read as the harmless one.
    """
    verdicts = _resolve_port(expr, scope, _port_context(tree))
    if not verdicts:
        return "blind", "no readable source at any depth", frozenset()
    verdicts.sort(key=lambda row: _PROVENANCE_ORDER.index(row[0]))
    kind, detail, _ = verdicts[0]
    numbers = frozenset().union(*(row[2] for row in verdicts if row[0] == kind))
    return kind, detail, numbers


def _endpoint_default() -> int:
    """The signature's own port, which a call without ``port=`` takes."""
    default = inspect.signature(serve_metrics_in_thread).parameters["port"].default
    assert isinstance(default, int), f"the endpoint's port default is {default!r}"
    return default


def _file_port_sites(rel: str, source: bytes) -> list[PortSite]:
    """Every metrics-server call in one file, each with the provenance of its number.

    A call that spells no port at all is a site too, and is charged with the signature's
    default: that is the hole the old literal-only census could not see, because the number
    was never written at the call site.
    """
    tree = ast.parse(source)
    ctx = _port_context(tree)
    out: list[PortSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != _METRICS_CALL:
            continue
        keyword = next((kw for kw in node.keywords if kw.arg == "port"), None)
        if keyword is not None:
            kind, detail, numbers = _port_provenance(tree, keyword.value, ctx["scope_of"](node))
        elif len(node.args) >= 2:
            kind, detail, numbers = _port_provenance(tree, node.args[1], ctx["scope_of"](node))
        else:
            kind, detail, numbers = "default", "the signature's port", frozenset(
                {_endpoint_default()}
            )
        out.append(PortSite(rel, node.lineno, kind, detail, numbers))
    return out


@functools.cache
def _test_port_sites() -> tuple[PortSite, ...]:
    """The census: every port a tracked test hands the metrics endpoint, and its source.

    Cached because L6, L8 and #232's L2 all read the same population; an uncached version
    re-parses 458 files per reader (``.scratch/m451_timing.log``).
    """
    rows: list[PortSite] = []
    for rel in _test_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if _METRICS_CALL.encode() not in raw:
            continue
        # Parse the bytes, not a hand-decoded string: a tracked test file starts with a
        # UTF-8 BOM (tests/unit/test_eval_resume_reuses_measured_cases.py), which Python's
        # own source decoder accepts while ``read_bytes().decode("utf-8")`` keeps it as
        # U+FEFF and raises SyntaxError. A census that dies on one file's encoding reports
        # nothing about the other 457.
        rows.extend(_file_port_sites(rel, raw))
    return tuple(sorted(rows, key=lambda site: (site.file, site.line)))


def _planted_sites(name: str, source: str) -> list[PortSite]:
    """Drive the census predicate with a source the tracked tree does not contain."""
    return _file_port_sites(name, source.encode("utf-8"))


def _refused(
    sites: list[PortSite] | tuple[PortSite, ...], *, third: set[int], ours: set[int]
) -> tuple[list[PortSite], list[PortSite], list[PortSite], list[PortSite]]:
    """The four refusals the single owner makes over one population.

    Shared with L8 so the planted sources drive the predicate the shipped census drives: an
    absence claim nobody has watched refuse anything is a green that means nothing.
    """
    env_reads = [site for site in sites if site.kind == "env"]
    unreadable = [site for site in sites if site.kind == "blind"]
    named = [site for site in sites if site.kind in _NUMERIC_KINDS]
    occupied = [site for site in named if site.numbers & third]
    stray = [site for site in named if not site.numbers <= {0} | ours]
    return env_reads, unreadable, occupied, stray


def test_L6_no_tracked_test_moves_a_scrape_endpoint_it_does_not_own() -> None:
    """One predicate, four refusals, over every bind the tracked test tree makes.

    This leg and #232's L2 each used to hold half of the same sentence: L6 refused literal
    numbers that are neither ``0`` nor one of ours, L2 refused environment reads at
    tests/** sites, and the shape neither could read — a number arriving through a name —
    was judged by nobody. Measured over the shipped tree (``.scratch/m451_parity.log``):
    13 binds, of which #232's own classifier labels 4 ``other``, and those 4 are exactly
    the ones this census now names (2 ``free``, 2 ``roster``). ``MY_PORT = 9090`` walked
    past the old literal scan untouched; here it is ``fixed (9090)`` and charged.

    The refusals, sharpest first: an environment read (a test would follow whatever the
    host exports), a number that belongs to a process this repo does not write, a fixed
    number the roster declares for nobody, and a number the census cannot read at all. The
    last one is deliberate fail-closed: a port no census can name is one a test moves
    without anything noticing, so it is refused until it is spelled in one of the four
    readable ways — ``port=0``, a roster entry read through #232's parser, a file-local
    helper that binds ``0`` and reads the kernel's number back, or a literal that the
    roster then has to place.
    """
    third = set(_third_party_numbers().values())
    ours = {int(info["port"]) for info in _our_endpoint_jobs().values()}
    assert third and ours and not third & ours, (
        f"the refusals only mean something while the two populations stay disjoint: "
        f"third={sorted(third)}, ours={sorted(ours)}"
    )
    sites = list(_test_port_sites())
    assert len(sites) >= 5, (
        f"the census saw {len(sites)} binds; an empty scan cannot certify that nobody "
        "moves a scrape endpoint"
    )
    env_reads, unreadable, occupied, stray = _refused(sites, third=third, ours=ours)
    assert not env_reads, (
        f"these test binds take their port from the process environment "
        f"{[site.tag() for site in env_reads]}: a test that follows "
        "METRICS_PORT / INVOICE_CRON_METRICS_PORT moves whatever endpoint the host points "
        "it at, which is the promise #232's L2 used to guard and this leg now owns"
    )
    assert not unreadable, (
        f"these test binds hand the endpoint a number the census cannot read "
        f"{[site.tag() for site in unreadable]}: spell it as port=0, a roster entry, or a "
        "kernel-chosen probe in the same file, because an unreadable port is one a test "
        "moves without any census noticing"
    )
    assert not occupied, (
        f"these test binds land on a number the roster declares for a process this repo "
        f"does not write ({sorted(_third_party_numbers().items())}): "
        f"{[site.tag() for site in occupied]}. A scrape promise about node_exporter, "
        "RabbitMQ or Prometheus cannot be witnessed by occupying the port ourselves — that "
        "is a green that means the opposite."
    )
    assert not stray, (
        f"a test binds a fixed port that is neither kernel-chosen nor one of our rostered "
        f"numbers: {[site.tag() for site in stray]}. A number outside the roster still "
        "collides with whatever else runs on the plane and makes the suite depend on the "
        "host."
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
def test_L8_the_owner_refuses_every_moving_shape_and_accepts_every_admissible_one() -> None:
    """L6 certifies an absence, so its predicate has to be watched refusing something.

    Nothing in the tracked tree today hands the endpoint an environment knob, another
    process's number or an unreadable port, so all four of L6's asserts run against empty
    results by default: a mutation that blinds the census — a dropped keyword match, a
    flipped comparison, a resolver that stops following names — reports exactly the green
    the honest reading reports. The planted sources below drive the same function from both
    sides, and they are the shapes the shipped tree happens not to contain: a third party's
    number through a module constant, a knob reached through a name, a probe helper that
    only looks like a probe, and a dict entry that wears the roster's spelling.

    The last of those is the fold's reason for existing. #232's classifier reads the
    expression in front of ``port=`` and stops; ``KNOB = os.getenv(...)`` a call site then
    passes is an environment read it labels ``other``, which is the half of the sentence
    this leg took over.
    """
    third = set(_third_party_numbers().values())
    ours = {int(info["port"]) for info in _our_endpoint_jobs().values()}
    assert third and ours and not third & ours, (
        f"a planted source only means something while the two populations stay disjoint: "
        f"third={sorted(third)}, ours={sorted(ours)}"
    )
    foreign = sorted(third)[0]
    off = _free_port()
    assert off not in third | ours, f"the OS handed out a rostered number: {off}"
    default = _endpoint_default()
    assert default in ours, (
        f"the endpoint's own signature default {default} is not one of our rostered numbers "
        f"{sorted(ours)} today, so the no-port plant below would be charged as a stray "
        "bind and the acceptance claim would be about a different world than this one"
    )

    plants: list[tuple[str, str, str]] = [
        (
            "literal_foreign",
            f"serve_metrics_in_thread(port={foreign})\n",
            "fixed",
        ),
        (
            "name_foreign",
            f"MY_PORT = {foreign}\n"
            f"def test_x():\n"
            f"    serve_metrics_in_thread(port=MY_PORT)\n",
            "fixed",
        ),
        (
            "literal_offroster",
            f"serve_metrics_in_thread(port={off})\n",
            "fixed",
        ),
        (
            "computed_offroster",
            f"serve_metrics_in_thread(port={off - 90} + 90)\n",
            "fixed",
        ),
        (
            "knob_at_the_call",
            "import os\n"
            'serve_metrics_in_thread(port=os.environ["METRICS_PORT"])\n',
            "env",
        ),
        (
            "knob_through_a_name",
            "import os\n"
            'KNOB = os.getenv("OTHER_METRICS_PORT", "9100")\n'
            "def test_x():\n"
            "    serve_metrics_in_thread(port=KNOB)\n",
            "env",
        ),
        (
            "kernel_probe",
            "import socket\n"
            "def _free_port():\n"
            "    probe = socket.socket()\n"
            '    probe.bind(("127.0.0.1", 0))\n'
            "    port = int(probe.getsockname()[1])\n"
            "    probe.close()\n"
            "    return port\n"
            "def test_x():\n"
            "    serve_metrics_in_thread(port=_free_port())\n",
            "free",
        ),
        (
            "probe_that_looks_like_a_probe",
            "import socket\n"
            "def _free_port():\n"
            "    probe = socket.socket()\n"
            '    probe.bind(("127.0.0.1", 0))\n'
            "    _ = int(probe.getsockname()[1])\n"
            "    probe.close()\n"
            f"    return {foreign}\n"
            "def test_x():\n"
            "    serve_metrics_in_thread(port=_free_port())\n",
            "fixed",
        ),
        (
            "param_fed_by_probe_and_literal",
            "import socket\n"
            "def _free_port():\n"
            "    probe = socket.socket()\n"
            '    probe.bind(("127.0.0.1", 0))\n'
            "    return int(probe.getsockname()[1])\n"
            "def _bind(port):\n"
            "    return serve_metrics_in_thread(port=port)\n"
            "def test_x():\n"
            "    _bind(_free_port())\n"
            f"    return _bind({off})\n",
            "fixed",
        ),
        (
            "roster_read",
            "def test_L2():\n"
            "    for info in _our_endpoint_jobs().values():\n"
            '        serve_metrics_in_thread(port=int(info["port"]))\n',
            "roster",
        ),
        (
            "dict_entry_in_the_rosters_spelling",
            "def test_x():\n"
            f"    entry = {{'port': {foreign}}}\n"
            '    return serve_metrics_in_thread(port=entry["port"])\n',
            "blind",
        ),
        (
            "name_from_nowhere",
            "def test_x():\n"
            "    serve_metrics_in_thread(port=from_elsewhere)\n",
            "blind",
        ),
        (
            "no_port_keyword",
            "def test_x():\n"
            "    serve_metrics_in_thread()\n",
            "default",
        ),
    ]
    planted: dict[str, PortSite] = {}
    for name, source, expected in plants:
        sites = _planted_sites(f"{name}.py", source)
        assert len(sites) == 1, (
            f"the plant {name!r} must make exactly one bind of the endpoint, got "
            f"{[site.tag() for site in sites]}"
        )
        site = sites[0]
        assert site.kind == expected, (
            f"the plant {name!r} is the shape L6 says it refuses or admits as {expected!r}, "
            f"but the census read it as {site.tag()}"
        )
        planted[name] = site

    env_reads, unreadable, occupied, stray = _refused(
        list(planted.values()), third=third, ours=ours
    )
    assert [site.file for site in env_reads] == [
        "knob_at_the_call.py",
        "knob_through_a_name.py",
    ], (f"the environment half of the fold does not refuse both spellings: {env_reads}")
    assert [site.file for site in unreadable] == [
        "dict_entry_in_the_rosters_spelling.py",
        "name_from_nowhere.py",
    ], (f"the fail-closed half of the fold does not refuse unreadable ports: {unreadable}")
    assert [site.file for site in occupied] == [
        "literal_foreign.py",
        "name_foreign.py",
        "probe_that_looks_like_a_probe.py",
    ], (
        f"the number the roster declares for somebody else is not charged wherever it "
        f"arrives — a literal, a module constant, or the return of a helper that only "
        f"looks like a kernel probe: {occupied}"
    )
    assert [site.file for site in stray] == [
        "literal_foreign.py",
        "name_foreign.py",
        "literal_offroster.py",
        "computed_offroster.py",
        "probe_that_looks_like_a_probe.py",
        "param_fed_by_probe_and_literal.py",
    ], (
        f"stray refuses exactly the fixed numbers that are neither 0 nor one of ours "
        f"({stray}); the probe-fed-and-literal plant belongs here even though the same "
        f"helper is also fed a kernel number, because one readable literal is enough to "
        f"make the bind depend on the host"
    )
    admitted = {
        "kernel_probe.py",
        "roster_read.py",
        "no_port_keyword.py",
    }
    charged = {site.file for bucket in (env_reads, unreadable, occupied, stray) for site in bucket}
    assert not admitted & charged, (
        f"the census charges the three provenances a test is allowed to bind with: "
        f"{sorted(admitted & charged)}. The kernel-chosen port, a rostered number of ours "
        f"and the signature default {default} are what L2, L4 and every production caller "
        f"already do, so refusing them would refuse the legs this file exists to run."
    )

    shipped = _refused(list(_test_port_sites()), third=third, ours=ours)
    assert shipped == ([], [], [], []), (
        f"the shipped census drives the same predicate to a refusal L6 did not report: "
        f"{[site.tag() for bucket in shipped for site in bucket]}"
    )
    named = [
        site for site in _test_port_sites() if site.kind in {"free", "roster"}
    ]
    assert named, (
        "no shipped bind is readable only through a name any more, so the name-following "
        "half of this census — the half that took the judgment off #232's shallow "
        "classifier — is exercised by nothing but the plants above, and L6's claim to own "
        "the whole sentence would be history rather than measurement"
    )

    scan = _gate_232()._metrics_scan()
    hidden = {
        (rel, line)
        for rel, info in scan.items()
        if info["calls"] and rel.startswith("tests/")
        for line, _shape in info["calls"]
    }
    rows = {(site.file, site.line) for site in _test_port_sites()}
    assert hidden == rows, (
        f"#232's census carves tests/** out of its listener population on the strength of "
        f"this leg, but the two censuses no longer enumerate the same binds: it hides "
        f"{sorted(hidden - rows)}, this one sees {sorted(rows - hidden)}. One of the two "
        "readers has stopped walking the call sites, and the exemption is unsupervised "
        "again."
    )
