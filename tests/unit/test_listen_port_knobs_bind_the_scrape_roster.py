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
      callers and the tests/** exclusion handed to #427's owner-side census —
      every exempt bind is re-checked by reference, not by this file's shallow
      literal classifier
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
  L15 a listener the roster scrapes for NOBODY: its port collides with no job,
      no deploy file starts its module (over a population whose two armed
      controls prove the scan reads), the exemption is declared in both
      directions, and §2's bullet for it carries the code's own default, the
      roster file, the movability its compose state earns and both gap phrases
  L16 an ops/architecture doc that promises 「独立进程 python -m <module>」 either
      shows a deploy carrier for that module in the same line or says out loud
      that nothing arms it — so a parity claim like 「部署形式同 outbox-relay」
      is graded against the carrier census and cannot be inherited silently

#268 grew L15/L16 because the census behind this unit's queued line
(``_KNOB_SITES`` was missing a third listener) is itself a measurement, and
measuring it found two more things. ``storage/invoice_cron.py`` binds
INVOICE_CRON_METRICS_PORT (code default 9103) through ``self.metrics_port``, a
shape the old resolver could not read at all — the site was invisible twice over.
And once it was readable: 9103 sits in no scrape job, and no compose file,
Dockerfile, host script or CI workflow names ``storage.invoice_cron`` anywhere,
while RUNBOOK.md and DRILLS.md both asserted its 「部署形式同 outbox-relay」 —
outbox-relay being armed by compose.production.yml:183 and start_local.ps1:300.
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
GATE_427 = ROOT / "tests" / "unit" / "test_scrape_roster_ports_answer_their_own_numbers.py"

#: Prometheus scrapes this path unless a job declares ``metrics_path``. External
#: behaviour, named here so L11 can refuse a doc that states a path the config
#: leaves implicit.
DEFAULT_METRICS_PATH = "/metrics"

#: env name -> the scrape job whose listen port it moves, read by the process.
_LISTEN_PORT_KNOBS = {
    "WORKER_METRICS_PORT": "worker",
    "OUTBOX_RELAY_METRICS_PORT": "outbox-relay",
}

#: env name -> (declaring file, dotted module a deploy file would name) for a
#: metrics server this repo builds but the roster scrapes for nobody. L15 keeps
#: the exemption honest in both directions: it re-reads the deploy census and the
#: roster, and either fact changing means the entry leaves this table and joins
#: ``_LISTEN_PORT_KNOBS`` with its job, evidence class and path source.
_UNROSTERED_LISTENERS: dict[str, tuple[str, str]] = {
    "INVOICE_CRON_METRICS_PORT": ("storage/invoice_cron.py", "storage.invoice_cron"),
}

#: Files allowed to start a metrics HTTP server. L2 re-derives this from a
#: repo-wide call-site census, so a third process must be declared here — with
#: its knob, its bullet in §2 and its evidence class — before it can pass.
_KNOB_SITES = ("agent/worker.py", "storage/outbox_relay.py", "storage/invoice_cron.py")

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

#: L15/L16's two gap phrases, spelled once here and required verbatim in the
#: doc. A bullet or a doc line that hedges — 「可能没起」「属部署侧事项」 — says
#: nothing a reader can act on, and reds.
_UNARMED_PHRASE = "尚无部署入口"
_UNSCRAPED_PHRASE = "名册没有作业"

#: Tracked files that could start a process. Written as a pattern over git's own
#: listing, not as a fixed list, so a new Dockerfile or a new host script joins
#: the census by itself; bench/, artifacts/ and demo/ are other people's
#: repositories (evaluation fixtures and the Java demo) and cannot arm our code.
_DEPLOY_POP_RE = re.compile(
    r"^(compose[^/]*\.yml|docker/Dockerfile[^/]*|scripts/[^/]+\.(sh|ps1)|"
    r"[^/]+\.(sh|ps1)|Makefile|\.github/workflows/[^/]+\.yml)$"
)
_NOT_OURS_RE = re.compile(r"^(bench/|artifacts/|demo/|tests/)")

#: docs that make operator-facing promises. The optimization ledger is excluded
#: because it is an append-only record of what was true when each section was
#: written — grading it would force history rewrites — and that exclusion is
#: guarded below by requiring the excluded file really is the ledger.
_LEDGER_MD = "docs/operations/DEEP_OPTIMIZATION_PLAN.md"
_DOC_GLOBS = ("docs/operations", "docs/architecture")
_PROCESS_CLAIM_RE = re.compile(r"独立进程[^。\n]{0,60}?python -m ([a-z0-9_.]+)")

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


# ───────────────────────────────────────── deploy ─────────────────────────────────────────
def _deploy_files() -> list[str]:
    """Tracked files that could start one of our processes.

    A pattern over ``git ls-files`` rather than a fixed tuple: a new Dockerfile or
    host script joins the census by itself. Floored because L15's headline is a
    「0 hits」 claim — an empty population would make every module unarmed.
    """
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    ).stdout.decode("utf-8")
    files = [
        rel
        for rel in listing.splitlines()
        if rel and _DEPLOY_POP_RE.match(rel) and not _NOT_OURS_RE.match(rel)
    ]
    assert len(files) >= 15, f"deploy census collapsed: {files}"
    gone = [rel for rel in files if not (ROOT / rel).is_file()]
    assert not gone, f"git lists these but they are not on disk: {gone}"
    return files


def _module_carriers(module: str) -> list[str]:
    """``file:line`` rows of the deploy census that start ``module``.

    Substring match on purpose: the carriers spell the same entry point three
    different ways — ``CMD ["python", "-m", "agent.worker"]`` in a Dockerfile,
    ``-Arguments @("-m", "agent.worker")`` in a host script, and a list-form
    ``command:`` in compose. A word-boundary regex would have to know each.
    """
    rows: list[str] = []
    for rel in _deploy_files():
        for n, line in enumerate(_lf(rel).splitlines(), 1):
            if module in line:
                rows.append(f"{rel}:{n}")
    return rows


# ────────────────────────────────────────── code ──────────────────────────────────────────
def _call_name(node: ast.Call) -> str | None:
    """The bare callee of a call: ``f(...)`` or ``mod.f(...)``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _env_mapping_base(node: ast.expr) -> bool:
    """Whether the base of a subscript really is the process environment mapping.

    ``os.environ["X"]`` and a bare ``environ["X"]`` qualify. A local dict happens to be
    named ``env`` in this repo — ``scripts/bench_replay.py`` keeps a binary map there
    and reads ``env["python"]`` — so accepting any name would certify a fiction as an
    environment read. The same over-broad acceptance charged
    ``tests/unit/test_scrape_roster_ports_answer_their_own_numbers.py``'s
    ``int(info["port"])`` as a knob named ``port``, which no code in this repo reads.
    """
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"


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
            and _env_mapping_base(sub.value)
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
        # Parse the bytes, not a hand-decoded string: a tracked test file starts with a
        # UTF-8 BOM (tests/unit/test_eval_resume_reuses_measured_cases.py), which
        # Python's own source decoder accepts and ``decode("utf-8")`` keeps as U+FEFF —
        # enough to raise SyntaxError. Measured today: none of the 13 files this census
        # parses carries that BOM, so this buys nothing yet; #427's L6 census, which
        # parses every tracked test, died on it for real.
        tree = ast.parse(raw)
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


def _module_int_constants(tree: ast.Module) -> dict[str, int]:
    """Module-level ``NAME = <int literal>`` bindings, for default resolution."""
    out: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
        ):
            out[target.id] = node.value.value
    return out


def _env_pair(read: ast.expr, consts: dict[str, int], where: str) -> tuple[str, int]:
    """``os.getenv(NAME, DEFAULT)`` as (env name, literal default).

    The default is accepted as a string literal (``"9100"``) or as
    ``str(MODULE_CONST)`` — the shape ``storage/invoice_cron.py`` ships — and a
    constant reference resolves to that module's own literal, so the number this
    gate compares is the number the process binds rather than a copy of it.
    """
    assert isinstance(read, ast.Call) and _call_name(read) == "getenv", (
        f"{where}: expected os.getenv(NAME, DEFAULT), found {_describe(read)} — "
        f"the listen port stopped being an env knob"
    )
    assert len(read.args) == 2 and not read.keywords, (
        f"{where}: getenv needs exactly (name, default), got "
        f"{[_describe(a) for a in read.args]} plus keywords "
        f"{[kw.arg for kw in read.keywords]}"
    )
    name = read.args[0]
    assert isinstance(name, ast.Constant) and isinstance(name.value, str), (
        f"{where}: the env NAME is {_describe(name)}, not a string literal — a "
        f"computed name is a knob no operator can put in .env"
    )
    default = read.args[1]
    text: str | None = None
    if isinstance(default, ast.Constant) and isinstance(default.value, str):
        text = default.value
    elif isinstance(default, ast.Call) and _call_name(default) == "str" and len(default.args) == 1:
        inner = default.args[0]
        assert isinstance(inner, ast.Name) and inner.id in consts, (
            f"{where}: getenv's default is str({_describe(inner)}) and "
            f"{getattr(inner, 'id', '?')!r} is not a module-level int literal — "
            f"the port the process binds has no readable number behind it"
        )
        text = str(consts[inner.id])
    assert text is not None and text.isdigit(), (
        f"{where}: the default reads {text!r}, not a port number — L3 and L7 "
        f"compare it against the roster and the doc, so it must stay literal"
    )
    return str(name.value), int(text)


def _port_env_pair(expr: ast.expr, tree: ast.Module, where: str) -> tuple[str, int]:
    """Resolve a ``port=`` expression to (env name, literal default).

    Shape A — ``int(os.getenv(NAME, "9100"))``, what agent/worker.py and
    storage/outbox_relay.py do.
    Shape B — an attribute the same class assigned once from
    ``int(<param> if <param> is not None else os.getenv(NAME, str(CONST)))``,
    what storage/invoice_cron.py does. Shape B is the one this gate used to be
    blind to: the census saw the file and reported its port expression as
    ``other``, which is how a third listener hid in a gate whose whole job is
    counting listeners. The ctor parameter must be the same name in the guard
    and in the taken branch, so a class that reads the env unconditionally (or
    ignores its injected port) does not pass.
    """
    consts = _module_int_constants(tree)
    unwrapped = _unwrap_int(expr)
    if isinstance(unwrapped, ast.Call):
        return _env_pair(unwrapped, consts, where)
    candidate = expr if unwrapped is None else unwrapped
    assert isinstance(candidate, ast.Attribute), (
        f"{where}: port= is {_describe(expr)}, expected either "
        f"int(os.getenv(NAME, DEFAULT)) or self.<attr> assigned from "
        f"int(<param> if <param> is not None else os.getenv(NAME, DEFAULT)) — an "
        f"unwrapped os.getenv(...) is a string, not a port this census can read"
    )
    attr = candidate.attr
    assigns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Attribute)
            and t.attr == attr
            and isinstance(t.value, ast.Name)
            and t.value.id == "self"
            for t in node.targets
        )
    ]
    assert len(assigns) == 1, (
        f"{where}: self.{attr} is assigned {len(assigns)} times in this "
        f"file — the gate needs exactly one declaration to read the port from"
    )
    inner = _unwrap_int(assigns[0].value)
    assert inner is not None and isinstance(inner, ast.IfExp), (
        f"{where}: self.{attr} = {_describe(assigns[0].value)}, not "
        f"int(<param> if <param> is not None else os.getenv(NAME, DEFAULT))"
    )
    guard = inner.test
    assert (
        isinstance(guard, ast.Compare)
        and len(guard.ops) == 1
        and isinstance(guard.ops[0], ast.IsNot)
        and isinstance(guard.comparators[0], ast.Constant)
        and guard.comparators[0].value is None
        and isinstance(guard.left, ast.Name)
        and isinstance(inner.body, ast.Name)
        and inner.body.id == guard.left.id
    ), (
        f"{where}: the guard reads {_describe(guard)} and the taken branch "
        f"{_describe(inner.body)} — an injected port must win over the env, "
        f"under the same parameter name, or the env is not the knob it claims"
    )
    return _env_pair(inner.orelse, consts, f"{where} (self.{attr})")


def _unwrap_int(node: ast.expr) -> ast.expr | None:
    """``int(x)`` -> ``x``; anything else -> None (the caller says what it saw)."""
    if (
        isinstance(node, ast.Call)
        and _call_name(node) == "int"
        and len(node.args) == 1
        and not node.keywords
    ):
        return node.args[0]
    return None


def _knob_defaults() -> dict[str, tuple[str, int]]:
    """env name -> (declaring file, literal default) for metrics-server calls.

    Each declared site must contain exactly one call whose ``port=`` resolves to
    an env read with a literal default (see ``_port_env_pair`` for the two
    accepted shapes): the env name and the default are the two things a port knob
    moves, so a comment, a log line or a differently-wrapped expression cannot
    satisfy the census — and the failure message names the shape it found.
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
            name, default = _port_env_pair(
                ports[0], tree, f"{rel}:{node.lineno}: port={_describe(ports[0])}"
            )
            found.append((name, default))
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
def _compose_knob_state(knob: str) -> tuple[str, str]:
    """(state, value) for ``knob`` across EVERY service in the compose files.

    L15 needs the movability of a knob that serves no roster job, so there is no
    service name to look it up by; this asks the same literal-or-templated
    question over the whole deploy set instead.
    """
    seen: list[tuple[str, str, str]] = []
    for rel in COMPOSE_FILES:
        services = _yaml(rel).get("services") or {}
        for name, svc in services.items():
            for key, value in (svc.get("environment") or {}).items():
                if str(key) == knob:
                    seen.append((rel, str(name), str(value)))
    if not seen:
        return "absent", ""
    assert len(seen) == 1, f"{knob} is set in more than one place: {seen}"
    value = seen[0][2]
    return ("literal", value) if value.isdigit() else ("templated", value)


# ────────────────────────────────────────── docs ──────────────────────────────────────────
def _doc_files() -> list[str]:
    """Operator-facing docs whose promises L16 grades, ledger excluded.

    The exclusion needs a guard, not a name: DEEP_OPTIMIZATION_PLAN.md is an
    append-only record of what was true at writing time, and grading a history
    entry would force a rewrite. So the clause asserts the excluded file really
    is that ledger, and that nothing else in the tree was quietly dropped.
    """
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    ).stdout.decode("utf-8")
    docs = [
        rel
        for rel in listing.splitlines()
        if rel.startswith(tuple(f"{g}/" for g in _DOC_GLOBS)) and rel.endswith(".md")
    ]
    assert len(docs) >= 20, f"doc census collapsed: {len(docs)} files"
    assert _LEDGER_MD in docs, f"{_LEDGER_MD} is no longer tracked — the exclusion hides nothing"
    headings = len(re.findall(r"^## #\d+", _lf(_LEDGER_MD), re.M))
    assert headings >= 50, (
        f"{_LEDGER_MD} carries {headings} '## #NNN' sections, so it is not the "
        f"optimization ledger this clause exempts — a renamed or replaced ledger "
        f"must not inherit the exemption"
    )
    return [rel for rel in docs if rel != _LEDGER_MD]


def _process_claims() -> list[dict[str, str]]:
    """Doc lines promising an independent process: ``独立进程 … python -m <module>``.

    Keyed on the claim's own wording rather than on the module, because the same
    ``python -m`` spelling legitimately documents a host CLI (``api.identity.cli``)
    that no deployment is supposed to start. #88's rule, inherited here: a claim
    only counts when the doc states it in a form a machine can match.
    """
    out: list[dict[str, str]] = []
    for rel in _doc_files():
        for n, line in enumerate(_lf(rel).splitlines(), 1):
            match = _PROCESS_CLAIM_RE.search(line)
            if match:
                out.append(
                    {"file": rel, "line": str(n), "module": match.group(1), "text": line}
                )
    assert len(out) >= 3, f"process-claim census collapsed: {len(out)} rows"
    return out


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
def _gate_427() -> Any:
    """Load #427's gate: it is the owner of the verdict on what a TEST may bind.

    Loading it is the point, not a convenience — #232 used to judge the tests/** half of
    its own carve-out with ``_port_shape``, a classifier that can only see the literal at
    the call. Measured on the shipped tree it is blind four times over
    (``.scratch/m451_parity.log``): the two ``port=_free_port()`` binds and #427's two
    ``port=int(info["port"])`` binds all read as ``other``, so a test that reached a scrape
    number through a name was invisible here. #427's L6 resolves each of those to ``free``
    or ``roster`` and refuses ``env``/``blind``/``occupied``/``stray``; this clause now asks
    it instead of guessing.
    """
    spec = importlib.util.spec_from_file_location("sp_gate427", GATE_427)
    assert spec is not None and spec.loader is not None, f"cannot load {GATE_427}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["sp_gate427"] = module
    spec.loader.exec_module(module)
    return module


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
    owner = _gate_427()
    rows = {(site.file, site.line): site for site in owner._test_port_sites()}
    for rel, calls in sorted(exempt.items()):
        for line, shape in calls:
            site = rows.get((rel, line))
            assert site is not None, (
                f"{rel}:{line} is a tests/** bind this census enumerates but #427's "
                f"owner-side census does not enumerate ({len(rows)} rows): the "
                "carve-out and the watcher no longer describe one population, so "
                "the exclusion hides whatever the owner stopped seeing"
            )
            if shape.startswith("env:"):
                assert site.kind == "env", (
                    f"{rel}:{line} reads its port from {shape[4:]} for this "
                    f"classifier but #427 resolves the same expression to "
                    f"{site.kind} ({site.detail}): the two readings of an environment "
                    "knob have split, and whichever is wrong an env-fed test is "
                    "either falsely charged or freely exempt"
                )
            assert site.kind not in {"env", "blind"}, (
                f"{rel}:{line} is {site.tag()} — a test either moves a scrape "
                "endpoint with the operator's environment or takes its number from "
                "nowhere readable, and this file's tests/** carve-out is what would "
                "let it pass quietly. Declare the file as a listener (with its knob, "
                "its §2 bullet and its evidence class) instead of exempting it."
            )
    derived = set(_knob_defaults())
    declared = set(_LISTEN_PORT_KNOBS) | set(_UNROSTERED_LISTENERS)
    assert derived == declared, (
        f"the code reads {sorted(derived)} as listen-port knobs but the tables "
        f"declare {sorted(declared)} (rostered {sorted(_LISTEN_PORT_KNOBS)}, "
        f"unrostered {sorted(_UNROSTERED_LISTENERS)})"
    )
    overlap = set(_LISTEN_PORT_KNOBS) & set(_UNROSTERED_LISTENERS)
    assert not overlap, (
        f"{sorted(overlap)} is declared both as a knob a roster job reads and as "
        f"one nobody scrapes — L15's exemption only means something if a name "
        f"lives in exactly one table"
    )


# ─────────────────────────────────────────── L2b ──────────────────────────────────────────
def _port_kwarg(source: str) -> ast.expr:
    """The ``port=`` argument of the single metrics-server call in a source string."""
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "serve_metrics_in_thread"
    ]
    assert len(calls) == 1, f"expected one metrics-server call, found {len(calls)}"
    port = next((kw.value for kw in calls[0].keywords if kw.arg == "port"), None)
    assert port is not None, "the fixture call has no port= keyword"
    return port


def test_the_port_shape_classifier_charges_an_environment_read_and_nothing_else() -> None:
    """The ``env:`` label is all L2's tests/** exemption can refuse, so it must mean one thing.

    L2 refuses a test that starts the metrics server on a port read from the
    environment, because such a test moves a scrape endpoint on the operator's
    machine. The clause therefore rides entirely on ``_port_shape``, and both of its
    failures are silent: too broad, and an honest test gets charged; too narrow, and
    the forbidden shape passes green. The over-broad half is not hypothetical — the
    subscript branch labelled
    ``tests/unit/test_scrape_roster_ports_answer_their_own_numbers.py``'s
    ``int(info["port"])`` as a knob named ``port``, a name no code in this repo reads,
    which would have red-ed L2 the moment that file was tracked. So this case drives the
    classifier from both sides and pins its shipped carriers, because a classifier tested
    only against fixtures can go on certifying a spelling nobody writes.
    """
    scan = _metrics_scan()
    sites = {
        (rel, line): shape
        for rel, info in scan.items()
        if not rel.startswith("tests/")
        for line, shape in info["calls"]
    }
    charged = {key: shape for key, shape in sites.items() if shape.startswith("env:")}
    assert charged, (
        f"no listener site is labelled env: ({sorted(sites.values())}): the "
        "classifier's positive side has no shipped carrier, so a fixture alone would "
        "be certifying a spelling nobody writes"
    )
    defaults = _knob_defaults()
    for (rel, _), shape in sorted(charged.items()):
        knob = shape[4:]
        assert knob in defaults and defaults[knob][0] == rel, (
            f"{rel} reads {shape!r} as its listen port but {knob} is not declared as "
            f"a knob read at {rel} ({defaults.get(knob)}) — the charge names a knob "
            "the census does not know"
        )
    environ_read = _port_kwarg("serve_metrics_in_thread(port=int(os.environ['X_PORT']))")
    assert _port_shape(environ_read) == "env:X_PORT", (
        "an os.environ subscript no longer labels as an environment read: the "
        "spelling scripts/bench_craft.py and cli/specproof/commands/eval.py use would "
        "slip past L2's tests/** exemption green"
    )
    local_dict = _port_kwarg("serve_metrics_in_thread(port=int(env['X_PORT']))")
    assert _port_shape(local_dict) != "env:X_PORT", (
        "a local dict named env labels as the process environment: "
        "scripts/bench_replay.py keeps a binary map under exactly that name "
        "(env['python']), so the charge would name a knob that does not exist"
    )
    roster_leg = ROOT / "tests" / "unit" / "test_scrape_roster_ports_answer_their_own_numbers.py"
    tree = ast.parse(roster_leg.read_bytes())
    coerced = [
        kw.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node) == "serve_metrics_in_thread"
        for kw in node.keywords
        if kw.arg == "port" and any(isinstance(sub, ast.Subscript) for sub in ast.walk(kw.value))
    ]
    assert coerced, (
        "the roster-port leg no longer hands a subscript of a parsed row to port=, so "
        "this classifier has nothing left to distinguish from an environment read"
    )
    shapes = {_port_shape(node) for node in coerced}
    assert shapes == {"other"}, (
        f"the roster leg's own port expression is charged as {sorted(shapes)}: it "
        "reads the number out of #232's roster parse, which is the opposite of an "
        "environment knob, and L2 would refuse the leg that occupies rostered numbers"
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
    unrostered = set(_UNROSTERED_LISTENERS)
    client = {_client_endpoint()[0]}
    known = publish | listen | unrostered | client
    assert named == known, (
        f"§2 names {sorted(named - known)} that no deploy file or default "
        f"declares, and never names {sorted(known - named)} "
        f"(publish: {sorted(publish)}; listen: {sorted(listen)}; unrostered: "
        f"{sorted(unrostered)}; client: {sorted(client)})"
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


# ────────────────────────────────────────── L15 ──────────────────────────────────────────
def test_an_unrostered_listener_earns_its_exemption_and_discloses_it() -> None:
    """The census that found this unit says what it did NOT find, in numbers.

    ``storage/invoice_cron.py`` binds a metrics port, so it had to be declared —
    but declaring it in ``_LISTEN_PORT_KNOBS`` would have been the lie, because
    that table means "a roster job reads this port". The honest slot is this one,
    and L15 keeps it honest from both sides:

    * the exemption must still be true — no job scrapes the port, and no deploy
      file starts the module. Either fact flipping means the entry leaves this
      table and the knob joins the rostered ones with its job and evidence;
    * the gap must be readable — §2 carries one bullet per entry, quoting the
      code's own default, the roster file to edit, the movability compose's own
      state earns, and both gap phrases;
    * the scan must still be able to say 「0 hits」 — the two rostered listeners
      are re-read from the same deploy population as controls, so an empty result
      for the third module is evidence, not a census that lost its population.
    """
    jobs = _roster()
    roster_ports = {info["port"] for info in jobs.values()}
    defaults = _knob_defaults()

    for knob, job in sorted(_LISTEN_PORT_KNOBS.items()):
        site = defaults[knob][0]
        module = site.removesuffix(".py").replace("/", ".")
        rows = _module_carriers(module)
        assert rows, (
            f"{job}'s own process is now started by nothing: no compose file, "
            f"Dockerfile, host script or CI workflow names {module}, yet the "
            f"roster scrapes {jobs[job]['target']} — the armed control this "
            f"clause depends on went unarmed"
        )

    for knob, (site, module) in sorted(_UNROSTERED_LISTENERS.items()):
        assert site in _KNOB_SITES, (
            f"{knob}'s exemption names {site} as its listener, but that file is "
            f"not in _KNOB_SITES, so L2's census never reads it"
        )
        assert knob in defaults, (
            f"the exemption declares {knob} read at {site}, but the AST census "
            f"finds no env-driven metrics call there any more"
        )
        rel, default = defaults[knob]
        assert rel == site, f"{knob} is now read at {rel}, the table says {site}"
        carriers = _module_carriers(module)
        assert not carriers, (
            f"{knob}'s exemption says nothing starts {module}, but the deploy "
            f"census now reads {carriers}: the process is armed, so its metrics "
            f"port needs a real scrape job — move the knob into "
            f"_LISTEN_PORT_KNOBS with its job, evidence class and path source"
        )
        assert default not in roster_ports, (
            f"{site} binds {default} and the roster already scrapes that port "
            f"({sorted(roster_ports)}): two listeners claim one socket, so "
            f"whichever the container wins, one job reads the other's metrics"
        )
        scraped = [job for job, info in jobs.items() if info["port"] == default]
        assert not scraped, (
            f"{knob} is now scraped by {scraped} — the unrostered exemption is "
            f"stale; declare the job in _LISTEN_PORT_KNOBS instead"
        )

        hits = [b for b in _sec2_bullets() if knob in b]
        assert len(hits) == 1, (
            f"§2 must carry exactly one bullet naming {knob}, found {len(hits)}"
        )
        bullet = hits[0]
        assert _ROSTER_FILE in bullet, (
            f"{knob}'s metrics are read only once a job exists: the bullet must "
            f"name {_ROSTER_FILE} as the file to change"
        )
        assert _UNARMED_PHRASE in bullet, (
            f"{knob}'s bullet must state that {_UNARMED_PHRASE} — a knob nobody "
            f"can set is not a knob, and an operator tuning it would be editing "
            f"a port no process binds"
        )
        assert _UNSCRAPED_PHRASE in bullet, (
            f"{knob}'s bullet must state that {_UNSCRAPED_PHRASE} for port "
            f"{default}, or the reader cannot tell a live endpoint from an "
            f"unread one"
        )
        quoted = re.search(r"代码默认 (\d{2,5})", bullet)
        assert quoted is not None, (
            f"{knob}'s bullet quotes no 代码默认, so the number it warns about "
            f"cannot be compared against {site}'s own literal"
        )
        assert int(quoted.group(1)) == default, (
            f"{knob}'s bullet says 代码默认 {quoted.group(1)} while {site} now "
            f"binds {default} — the doc and the code stopped saying one number"
        )
        state, _value = _compose_knob_state(knob)
        assert state != "templated", (
            f"{site} now takes {knob} from a templated compose value ({_value!r}): "
            f"an operator's .env would move an unscraped port, and the bullet's "
            f"whole framing (edit the roster) stops being the fix"
        )
        want, forbid = (
            (_MOVABLE_MARKER, _PINNED_MARKER)
            if state == "absent"
            else (_PINNED_MARKER, _MOVABLE_MARKER)
        )
        assert want in bullet, (
            f"compose sets no {knob} ({state}), so a host run of {module} does "
            f"answer {want} — the bullet has to say it"
        )
        assert forbid not in bullet, (
            f"{knob}'s bullet says {forbid!r} while compose says otherwise "
            f"(state {state!r})"
        )


# ────────────────────────────────────────── L16 ──────────────────────────────────────────
def test_a_promised_independent_process_shows_its_carrier_or_says_it_has_none() -> None:
    """「独立进程 python -m X」 is a deployment promise, and for X =
    ``storage.invoice_cron`` the plane had nothing: RUNBOOK.md and DRILLS.md both
    wrote 「部署形式同 outbox-relay」, outbox-relay being armed by
    compose.production.yml's ``command:`` and by start_local.ps1 — the parity was
    with a shape X does not have.

    The rule is disjunctive on purpose, so it grades docs without inventing
    obligations: a claim is fine if a deploy file really starts the module, and
    fine if the doc says in the same breath that nothing does. What is not fine
    is the third state — a confident sentence about a process no entry point
    arms, disclosed nowhere.
    """
    claims = _process_claims()
    disclosed: list[str] = []
    carried: list[str] = []
    for claim in claims:
        module = claim["module"]
        if _module_carriers(module):
            carried.append(f"{claim['file']}:{claim['line']}")
            continue
        assert _UNARMED_PHRASE in claim["text"], (
            f"{claim['file']}:{claim['line']} promises 独立进程 python -m {module} "
            f"and no deploy file starts it — either add the entry point, or say "
            f"{_UNARMED_PHRASE} in the same sentence so the reader knows the "
            f"process is not shipped"
        )
        disclosed.append(f"{claim['file']}:{claim['line']}")
    assert carried or disclosed, (
        "the census walked every graded doc but found neither a carried nor a "
        "disclosed claim — it read an empty population"
    )
    for knob, (_site, module) in sorted(_UNROSTERED_LISTENERS.items()):
        rows = [
            c for c in claims if c["module"] == module and _UNARMED_PHRASE in c["text"]
        ]
        assert rows, (
            f"L15 exempts {knob} because nothing arms {module}, but no operator-"
            f"facing doc now says {_UNARMED_PHRASE} about it — the table's reason "
            f"has no disclosure behind it, which is how #246's placeholder secret "
            f"read as configured"
        )
    print(f"[#268] process claims: {len(claims)} | carried {len(carried)} "
          f"| disclosed {len(disclosed)}")
