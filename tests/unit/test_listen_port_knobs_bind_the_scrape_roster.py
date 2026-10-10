"""#232: the roster's port and path are promises about somebody else's socket,
and nothing read the provider side of those promises together with the docs
that advertise the knobs which move them.

Measured first (.scratch/probe232_ports.py, read-only, both the worktree and the
``git show HEAD:`` blobs staged outside the repo root):

* 6 scrape jobs, and each one's port has a provider-side EVIDENCE — but of
  four different kinds. ``api`` is published by compose and served by a route in
  api/server.py; ``worker`` is backed by *only* the default of an env its own
  process reads; ``outbox-relay`` is pinned twice over (expose + a literal env
  + the same kind of code default); ``otel-collector``'s port lives in
  infra/otel/otel-collector.yaml; ``prometheus`` and ``rabbitmq`` rest on
  **image defaults** — rabbitmq:15692 has no repo-side declaration of any kind.
* compose publishes 13 ``${X:-port}`` host-side knobs. OBSERVABILITY.md §2 named
  exactly 5 of them and claimed 「均可经环境变量覆盖 … 改左边值」. Two knobs that
  move a *listen* port — WORKER_METRICS_PORT and OUTBOX_RELAY_METRICS_PORT, read
  by the processes themselves — were named nowhere in §2, so an operator fixing a
  port conflict by their side of the file would move a scrape endpoint off the
  roster. #220's probes make that loud rather than silent, but the alert would
  read 「目标没了」, not 「端口错了」.
* Those two same-shaped knobs are NOT interchangeable: compose.production.yml
  pins ``OUTBOX_RELAY_METRICS_PORT: "9101"`` as a literal (so .env cannot move
  it) and sets nothing for the worker (so .env moves that one freely). No doc
  said which was which.
* No compose mapping parameterises the *container* side of a port mapping, so a
  listen port can only ever move through the process env or an image bump. That
  premise needed a repair before it was evidence: the first version of the
  splitter cut each mapping at its last colon, and since ``${X:-9090}`` holds a
  colon inside its braces, a templated *container* side reached L8 as ``-9090}`` —
  the arm that templates it red L1 and L5 (artifacts of the mangled string) and
  left L8, the clause built for exactly that mutation, GREEN. See `_split_mapping`.
* observability/tracing.py's default endpoint literal is ``localhost:4318``, the
  same number §2 advertises as a freely-overridable host knob: moving it leaves
  an in-app client pointing at a port nothing publishes.

So this gate pins each job's evidence *set* (derived, both directions — a
declaration that stops being true reds, and so does a new backing that nobody
declared), pins the knob inventory in §2 against the deploy files, and forces the
doc to keep its classification honest: the bullet for each listen-port knob must
carry the movability its compose state actually has, plus the roster file the
same change must touch.

Case map (used by .scratch/arm232-port-arms.py):
  L1  every scrape job's provider-evidence SET == the declared table
  L2  the listen-port knobs are exactly what the code reads: an AST call-site
      census over every tracked file, both directions (an undeclared metrics
      server or a dead knob reds), with the definition site separated from the
      callers and the tests/** exclusion re-derived from each test's own port
      expression
  L3  each knob's literal default == the roster port of the job it serves
  L4  each knob's compose state is literal-or-absent, never templated, and a
      literal must equal the roster port
  L5  §2's env inventory partitions into publish ∪ listen ∪ client, both ways
  L6  §2 classifies publish knobs correctly and its stated 「N 处」 == the
      number of exception bullets it actually carries
  L7  each listen-knob bullet names the roster file, quotes the roster's own
      target, matches the code default it quotes against the code's literal, and
      carries the movability marker its compose state actually earns
  L8  no compose mapping parameterises the container side
  L9  roster port == collector exporter endpoint == published container port
  L10 the roster's metrics_path is literally served by its declared source file
  L11 §1's prometheus row states a path exactly where the roster declares one,
      and states the same value
  L12 the in-app OTLP client default port == the receiver's container port, and
      §2 still tells the reader which env re-points it
  L13 image-default jobs: declared image string == compose, no flag overrides it
  L14 #220's roster parse and this gate's agree on the population and on which
      jobs our code serves
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROM_YML = "infra/prometheus/prometheus.yml"
OTEL_YAML = "infra/otel/otel-collector.yaml"
OBS_MD = "docs/operations/OBSERVABILITY.md"
COMPOSE_FILES = ("compose.phase0.yml", "compose.production.yml", "compose.observability.yml")
GATE_220 = ROOT / "tests" / "unit" / "test_scrape_roster_binds_the_liveness_probes.py"

#: Prometheus scrapes this path unless a job declares ``metrics_path``. External
#: behaviour, named here so L11 can refuse a doc that states a path the config
#: leaves implicit.
DEFAULT_METRICS_PATH = "/metrics"

#: env name -> the scrape job whose listen port it moves, read by the process.
_LISTEN_PORT_KNOBS = {
    "WORKER_METRICS_PORT": "worker",
    "OUTBOX_RELAY_METRICS_PORT": "outbox-relay",
}

#: Files allowed to start a metrics HTTP server. L2 re-derives this from a
#: repo-wide call-site census, so a third process must be declared here — with
#: its knob, its bullet in §2 and its evidence class — before it can pass.
_KNOB_SITES = ("agent/worker.py", "storage/outbox_relay.py")

#: The module that DEFINES serve_metrics_in_thread. L2's census must SEE this
#: file and must never list it as a listener: separating a definition from a
#: use is exactly what a substring scan cannot do (it matched the ``def`` line).
_DEFINITION_FILE = "observability/metrics_http.py"

#: Which declaration in the repo actually answers each roster target. Only our
#: own processes belong here; third-party targets are backed by compose/config
#: evidence or by _IMAGE_DEFAULTS below.
_PATH_SOURCES: dict[str, tuple[str, str]] = {
    "api": ("api/server.py", "route"),
    "worker": ("observability/metrics_http.py", "comparison"),
    "outbox-relay": ("observability/metrics_http.py", "comparison"),
}

#: What backs each job's port, on the provider's own side. L1 recomputes the set
#: from the deploy files and the code and refuses any difference in either
#: direction.
_EVIDENCE: dict[str, frozenset[str]] = {
    "api": frozenset({"compose-publish", "code-path"}),
    "worker": frozenset({"code-listen", "code-path"}),
    "outbox-relay": frozenset(
        {"compose-expose", "compose-env-literal", "code-listen", "code-path"}
    ),
    "otel-collector": frozenset({"compose-publish", "config-endpoint"}),
    "prometheus": frozenset({"compose-publish", "image-default"}),
    "rabbitmq": frozenset({"image-default"}),
}

#: Jobs whose listen port is the image's built-in default: nothing in this repo
#: sets it, so a tag bump is the only thing that could move it. ``override_flag``
#: must stay absent from the service command, or the claim below is stale.
_IMAGE_DEFAULTS: dict[str, dict[str, Any]] = {
    "rabbitmq": {
        "image": "rabbitmq:4.0-management-alpine",
        "port": 15692,
        "override_flag": None,
        "reason": (
            "rabbitmq_prometheus plugin, enabled in the -management image; 15692 "
            "is that plugin's built-in port and no repo file states it"
        ),
    },
    "prometheus": {
        "image": "prom/prometheus:v3.3.1",
        "port": 9090,
        "override_flag": "--web.listen-address",
        "reason": (
            "Prometheus' own default web port; the command block starts it with "
            "config/storage/retention flags only"
        ),
    },
}

#: §2's exception bullets must say, per knob, whether .env can move it. The two
#: markers are mutually exclusive inside one bullet, so a doc that hedges reds.
_MOVABLE_MARKER = "改得动"
_PINNED_MARKER = "改不动"
_ROSTER_FILE = "infra/prometheus/prometheus.yml"

_CN_NUMBERS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}


def _lf(rel: str) -> str:
    return (ROOT / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")


def _yaml(rel: str) -> dict[str, Any]:
    data = yaml.safe_load(_lf(rel))
    assert isinstance(data, dict), f"{rel} did not parse to a mapping"
    return data


# ───────────────────────────────────────── roster ─────────────────────────────────────────
def _roster() -> dict[str, dict[str, Any]]:
    """job -> host / port / metrics_path / whether the path was declared.

    Floored at 6 so a narrowed parse cannot turn every 'no mismatch found'
    below into a claim about an empty population.
    """
    configs = _yaml(PROM_YML)["scrape_configs"]
    assert isinstance(configs, list), "scrape_configs is not a list"
    out: dict[str, dict[str, Any]] = {}
    for entry in configs:
        targets: list[str] = []
        for sc in entry.get("static_configs", []) or []:
            targets.extend(str(t) for t in sc["targets"])
        assert len(targets) == 1, f"{entry['job_name']} has {len(targets)} targets"
        host, _, port = targets[0].rpartition(":")
        out[str(entry["job_name"])] = {
            "host": host,
            "port": int(port),
            "target": targets[0],
            "path": str(entry.get("metrics_path", DEFAULT_METRICS_PATH)),
            "path_declared": "metrics_path" in entry,
        }
    assert len(out) >= 6, f"roster parse collapsed: {sorted(out)}"
    return out


# ──────────────────────────────────────── compose ────────────────────────────────────────
def _service_records(job: str) -> list[dict[str, Any]]:
    """Every compose declaration of ``job`` across the three deploy files."""
    out: list[dict[str, Any]] = []
    for rel in COMPOSE_FILES:
        services = _yaml(rel).get("services")
        assert isinstance(services, dict), f"{rel} declares no services mapping"
        svc = services.get(job)
        if isinstance(svc, dict):
            out.append({"file": rel, "svc": svc})
    return out


def _split_mapping(row: str) -> tuple[str, str]:
    """(host side, container side) of a compose port mapping, cut at its last
    TOP-LEVEL colon.

    ``${PROMETHEUS_PORT:-9090}:9090`` carries a colon *inside* its braces, so
    ``row.rpartition(":")`` cuts the substitution in half: a mapping whose
    container side is templated arrives as ``-9090}``. #232's own
    ``container_side_templated`` arm measured exactly that on round 1 — L8, the
    clause written to refuse ``${`` on the container side, stayed GREEN while L1
    and L5 went red on the mangled string. A belt cannot see what the parser ate,
    so the split walks brace depth and cuts only where depth is zero.
    """
    parts: list[str] = []
    buf = ""
    depth = 0
    for ch in row:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            assert depth >= 0, f"port mapping {row!r}: unbalanced }}"
        elif ch == ":" and depth == 0:
            parts.append(buf)
            buf = ""
            continue
        buf += ch
    assert depth == 0, f"port mapping {row!r}: unterminated ${{"
    parts.append(buf)
    assert 2 <= len(parts) <= 3, (
        f"port mapping {row!r} is not [ip:]host:container, the split read {parts}"
    )
    left, right = ":".join(parts[:-1]), parts[-1]
    assert left and right, f"port mapping {row!r} is not host:container"
    return left, right


def _mappings(svc: dict[str, Any]) -> list[tuple[str, str]]:
    return [_split_mapping(str(row)) for row in svc.get("ports", []) or []]


def _all_mappings() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for rel in COMPOSE_FILES:
        services = _yaml(rel)["services"]
        for name, svc in services.items():
            for left, right in _mappings(svc):
                rows.append({"service": str(name), "left": left, "right": right})
    assert len(rows) >= 10, f"port mapping census collapsed: {len(rows)}"
    return rows


def _env_state(job: str, knob: str) -> tuple[str, str]:
    """(state, value) of ``knob`` in the compose service that serves ``job``."""
    seen: list[tuple[str, str]] = []
    for rec in _service_records(job):
        environment = rec["svc"].get("environment") or {}
        for key, value in environment.items():
            if str(key) == knob:
                seen.append((str(value), rec["file"]))
    if not seen:
        return "absent", ""
    assert len(seen) == 1, f"{knob} is set in more than one place: {seen}"
    value = seen[0][0]
    if value.isdigit():
        return "literal", value
    return "templated", value


def _publish_knobs() -> dict[str, str]:
    """``${NAME:-port}`` on the HOST side of the observability stack's mappings.

    Read from compose.observability.yml — the file §2's sentence is about — and
    never from the doc, so the doc cannot teach the gate what to expect.
    """
    out: dict[str, str] = {}
    for name, svc in _yaml("compose.observability.yml")["services"].items():
        for left, right in _mappings(svc):
            match = re.fullmatch(r"\$\{([A-Z0-9_]+):-?(\d{2,5})\}", left)
            if match:
                out[match.group(1)] = f"{name}:{right}"
    assert len(out) >= 5, f"publish knob census collapsed: {sorted(out)}"
    return out


# ────────────────────────────────────────── code ──────────────────────────────────────────
def _call_name(node: ast.Call) -> str | None:
    """The bare callee of a call: ``f(...)`` or ``mod.f(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _port_shape(node: ast.expr) -> str:
    """How a listen-port expression arrives: ``env:NAME``, ``literal:N``, other."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _call_name(sub) == "getenv":
            first = sub.args[0] if sub.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return f"env:{first.value}"
        if (
            isinstance(sub, ast.Subscript)
            and isinstance(sub.slice, ast.Constant)
            and isinstance(sub.slice.value, str)
        ):
            return f"env:{sub.slice.value}"
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return f"literal:{node.value}"
    return "other"


def _describe(node: ast.AST) -> str:
    """A short, readable shape for a failure message (an AST dump truncates)."""
    if isinstance(node, ast.Call):
        name = _call_name(node) or type(node.func).__name__
        inner = ", ".join(_describe(a) for a in node.args)
        return f"{name}({inner})"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    return type(node).__name__


def _metrics_scan() -> dict[str, dict[str, Any]]:
    """Tracked files that mention the metrics server, bucketed by AST role.

    The bytes substring only pre-filters candidates for speed; bucket membership
    comes from the parse tree. A plain bytes census could not make L2's claim:
    it matched the defining ``def`` line, the unit test that calls the function
    directly, and (once this file is tracked) the gate's own source, so the
    population it enumerated would have to exempt the very files it enumerates.
    """
    listing = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    ).stdout.decode("utf-8")
    files = [line for line in listing.splitlines() if line]
    assert len(files) > 50, f"tracked-file census collapsed: {len(files)} files"
    out: dict[str, dict[str, Any]] = {}
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if b"serve_metrics_in_thread" not in raw:
            continue
        tree = ast.parse(raw.decode("utf-8").replace("\r\n", "\n"))
        calls: list[tuple[int, str]] = []
        defines = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == "serve_metrics_in_thread":
                port = next((kw.value for kw in node.keywords if kw.arg == "port"), None)
                target = port if port is not None else node
                calls.append((node.lineno, _port_shape(target)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defines += node.name == "serve_metrics_in_thread"
        out[rel] = {"calls": calls, "defines": defines}
    assert out, "no tracked file mentions serve_metrics_in_thread at all"
    definers = sorted(rel for rel, info in out.items() if info["defines"])
    assert definers == [_DEFINITION_FILE], (
        f"serve_metrics_in_thread must be defined exactly once, in "
        f"{_DEFINITION_FILE}; the scan saw definitions in {definers}"
    )
    assert sorted(rel for rel, info in out.items() if info["calls"]), (
        "the scan saw the definition but no caller anywhere: the census read "
        "an empty population"
    )
    return out


def _knob_defaults() -> dict[str, tuple[str, int]]:
    """env name -> (declaring file, literal default) for metrics-server calls.

    Each declared site must contain exactly one call whose ``port=`` is
    ``int(os.getenv(NAME, DEFAULT))`` with two literals: the env name and the
    default are the two things a port knob moves, so a comment, a log line or a
    differently-wrapped expression cannot satisfy the census — and the failure
    message names the shape it actually found.
    """
    out: dict[str, tuple[str, int]] = {}
    for rel in _KNOB_SITES:
        tree = ast.parse(_lf(rel))
        found: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) != "serve_metrics_in_thread":
                continue
            ports = [kw.value for kw in node.keywords if kw.arg == "port"]
            assert len(ports) == 1, (
                f"{rel}:{node.lineno}: serve_metrics_in_thread call needs one "
                f"port= keyword, got keywords {[kw.arg for kw in node.keywords]}"
            )
            wrapper = ports[0]
            assert isinstance(wrapper, ast.Call) and _call_name(wrapper) == "int", (
                f"{rel}:{node.lineno}: port= is {_describe(wrapper)}, not "
                f"int(os.getenv(NAME, DEFAULT)) — the listen port stopped being "
                f"an env knob"
            )
            assert len(wrapper.args) == 1, (
                f"{rel}:{node.lineno}: int() wraps "
                f"{[_describe(a) for a in wrapper.args]}, expected one argument"
            )
            read = wrapper.args[0]
            assert isinstance(read, ast.Call) and _call_name(read) == "getenv", (
                f"{rel}:{node.lineno}: int() wraps {_describe(read)}, not "
                f"os.getenv(...) — the env name and default have to be literal"
            )
            assert len(read.args) == 2 and all(
                isinstance(a, ast.Constant) for a in read.args
            ), (
                f"{rel}:{node.lineno}: getenv needs two literals (name, default), "
                f"got {[_describe(a) for a in read.args]}"
            )
            found.append((str(read.args[0].value), int(str(read.args[1].value))))
        assert len(found) == 1, f"{rel}: expected one env-driven metrics call, got {found}"
        out[found[0][0]] = (rel, found[0][1])
    assert out, "_KNOB_SITES declare no metrics server at all"
    return out


def _served_paths(rel: str, kind: str) -> set[str]:
    """Paths a file's own declarations serve: FastAPI route literals, or the
    ``self.path == "..."`` comparisons of the stdlib handler."""
    tree = ast.parse(_lf(rel))
    out: set[str] = set()
    if kind == "route":
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not dec.args:
                    continue
                func = dec.func
                if not (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "app"
                    and func.attr in {"get", "post", "put", "delete", "api_route"}
                ):
                    continue
                first = dec.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    out.add(first.value)
        assert len(out) >= 2, f"{rel}: app-level route census collapsed: {sorted(out)}"
    else:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or not isinstance(
                node.left, ast.Attribute
            ):
                continue
            if node.left.attr != "path":
                continue
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(
                    comparator.value, str
                ):
                    out.add(str(comparator.value))
        assert out, f"{rel}: no self.path comparison found"
    return out


def _client_endpoint() -> tuple[str, str]:
    """(env name, literal default URL) of the OTLP exporter's endpoint getenv."""
    tree = ast.parse(_lf("observability/tracing.py"))
    found: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "attr", "") != "getenv":
            continue
        if len(node.args) < 2:
            continue
        name, default = node.args[0], node.args[1]
        if not (isinstance(name, ast.Constant) and isinstance(default, ast.Constant)):
            continue
        if isinstance(name.value, str) and name.value.startswith("OTEL_EXPORTER"):
            found.append((str(name.value), str(default.value)))
    assert len(found) == 1, f"expected one OTLP endpoint default, found {found}"
    return found[0]


def _otel_endpoints() -> dict[str, str]:
    """Every ``endpoint: host:port`` in the collector config, by its yaml path.

    Recursive on purpose: a fourth endpoint under any other key is counted by
    this same scan, so the scan cannot be made blind by renaming where it lives.
    """
    data = _yaml(OTEL_YAML)
    out: dict[str, str] = {}

    def walk(node: Any, trail: tuple[str, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "endpoint" and isinstance(value, str):
                    out[".".join(trail)] = value
                else:
                    walk(value, (*trail, str(key)))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, (*trail, str(index)))

    walk(data, ())
    assert len(out) >= 3, f"otel endpoint parse collapsed: {out}"
    return out


# ────────────────────────────────────────── docs ──────────────────────────────────────────
def _section(start: str, stop: str) -> str:
    body = _lf(OBS_MD)
    assert start in body and stop in body, f"missing section markers {start!r}/{stop!r}"
    return body[body.index(start) : body.index(stop)]


def _sec2_bullets() -> list[str]:
    """§2's exception bullets, each as its whole indented block."""
    blocks: list[str] = []
    current: list[str] = []
    for line in _section("## 2.", "## 3.").splitlines():
        if line.startswith("  - "):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        elif current and line.startswith("    "):
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def _doc_envs() -> set[str]:
    """ENV-shaped tokens §2's own section spells out."""
    return set(re.findall(r"\b([A-Z][A-Z0-9_]{4,})\b", _section("## 2.", "## 3.")))


def _sec1_row() -> str:
    """§1's prometheus row, the operator-facing target list."""
    row = next(
        (
            line
            for line in _section("## 1.", "## 2.").splitlines()
            if line.startswith("| prometheus |")
        ),
        "",
    )
    assert row, "§1 has no prometheus row to compare against the roster"
    return row


# ───────────────────────────────────────── tests ─────────────────────────────────────────
# ─────────────────────────────────────────── L1 ───────────────────────────────────────────
def test_each_scrape_job_has_the_declared_provider_evidence() -> None:
    """The roster says 'somebody listens here'. This is the provider's side of
    that sentence, recomputed from the deploy files, the collector config and
    the code. A backing that disappears (a port stop being published, an env
    stop matching) reds; so does a new backing nobody declared, because an
    undeclared support is one nobody checked for strength."""
    derived: dict[str, set[str]] = {}
    for job, info in _roster().items():
        found: set[str] = set()
        for rec in _service_records(job):
            svc = rec["svc"]
            for _left, right in _mappings(svc):
                if right.isdigit() and int(right) == info["port"]:
                    found.add("compose-publish")
            if str(info["port"]) in [str(x) for x in (svc.get("expose") or [])]:
                found.add("compose-expose")
            for key, value in (svc.get("environment") or {}).items():
                text = str(value)
                if "PORT" in str(key) and text.isdigit() and text == str(info["port"]):
                    found.add("compose-env-literal")
        if job in set(_LISTEN_PORT_KNOBS.values()):
            found.add("code-listen")
        if job in _PATH_SOURCES and info["path"] in _served_paths(*_PATH_SOURCES[job]):
            found.add("code-path")
        for trail, endpoint in _otel_endpoints().items():
            if trail.startswith("exporters.") and endpoint.endswith(f":{info['port']}"):
                found.add("config-endpoint")
        default = _IMAGE_DEFAULTS.get(job)
        if default is not None and int(default["port"]) == info["port"]:
            found.add("image-default")
        derived[job] = found

    declared = {job: set(members) for job, members in _EVIDENCE.items()}
    assert set(derived) == set(declared), (
        f"the roster and the evidence table cover different jobs: "
        f"roster only {sorted(set(derived) - set(declared))}, "
        f"table only {sorted(set(declared) - set(derived))}"
    )
    for job in sorted(derived):
        assert derived[job], f"{job} has no provider-side evidence at all"
        assert derived[job] == declared[job], (
            f"{job}: provider side now reads {sorted(derived[job])} but the "
            f"declared backing is {sorted(declared[job])} — missing "
            f"{sorted(declared[job] - derived[job])}, undeclared "
            f"{sorted(derived[job] - declared[job])}"
        )
    classes = {c for members in derived.values() for c in members}
    for member in {c for s in declared.values() for c in s}:
        assert member in classes, f"evidence class {member!r} is declared but seen nowhere"


# ─────────────────────────────────────────── L2 ───────────────────────────────────────────
def test_the_listen_port_knobs_are_exactly_what_the_code_reads() -> None:
    """A census over the whole TRACKED tree, not over the files this gate was
    written to look at: a third process that starts a metrics server moves a
    scrape endpoint and must be declared before it can pass quietly.

    The population is git's, not the filesystem's — what a fresh checkout and CI
    contain, and an untracked file is not deployable, so it is not yet shipped.
    The population is CALLERS outside ``tests/**``; the definition site drops
    out because a ``def`` is not a call, and the tests/** exclusion is guarded
    below rather than trusted: an exclusion that stops hiding anything reds, and
    a test that starts binding a real port reds too.
    """
    scan = _metrics_scan()
    assert not scan[_DEFINITION_FILE]["calls"], (
        f"{_DEFINITION_FILE} both defines serve_metrics_in_thread and calls it, "
        f"so the listener census has to grow a declaration for it"
    )
    listeners = {
        rel for rel, info in scan.items() if info["calls"] and not rel.startswith("tests/")
    }
    assert listeners == set(_KNOB_SITES), (
        f"files starting a metrics server and _KNOB_SITES disagree: "
        f"undeclared {sorted(listeners - set(_KNOB_SITES))}, "
        f"dead entries {sorted(set(_KNOB_SITES) - listeners)}"
    )
    exempt = {
        rel: info["calls"]
        for rel, info in scan.items()
        if info["calls"] and rel.startswith("tests/")
    }
    assert exempt, (
        "the census carves tests/** out of the listener population, but no test "
        "calls the metrics server any more: the exclusion hides nothing, so "
        "delete it instead of keeping a slot for a future listener"
    )
    for rel, calls in sorted(exempt.items()):
        for line, shape in calls:
            assert not shape.startswith("env:"), (
                f"{rel}:{line} starts a metrics server with a port read from "
                f"{shape[4:]}: a test now moves a scrape endpoint, so the "
                f"tests/** exclusion is false and this file needs declaring"
            )
    derived = set(_knob_defaults())
    assert derived == set(_LISTEN_PORT_KNOBS), (
        f"the code reads {sorted(derived)} as listen-port knobs but the table "
        f"declares {sorted(_LISTEN_PORT_KNOBS)}"
    )


# ─────────────────────────────────────────── L3 ───────────────────────────────────────────
def test_each_knob_default_is_the_port_the_roster_scrapes() -> None:
    jobs = _roster()
    defaults = _knob_defaults()
    for knob, job in sorted(_LISTEN_PORT_KNOBS.items()):
        assert job in jobs, f"{knob} serves job {job!r}, which nothing scrapes"
        assert knob in defaults, (
            f"the table claims {knob} is read at a metrics-server call site, but "
            f"the AST census finds no such declaration any more — the knob was "
            f"renamed or its call deleted, so nothing binds this listen port"
        )
        rel, default = defaults[knob]
        assert default == jobs[job]["port"], (
            f"{rel} defaults {knob} to {default} but the roster scrapes "
            f"{job} on {jobs[job]['port']} — the process answers on one port, "
            f"Prometheus asks on the other"
        )


# ─────────────────────────────────────────── L4 ───────────────────────────────────────────
def test_a_listen_port_knob_is_pinned_by_literal_or_left_absent() -> None:
    """If compose ever templates the knob, .env moves a listen port the roster
    hard-codes, and the doc's per-knob classification below has to be rewritten
    rather than quietly inherited."""
    jobs = _roster()
    for knob, job in sorted(_LISTEN_PORT_KNOBS.items()):
        state, value = _env_state(job, knob)
        assert state != "templated", (
            f"{job} sets {knob} to {value!r}: a templated listen-port knob lets "
            f".env move the scrape endpoint, so this unit's doc clause (L7) and "
            f"the roster pin both need re-checking before this can pass"
        )
        if state == "literal":
            assert int(value) == jobs[job]["port"], (
                f"{job} pins {knob} to {value} while the roster scrapes "
                f"{jobs[job]['port']} — the deployment says one port, the "
                f"scrape config another"
            )


# ─────────────────────────────────────────── L5 ───────────────────────────────────────────
def test_observability_doc_environment_inventory_partitions_the_knobs() -> None:
    """§2 is the operator's knob list. Every env it names must be a knob this
    repo actually has, and every knob that exists must be named there — a
    leftover name is a stale claim, a missing one is the hole #232 was found in."""
    named = _doc_envs()
    publish = set(_publish_knobs())
    listen = set(_LISTEN_PORT_KNOBS)
    client = {_client_endpoint()[0]}
    known = publish | listen | client
    assert named == known, (
        f"§2 names {sorted(named - known)} that no deploy file or default "
        f"declares, and never names {sorted(known - named)} "
        f"(publish: {sorted(publish)}; listen: {sorted(listen)}; client: "
        f"{sorted(client)})"
    )


# ─────────────────────────────────────────── L6 ───────────────────────────────────────────
def test_the_publish_knob_sentence_does_not_claim_too_much() -> None:
    """「均可经环境变量覆盖」 is only true of the host side. The sentence has to
    say so and say what does NOT move, or a reader applies it to the wrong knob."""

    sec2 = _section("## 2.", "## 3.")
    head = sec2[: sec2.index("另有")] if "另有" in sec2 else sec2
    assert "左边值" in head, "§2's knob sentence no longer says which side it covers"
    assert "监听端口不变" in head, (
        "§2 says the knobs override the host publish port but never states that "
        "the container listen port — and therefore the scrape endpoint — stays put"
    )
    stated = re.search(r"另有([一二三四五六七]|\d+)处不属于", sec2)
    assert stated is not None, "§2 no longer introduces its exception bullets"
    digits = stated.group(1)
    count = int(digits) if digits.isdigit() else _CN_NUMBERS[digits]
    bullets = _sec2_bullets()
    assert count == len(bullets), (
        f"§2 announces {count} exceptions but carries {len(bullets)} bullets: "
        f"{[b.splitlines()[0][:40] for b in bullets]}"
    )


# ─────────────────────────────────────────── L7 ───────────────────────────────────────────
def test_each_listen_knob_bullet_carries_its_own_truth() -> None:
    """The disclosure has to be per knob, not per paragraph: the two knobs look
    alike by name yet differ in whether .env can move them, and either way the
    roster file is the change that has to happen in the same edit."""
    jobs = _roster()
    defaults = _knob_defaults()
    bullets = _sec2_bullets()
    for knob, job in sorted(_LISTEN_PORT_KNOBS.items()):
        hits = [b for b in bullets if knob in b]
        assert len(hits) == 1, (
            f"§2 must carry exactly one bullet naming {knob}, found {len(hits)}"
        )
        bullet = hits[0]
        assert _ROSTER_FILE in bullet, (
            f"{knob} moves the port the roster scrapes, but its bullet never "
            f"names {_ROSTER_FILE} — the reader is told about one half of the edit"
        )
        assert f"{jobs[job]['host']}:{jobs[job]['port']}" in bullet, (
            f"{knob}'s bullet does not quote the roster's own target "
            f"{jobs[job]['host']}:{jobs[job]['port']}, so the number it is "
            f"warning about is invisible"
        )
        quoted = re.search(r"代码默认 (\d{2,5})", bullet)
        if quoted is not None:
            assert knob in defaults, (
                f"{knob}'s bullet quotes 代码默认 {quoted.group(1)}, but no tracked "
                f"call site declares {knob} any more — the number the operator is "
                f"told the process defaults to has no counterpart in the code"
            )
            rel_default, default = defaults[knob]
            assert int(quoted.group(1)) == default, (
                f"{knob}'s bullet quotes 代码默认 {quoted.group(1)} while "
                f"{rel_default} now defaults it to {default} — the doc and the "
                f"code's own literal stopped saying the same number"
            )
        state, _value = _env_state(job, knob)
        want, forbid = (
            (_MOVABLE_MARKER, _PINNED_MARKER)
            if state == "absent"
            else (_PINNED_MARKER, _MOVABLE_MARKER)
        )
        assert want in bullet, (
            f"{job} has no {knob} entry in compose ({state}), so .env can move "
            f"it — but the bullet does not say {want!r}"
            if state == "absent"
            else f"{job} pins {knob} as a literal in compose, yet the bullet "
            f"does not say {want!r}"
        )
        assert forbid not in bullet, (
            f"{knob}'s bullet says {forbid!r} while compose says otherwise "
            f"(state {state!r}) — the two knobs' descriptions were swapped"
        )


# ─────────────────────────────────────────── L8 ───────────────────────────────────────────
def test_no_deploy_file_parameterises_a_container_port() -> None:
    """The roster may hard-code ports only while nothing on the container side
    of a mapping is templated. If a mapping ever reads ``${X:-p}:${X:-p}``,
    'edit the roster' stops being enough and this unit's premise needs a new
    clause instead."""

    templated = [
        row
        for row in _all_mappings()
        if re.search(r"\$\{[A-Z0-9_]+", row["right"])
    ]
    assert not templated, (
        f"these mappings template the container side, so a listen port can move "
        f"without any edit to infra/prometheus/prometheus.yml: {templated}"
    )


# ─────────────────────────────────────────── L9 ───────────────────────────────────────────
def test_the_otel_port_is_one_number_across_three_planes() -> None:
    """roster target == the collector's own exporter endpoint == the container
    port compose publishes. Each plane states it independently; two agreeing
    against a third is the outage."""
    info = _roster()["otel-collector"]
    endpoint = _otel_endpoints()["exporters.prometheus"]
    assert endpoint.endswith(f":{info['port']}"), (
        f"the collector exports metrics on {endpoint!r} while the roster scrapes "
        f"port {info['port']}"
    )
    rights = [
        right
        for rec in _service_records("otel-collector")
        for _left, right in _mappings(rec["svc"])
    ]
    assert str(info["port"]) in rights, (
        f"compose publishes no container mapping for port {info['port']} that the "
        f"roster scrapes on otel-collector (container sides: {rights})"
    )


# ────────────────────────────────────────── L10 ──────────────────────────────────────────
def test_the_scrape_path_is_served_by_its_declared_source() -> None:
    """A metrics_path nobody literally serves is a 404 that Prometheus reports
    as an up target with no series — the rule set then reads nothing."""
    jobs = _roster()
    assert set(_PATH_SOURCES) <= set(jobs), (
        f"_PATH_SOURCES names jobs the roster does not scrape: "
        f"{sorted(set(_PATH_SOURCES) - set(jobs))}"
    )
    for job, (rel, kind) in sorted(_PATH_SOURCES.items()):
        served = _served_paths(rel, kind)
        assert jobs[job]["path"] in served, (
            f"{job} is scraped at {jobs[job]['path']} but {rel} declares only "
            f"{sorted(served)}"
        )
    listen_jobs = set(_LISTEN_PORT_KNOBS.values())
    assert listen_jobs <= set(_PATH_SOURCES), (
        f"these jobs are served by our own process yet declare no path source: "
        f"{sorted(listen_jobs - set(_PATH_SOURCES))}"
    )


# ────────────────────────────────────────── L11 ──────────────────────────────────────────
def test_the_doc_row_states_a_path_exactly_where_the_roster_declares_one() -> None:
    """#220's R10 compared host:port tokens; the paths were never checked.
    Omitting ``metrics_path`` is not the same claim as writing ``/metrics``, and
    /metrics/per-object is a different endpoint, not a spelling."""

    token = re.compile(r"\b([a-z][a-z0-9.-]*):(\d{2,5})(/[A-Za-z0-9._/-]*)?\b")
    row = _sec1_row()
    claimed = {f"{h}:{p}{pth or ''}" for h, p, pth in token.findall(row)}
    jobs = _roster()
    expected = {
        (
            f"{info['host']}:{info['port']}{info['path']}"
            if info["path_declared"]
            else f"{info['host']}:{info['port']}"
        )
        for info in jobs.values()
    }
    assert claimed == expected, (
        f"§1's row and the roster disagree: row only {sorted(claimed - expected)}, "
        f"roster only {sorted(expected - claimed)}"
    )
    for job, info in sorted(jobs.items()):
        if not info["path_declared"]:
            assert info["path"] == DEFAULT_METRICS_PATH, (
                f"{job} relies on the default yet resolves to {info['path']}"
            )


# ────────────────────────────────────────── L12 ──────────────────────────────────────────
def test_the_in_app_otlp_client_is_told_about() -> None:
    """§2 advertises OTEL_OTLP_HTTP_PORT as a conflict fix. The code's own
    default endpoint says 4318, so the sentence owes the reader the env that
    re-points the client — otherwise traces are dropped and nothing alerts."""

    env, url = _client_endpoint()
    port = re.search(r":(\d{2,5})/", url)
    assert port is not None, f"client endpoint default {url!r} carries no port"
    rights = [
        right
        for rec in _service_records("otel-collector")
        for _left, right in _mappings(rec["svc"])
    ]
    assert port.group(1) in rights, (
        f"observability/tracing.py defaults to {url!r} while the collector's "
        f"container ports are {rights}"
    )
    bullet = next((b for b in _sec2_bullets() if env in b), "")
    assert bullet, f"§2 never names {env}, the only way to re-point the client"
    assert "OTEL_OTLP_HTTP_PORT" in bullet, (
        f"§2's {env} bullet does not tie it to the knob whose move strands it"
    )


# ────────────────────────────────────────── L13 ──────────────────────────────────────────
def test_an_image_default_job_still_rests_on_the_image() -> None:
    """'No repo file sets this port' is only true of a specific image. Pin the
    string so a tag bump invalidates the claim instead of rotting under it."""
    jobs = _roster()
    for job, entry in sorted(_IMAGE_DEFAULTS.items()):
        assert job in jobs, f"{job} is declared image-default but nothing scrapes it"
        assert jobs[job]["port"] == int(entry["port"]), (
            f"roster scrapes {job} on {jobs[job]['port']}, the image-default "
            f"table says {entry['port']}"
        )
        recs = _service_records(job)
        assert len(recs) == 1, f"{job} is declared in {len(recs)} compose files"
        svc = recs[0]["svc"]
        assert str(svc.get("image", "")) == entry["image"], (
            f"{job} now runs {(svc.get('image') or '?')!r}, not the {entry['image']!r} "
            f"whose built-in port this unit certifies — re-check the default "
            f"before amending the table"
        )
        command = " ".join(str(c) for c in (svc.get("command") or []))
        flag = entry["override_flag"]
        if flag is None:
            assert "--web.listen-address" not in command, (
                f"{job} now overrides its listen port in the command: {command!r}"
            )
        else:
            assert flag not in command, (
                f"{command!r} overrides the listen port with {flag}, so "
                f"'{job} rests on the image default' is no longer the reason"
            )
        assert len(str(entry["reason"])) > 30, f"{job}'s reason is not a claim"


# ────────────────────────────────────────── L14 ──────────────────────────────────────────
def _gate_220() -> Any:
    """Load #220's gate as a module so both gates can be asked the same thing."""
    spec = importlib.util.spec_from_file_location("sp_gate220", GATE_220)
    assert spec is not None and spec.loader is not None, f"cannot load {GATE_220}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["sp_gate220"] = module
    spec.loader.exec_module(module)
    return module


def test_the_roster_gate_and_this_gate_read_one_population() -> None:
    """Two parsers over one file drift: #220 reads targets and job names, this
    gate reads ports, paths and providers. If they ever disagree about the
    population — or about which jobs our own code serves — each gate would be
    certifying a different deployment."""
    gate = _gate_220()
    theirs: dict[str, dict[str, Any]] = gate._jobs()
    ours = _roster()
    assert set(theirs) == set(ours), (
        f"#220 parses jobs {sorted(theirs)} while this gate parses "
        f"{sorted(ours)} out of the same {PROM_YML}"
    )
    for job in sorted(ours):
        assert str(theirs[job]["metrics_path"]) == ours[job]["path"], (
            f"{job}: #220 reads metrics_path {theirs[job]['metrics_path']!r}, "
            f"this gate reads {ours[job]['path']!r}"
        )
        assert ours[job]["target"] in list(theirs[job]["targets"]), (
            f"{job}: target {ours[job]['target']!r} is not in #220's read of the "
            f"same entry: {theirs[job]['targets']}"
        )
    owners = set(gate._FAMILY_OWNERS["specproof_"])
    served = {job for job, (_rel, _kind) in _PATH_SOURCES.items()}
    assert owners == served, (
        f"#220 says {sorted(owners)} serve specproof_*, this gate's own path "
        f"sources are {sorted(served)} — one of the two is certifying a family "
        f"nobody publishes"
    )
