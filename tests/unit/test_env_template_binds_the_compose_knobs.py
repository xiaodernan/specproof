"""#233: `.env.example` must be a complete, non-fake, single-defaulted inventory.

The operator's only list of levers is `.env.example`. Three ways that list can
lie, all measured here against the files that actually move something:

  * incomplete  - a compose file interpolates `${X:-d}` and the template never
                  names X, so the lever exists but is invisible;
  * fake        - the template names X and nothing in the shipped plane ever
                  reads X, so setting it does nothing (and the operator believes
                  it did);
  * two-headed  - X has more than one default across carriers (compose's own
                  `:-d` vs a code literal, or two code readers), so which value
                  you get depends on who runs first, and no single file is wrong.

Everything is derived from the files: knobs from the parsed compose YAML, rows
from the template, code defaults from an AST walk over the *tracked* non-test
plane, scrape targets from `infra/prometheus/prometheus.yml`, install lines from
`docker/Dockerfile.*`. No number in this file is typed from memory; the two
tables that are typed (`_LITERAL_COMPOSE_SECRETS`, `_DIVERGENT_DEFAULTS`) are
pinned against the measurement in both directions, so they cannot quietly shrink
or go stale.

Honest boundaries, stated up front:
  * This gate reads deployment *declarations*. It starts no container, so it
    proves that a name is interpolated / a default is declared, never that a
    running stack agrees. Where a claim needs a live process (does the OTLP
    exporter append `/v1/traces`?) the file says it is unmeasured here instead
    of asserting a semantics.
  * `opentelemetry` is an optional extra and neither shipped Dockerfile installs
    it, so L11 proves the traces pipeline is inert on the shipped plane. That is
    a static reading of the install lines plus the pyproject extra membership -
    it does not depend on this machine's venv, and it is deliberately NOT
    phrased as `init_tracing() is None`, which would pass or fail depending on
    what the test runner happens to have installed.
  * The template documents one carrier per divergent knob; the other readings
    are listed in the table and in the template's own comments, not smoothed
    over.
"""

from __future__ import annotations

import ast
import inspect
import re
import subprocess
import tomllib
from pathlib import Path

import yaml

from storage import env_config as _env_config

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env.example"
COMPOSES = ("compose.phase0.yml", "compose.production.yml", "compose.observability.yml")
PROM = ROOT / "infra" / "prometheus" / "prometheus.yml"
DOCKERFILES = ("docker/Dockerfile.api", "docker/Dockerfile.worker")

KNOB_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)((?::-[^{}\n]*)?)\}")
# Structural admission: a credential row is a name that ENDS in a credential
# suffix. A substring test would also catch CRAFT_TOKEN_BUDGET, which counts
# tokens rather than guarding one.
CRED_SUFFIXES = ("_PASSWORD", "_SECRET", "_KEY")

# compose keeps a literal dev value as the fallback for these seven knobs. That
# is the deployment plane's choice (changing compose needs approval and is out
# of this gate's scope); the template's job is to override every one of them.
_LITERAL_COMPOSE_SECRETS = frozenset(
    {
        "ES_PASSWORD",
        "GRAFANA_ADMIN_PASSWORD",
        "MONGODB_PASSWORD",
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "RABBITMQ_PASSWORD",
        "REDIS_PASSWORD",
    }
)

# Knobs with more than one default in the shipped plane. Keyed by name; the
# value names the carrier the template documents and lists the other readings
# with their source, all of which L10 re-measures.
_DIVERGENT_DEFAULTS = {
    "SPECPROOF_CORS_ORIGINS": {
        "documented": "compose",
        "readings": {
            "compose": "http://localhost:3000",
            "api/server.py": "http://localhost:3000,http://localhost:8000",
        },
        "why": "the deployed stack only sees compose's fallback; the wider code "
        "default applies when the variable is unset outside compose",
    },
    "SPECPROOF_PUBLIC_URL": {
        "documented": "api/routes/admin.py",
        "readings": {
            "cli/specproof/commands/verify.py": "",
            "api/routes/webhooks.py": "",
            "api/routes/admin.py": "http://localhost:8000",
        },
        "why": "three readers of the same name ship two different defaults; the "
        "Check-Run link reader (verify.py) and the webhook reader (webhooks.py) "
        "default to empty while admin.py defaults to its own origin. The template "
        "documents the admin.py reader (its declared value matches that default); "
        "the divergence stands until one default is made authoritative (see #235 "
        "honest boundary on unifying it)",
    },
    "OTEL_EXPORTER_OTLP_ENDPOINT": {
        "documented": "compose",
        "readings": {
            "compose": "http://otel-collector:4318",
            "observability/tracing.py": "http://localhost:4318/v1/traces",
        },
        "why": "the template keeps the value a deployed stack uses; whether the "
        "exporter treats it as a base URL or verbatim is NOT measured here",
    },
    "CRAFT_TOKEN_BUDGET": {
        "documented": "craft/budget.py",
        "readings": {
            "craft/budget.py": "200000",
            "craft/llm.py": "500000",
        },
        "why": "two production caps read one name; the run-level Budget is the "
        "binding one, and the CLI help quotes only the other",
    },
}


def _text(rel: Path | str) -> str:
    p = rel if isinstance(rel, Path) else ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def _walk_strings(node, path: str = ""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def compose_knobs() -> dict[str, list[tuple[str, str]]]:
    """knob -> [(file, fallback)] for every `${X:-d}` in the three composes."""
    out: dict[str, list[tuple[str, str]]] = {}
    for name in COMPOSES:
        doc = yaml.safe_load(_text(name))
        for _path, s in _walk_strings(doc):
            for m in KNOB_RE.finditer(s):
                tail = m.group(2)
                fallback = tail[2:] if tail.startswith(":-") else None
                out.setdefault(m.group(1), []).append((name, fallback))
    return out


def env_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in _text(ENV).splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        rows[k.strip()] = v.strip()
    return rows


def _literal(e: ast.expr | None, consts: dict[str, ast.expr]) -> str | None:
    """Read a default out of the AST, following a module constant when the
    default IS one (`str(DEFAULT_RECLAIM_INTERVAL_SECONDS)` resolves)."""
    if e is None:
        return None
    if isinstance(e, ast.Constant):
        return str(e.value)
    if isinstance(e, ast.Name):
        return _literal(consts.get(e.id), consts)
    if isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.USub):
        inner = _literal(e.operand, consts)
        return "-" + inner if inner is not None else None
    if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "str":
        return _literal(e.args[0], consts) if e.args else None
    if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
        a, b = _literal(e.left, consts), _literal(e.right, consts)
        return a + b if a is not None and b is not None else None
    return None


def tracked(pattern: str = "") -> list[str]:
    cmd = ["git", "ls-files"] + ([pattern] if pattern else [])
    out = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return [line for line in out.stdout.splitlines() if line]


_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{2,}")


def _declared_readers() -> tuple[str, ...]:
    """The ``(NAME, DEFAULT)`` readers ``storage/env_config.py`` declares.

    #471 moved the shipped ``int(os.getenv(NAME, DEFAULT))`` coercions behind that
    module. This census is the proof that a knob advertised to an operator still
    has a reader in the process that starts it, so it has to keep seeing those
    sites: a scan that recognised only the inline spelling reported MYSQL_PORT,
    MINIO_PORT and the worker knobs as unread, and the delivery gates would bless a
    template row nobody consumes. Read from the module's declared surface and
    filtered by its parameter shape, so a renamed or re-shaped helper makes the
    census lose a reader on the same commit that changed it rather than quietly.
    """
    readers: list[str] = []
    for declared in _env_config.__all__:
        obj = getattr(_env_config, declared)
        if isinstance(obj, type) or not callable(obj):
            continue
        params = list(inspect.signature(obj).parameters)
        assert params == ["name", "default"], f"storage/env_config.{declared} takes {params}"
        readers.append(declared)
    assert readers, "storage/env_config.py declares no (name, default) reader"
    return tuple(sorted(readers))


_ENV_CONFIG_READERS = _declared_readers()


def code_reads() -> dict[str, list[tuple[str, str | None]]]:
    """env name -> [(file, literal default | None)] over tracked non-test Python.

    Every carrier is kept: two readers giving one name different defaults is the
    drift L10 reports, and a last-wins dict would hide it. A default of None means
    the name is read but with no declared default (single-arg getenv, a constant
    held in a module name, or an env-field mapping dict): L06 counts the key as a
    reader while L10 skips None values when comparing default values.
    """
    out: dict[str, list[tuple[str, str | None]]] = {}
    files = [f for f in tracked("*.py") if not f.startswith("tests/")]
    assert len(files) > 100, (
        f"AST walk saw only {len(files)} production files; the scan read nothing"
    )
    for rel in files:
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        consts: dict[str, ast.expr] = {}
        env_field_dicts: set[str] = set()
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                consts[node.targets[0].id] = node.value
                # A module-level dict whose values are all env-style strings is an
                # env-field mapping (e.g. _ENV_FIELDS); os.environ[name] is driven
                # from it, so each value is a real reader even without a literal
                # getenv at the call site. The `all(...)` guard keeps ordinary
                # dicts (status codes, config blobs) out.
                if isinstance(node.value, ast.Dict):
                    vals = [
                        v
                        for v in node.value.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    ]
                    if vals and all(_ENV_NAME.fullmatch(v.value) for v in vals):
                        env_field_dicts.add(node.targets[0].id)
        # env-field mapping dicts: every value is read (default unknown).
        for dname in env_field_dicts:
            dval = consts.get(dname)
            if isinstance(dval, ast.Dict):
                for v in dval.values:
                    if (
                        isinstance(v, ast.Constant)
                        and isinstance(v.value, str)
                        and _ENV_NAME.fullmatch(v.value)
                    ):
                        out.setdefault(v.value, []).append((rel, None))
        for node in ast.walk(tree):
            # os.environ["NAME"] subscript access carries no default; record it
            # with a sentinel so L03/L10 see the reader without inventing a value.
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "environ"
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "os"
            ):
                idx = node.slice
                if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
                    key = idx.value
                    if _ENV_NAME.fullmatch(key):
                        # None marks "read, default unknown": L10 skips it when
                        # comparing defaults (a required var is not a divergent
                        # default) while L06 still counts the key as read.
                        out.setdefault(key, []).append((rel, None))
                continue
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "get"
                and isinstance(f.value, ast.Attribute)
            ):
                fname = f"{f.value.attr}.get"
            elif isinstance(f, ast.Attribute):
                fname = f.attr
            elif isinstance(f, ast.Name):
                fname = f.id
            else:
                continue
            if (
                fname not in {"getenv", "environ.get", *_ENV_CONFIG_READERS}
                and not re.match(r"^_?env_", fname)
            ):
                continue
            if not node.args:
                continue
            # The name may be a literal, or a constant holding it
            # (THINKING_MODE_ENV = "LLM_THINKING_MODE" then os.getenv(THINKING_MODE_ENV)).
            key_arg = node.args[0]
            if isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str):
                key = key_arg.value
            elif isinstance(key_arg, ast.Name) and key_arg.id in consts:
                resolved = _literal(consts[key_arg.id], consts)
                key = resolved if isinstance(resolved, str) else None
            else:
                key = None
            if not (isinstance(key, str) and _ENV_NAME.fullmatch(key)):
                continue
            # Default: positional args[1] OR the `default=` keyword used by _env_* helpers.
            d: str | None = None
            if len(node.args) > 1:
                d = _literal(node.args[1], consts)
            else:
                for kw in node.keywords:
                    if kw.arg == "default":
                        d = _literal(kw.value, consts)
            # A single-arg getenv (no default) is still a reader; record None so
            # L06 sees it without it counting as a divergent default in L10.
            out.setdefault(key, []).append((rel, d))
    return out


def scrape_targets() -> dict[str, tuple[str, int]]:
    """roster job -> (host, port) from the deployed prometheus.yml."""
    doc = yaml.safe_load(_text(PROM))
    out: dict[str, tuple[str, int]] = {}
    for job in doc.get("scrape_configs", []):
        for sc in job.get("static_configs", []) or []:
            for tgt in sc.get("targets", []) or []:
                host, _, port = str(tgt).rpartition(":")
                out[str(job["job_name"])] = (host, int(port))
    assert out, "prometheus.yml yielded no scrape targets; the roster scan read nothing"
    return out


def _svc_port_rows() -> dict[str, list[tuple[str, str, str]]]:
    """service -> [(file, host_expr, container_port)] for compose `ports:` rows."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for name in COMPOSES:
        doc = yaml.safe_load(_text(name))
        for svc, body in (doc.get("services") or {}).items():
            for row in body.get("ports", []) or []:
                host, container = _split_port(str(row))
                out.setdefault(svc, []).append((name, host, container))
    return out


def _split_port(row: str) -> tuple[str, str]:
    """Cut a port mapping at its LAST top-level colon, brace-aware."""
    depth = 0
    cut = None
    for i, ch in enumerate(row):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ":" and depth == 0:
            cut = i
    if cut is None:
        return row, row
    return row[:cut], row[cut + 1 :]


# --------------------------------------------------------------------------


def test_L01_every_compose_knob_is_declared_by_the_template():
    """A lever compose honours but the template omits is a lever nobody knows.

    Measured 2026-10-11: 12 of 29 knobs were missing, including the only
    credential whose compose fallback is a literal dev password.
    """
    knobs = compose_knobs()
    rows = env_rows()
    missing = sorted(set(knobs) - set(rows))
    assert not missing, (
        f".env.example omits {len(missing)} of the {len(knobs)} knobs the composes "
        f"interpolate: {missing}. Each one is a live lever with a fallback that no "
        f"operator-visible file names."
    )


def test_L02_the_scanned_compose_set_is_the_whole_deployed_surface():
    """The gate's own file list must equal the tracked compose files.

    Without this, dropping a file from COMPOSE_FILES would silently narrow every
    other clause in this file instead of going red.
    """
    tracked_composes = set(tracked("compose*.yml"))
    assert tracked_composes == set(COMPOSES), (
        f"deployed surface is {sorted(tracked_composes)} but this gate scans "
        f"{sorted(COMPOSES)}: a compose file outside the scan hides its knobs from L01/L03"
    )
    knobs = compose_knobs()
    per_file = {
        c: sum(1 for v in knobs.values() if any(f == c for f, _ in v)) for c in COMPOSES
    }
    assert all(n > 0 for n in per_file.values()), (
        f"a scanned compose contributed no knob: {per_file}"
    )


def test_L03_non_credential_template_rows_equal_the_compose_fallback():
    """Copying the template must reproduce a stack started WITHOUT .env.

    compose's `:-d` is what a deployed stack uses when the row is absent, so the
    template's value is a claim about that default; a remembered number here is
    a second, different default.
    """
    offenders = []
    for knob, uses in sorted(compose_knobs().items()):
        if knob.endswith(CRED_SUFFIXES):
            continue
        fallbacks = {f for _, f in uses}
        assert len(fallbacks) == 1, (
            f"{knob}: the composes give it different fallbacks {sorted(fallbacks)}"
        )
        want = next(iter(fallbacks))
        got = env_rows().get(knob)
        if got != want:
            offenders.append((knob, want, got))
    assert not offenders, (
        f"template value != compose fallback for {offenders}; with these rows the "
        f"template no longer reproduces the deployed defaults"
    )


def test_L04_every_credential_row_is_a_placeholder():
    """No real credential value may live in a file meant to be copied."""
    rows = env_rows()
    offenders = {
        k: v
        for k, v in rows.items()
        if k.endswith(CRED_SUFFIXES) and v not in ("", "replace_me")
    }
    assert not offenders, f"credential rows carrying a value instead of replace_me: {offenders}"


def test_L05_compose_secret_fallbacks_are_pinned_and_all_overridden():
    """compose keeps literal dev passwords; the template must name every one.

    The set is re-measured both ways: a new literal-credential fallback reddens
    this clause, and so does removing one without editing the table here.
    """
    literal = {
        knob
        for knob, uses in compose_knobs().items()
        if knob.endswith(CRED_SUFFIXES)
        and any(f not in (None, "", "replace_me") for _, f in uses)
    }
    assert literal == _LITERAL_COMPOSE_SECRETS, (
        f"compose files now fall back to literals for {sorted(literal)}, table says "
        f"{sorted(_LITERAL_COMPOSE_SECRETS)}: the deployment plane changed, not this gate"
    )
    undeclared = sorted(literal - set(env_rows()))
    assert not undeclared, f"credential knobs with no template row: {undeclared}"


def test_L06_no_template_row_is_a_fake_lever():
    """Every row must be read by something that ships.

    A reader is: a compose file (interpolation or passthrough), production
    Python (AST name), a start script, or a Dockerfile. Docs and tests are not
    readers - a row only a test sets is the #130 fail-open shape on the
    deployment plane. Measured 2026-10-11: four rows had no reader at all, two
    of them naming a *different* variable than the code actually reads.
    """
    readers = {
        "compose": "".join(_text(c) for c in COMPOSES),
        "code": set(code_reads()),
        "script": "".join(
            _text(f)
            for f in tracked()
            if f.endswith((".sh", ".ps1", ".bat")) or Path(f).name.startswith("Dockerfile")
        ),
    }
    orphans = sorted(
        k
        for k in env_rows()
        if k not in readers["code"] and k not in readers["compose"] and k not in readers["script"]
    )
    assert not orphans, (
        f"template rows nothing in the shipped plane reads: {orphans}. Setting them "
        f"changes nothing while the operator believes it did."
    )


def test_L07_the_template_has_no_duplicate_rows():
    """A repeated KEY= is two claims about one lever; the last one wins silently."""
    seen: dict[str, int] = {}
    for line in _text(ENV).splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        seen[s.split("=", 1)[0].strip()] = seen.get(s.split("=", 1)[0].strip(), 0) + 1
    dupes = {k: n for k, n in seen.items() if n > 1}
    assert not dupes, f"duplicate rows in .env.example: {dupes}"


def test_L08_the_container_half_of_every_published_port_is_the_scraped_port():
    """The knob moves the host side; the roster reads the container side.

    `PROMETHEUS_PORT` etc. are class-A publishes (`${X:-p}:p`). The right half is
    what Prometheus's service-name target hits, so if it ever stops equalling
    the roster port, the scrape silently misses - and no #232 clause would see
    it, because that gate reads the roster side of the same relation.
    """
    roster = scrape_targets()
    svc_ports = _svc_port_rows()
    checks = []
    for job, (host, port) in sorted(roster.items()):
        rows = svc_ports.get(host)
        if not rows:
            continue  # class-C/worker-style services expose on the network only
        for f, _host_expr, container in rows:
            if int(container) == port:
                checks.append((job, host, port, f))
    assert checks, f"none of the {sorted(roster)} scrape targets met a published port row"
    for job, host, port, f in checks:
        rows = [r for r in svc_ports[host] if int(r[2]) == port]
        assert len(rows) >= 1, f"{job}: roster port {port} has no container-side row in {f}"
    # the container side is a literal, never a knob: a templated right half would
    # let .env move an endpoint the roster hard-codes.
    templated = [
        (svc, expr)
        for svc, rows in svc_ports.items()
        for _f, expr, container in rows
        if "${" in container
    ]
    assert not templated, f"container-side port is templated (roster would drift): {templated}"


def test_L09_scraped_services_publish_only_through_declared_knobs():
    """Host-publish rows for scraped services must come from the template too.

    Otherwise an operator can republish api/prometheus/otel-collector without
    any record of the lever, and the port that Grafana links to changes under
    the dashboards.
    """
    roster = scrape_targets()
    svc_ports = _svc_port_rows()
    knob_names = set(compose_knobs())
    rows = env_rows()
    unseen = []
    for host, port in sorted({h: p for h, (_h, p) in roster.items()}.items()):
        for _f, host_expr, _container in svc_ports.get(host, []):
            m = KNOB_RE.match(host_expr)
            if not m:
                continue
            knob = m.group(1)
            if knob not in knob_names or knob not in rows:
                unseen.append((host, port, knob))
    assert not unseen, f"published ports of scraped services driven by an undeclared knob: {unseen}"


def test_L10_multi_default_knobs_are_exactly_the_documented_table():
    """One name, several defaults: the table and the files must agree both ways.

    Two families are measured: compose-fallback vs a code literal default, and
    two code readers of the same name. Repairing a divergence without editing
    the table reddens this clause too - the table is a claim about the files.
    """
    knobs = compose_knobs()
    reads = code_reads()
    measured: dict[str, dict[str, str]] = {}
    for knob in sorted(set(knobs) | set(reads)):
        readings: dict[str, str] = {}
        for _f, fallback in knobs.get(knob, []):
            if fallback is not None and not knob.endswith(CRED_SUFFIXES):
                readings["compose"] = fallback
        for rel, default in reads.get(knob, []):
            if default is not None:
                readings[rel] = default
        if len(set(readings.values())) > 1:
            measured[knob] = readings
    assert set(measured) == set(_DIVERGENT_DEFAULTS), (
        f"divergent-default knobs are {sorted(measured)} but the table lists "
        f"{sorted(_DIVERGENT_DEFAULTS)}: a new divergence, or one was repaired and "
        f"the table left behind"
    )
    for knob, table in _DIVERGENT_DEFAULTS.items():
        got = measured[knob]
        assert got == table["readings"], (
            f"{knob}: files say {got}, table says {table['readings']}"
        )
        assert table["documented"] in got, (
            f"{knob}: documented carrier {table['documented']} is not a reader"
        )
        declared = env_rows()[knob]
        carrier_key = (
        "compose" if table["documented"] == "compose" else table["documented"]
    )
        assert declared == got[carrier_key], (
            f"{knob}: the template declares {declared!r} while the carrier it says it "
            f"documents ({table['documented']}) gives {got[carrier_key]!r}"
        )


def test_L11_the_traces_pipeline_is_not_armed_by_the_shipped_images():
    """`pip install .` installs no extras, so opentelemetry is absent in prod.

    That makes OTEL_EXPORTER_OTLP_ENDPOINT inert on the deployed plane: the only
    reader lives behind an import that fails. This is read off the two
    Dockerfiles and pyproject, not off this machine's venv, so CI agrees.
    """
    installs: dict[str, list[str]] = {}
    for df in DOCKERFILES:
        lines = [
            line.strip()
            for line in _text(df).splitlines()
            if re.search(r"pip install|uv pip install|uv install", line)
        ]
        assert lines, (
            f"{df}: no install line found - the scan read nothing and cannot claim 'no extras'"
        )
        installs[df] = lines
    with_extras = {
        df: [line for line in ls if "[" in line.split("install")[-1]]
        for df, ls in installs.items()
    }
    assert all(not v for v in with_extras.values()), (
        f"a Dockerfile now installs an extra: {with_extras}"
    )

    proj = tomllib.loads(_text("pyproject.toml"))
    base_names = {
        re.split(r"[<>=!\[]", s.strip())[0].strip().lower()
        for s in proj["project"]["dependencies"]
    }
    otel_extra = {
        re.split(r"[<>=!\[]", s.strip())[0].strip().lower()
        for s in proj["project"]["optional-dependencies"]["otel"]
    }
    assert not {n for n in base_names if n.startswith("opentelemetry")}, (
        f"opentelemetry is in the base dependencies ("
        f"{sorted(n for n in base_names if n.startswith('opentelemetry'))}) "
        f"- the pipeline is armed now, so L12's disclosure and this clause must be re-aimed"
    )
    assert (
        {n for n in otel_extra if n.startswith("opentelemetry")}
    ), "the otel extra no longer holds opentelemetry"
    assert not (
        base_names & {n for n in otel_extra if n.startswith("opentelemetry")}
    ), "an otel package is in both sets"


def test_L12_the_template_discloses_the_inert_traces_knob():
    """A documented knob that currently moves nothing has to say so where it is read."""
    text = _text(ENV)
    row = next(
        (line for line in text.splitlines() if line.startswith("OTEL_EXPORTER_OTLP_ENDPOINT=")),
        "",
    )
    assert row, "OTEL_EXPORTER_OTLP_ENDPOINT row disappeared from the template"
    block = text[: text.index(row)]
    window = block[-1200:]
    for claim in ("[otel]", "NoOp", "pip install"):
        assert claim in window, (
            f"the traces block above {row} no longer says {claim!r}: the row is "
            f"advertised as a lever while the shipped images never read it"
        )


def test_L13_craft_budget_rows_never_offer_zero_as_no_enforcement():
    """`Budget._env_int` raises on 0, so '0 = unlimited' is a refused claim.

    The row this unit replaced said `0 = no enforcement`; it was never true.
    A comment may *mention* the old phrase to explain why it is gone, but no
    active (non-comment) row may assert it, and no CRAFT_* value may be 0/empty
    (that raises at startup via BudgetError).
    """
    rows = {k: v for k, v in env_rows().items() if k.startswith("CRAFT_")}
    bad = {k: v for k, v in rows.items() if v in ("0", "")}
    assert not bad, f"CRAFT_* rows set to 0/empty would raise at startup: {bad}"
    # The old '0 = no enforcement' claim must not survive as an active row.
    affirmative = [
        ln for ln in _text(ENV).splitlines()
        if "0 = no enforcement" in ln and not ln.strip().startswith("#")
    ]
    assert not affirmative, (
        f"affirmative '0 = no enforcement' claim survives outside a comment: {affirmative}"
    )


def test_L14_worker_reclaim_default_resolves_through_the_constant():
    """compose's fallback must equal what the code's own constant says.

    The default is not a literal at the read site - it is
    `str(DEFAULT_RECLAIM_INTERVAL_SECONDS)` - so a line regex reading the
    `getenv(` call sees no number and this clause silently compares nothing.
    """
    reads = code_reads().get("WORKER_RECLAIM_INTERVAL_SECONDS", [])
    assert reads, (
        "agent/worker.py no longer reads WORKER_RECLAIM_INTERVAL_SECONDS; re-aim this clause"
    )
    worker_defaults = {d for rel, d in reads if rel == "agent/worker.py"}
    assert len(worker_defaults) == 1, (
        f"worker.py gives the reclaim interval several defaults: {worker_defaults}"
    )
    code_default = next(iter(worker_defaults))
    fallbacks = {f for _c, f in compose_knobs()["WORKER_RECLAIM_INTERVAL_SECONDS"]}
    assert fallbacks == {code_default}, (
        f"compose falls back to {sorted(fallbacks)} while agent/worker.py's "
        f"DEFAULT_RECLAIM_INTERVAL_SECONDS resolves to {code_default!r}"
    )
    assert env_rows()["WORKER_RECLAIM_INTERVAL_SECONDS"] == code_default, (
        f"the template declares {env_rows()['WORKER_RECLAIM_INTERVAL_SECONDS']!r}, not the "
        f"{code_default!r} both carriers agree on"
    )


def test_L15_a_knob_read_only_through_the_helper_is_still_counted_as_read():
    """#471 moved the numeric coercions behind ``storage/env_config.py``.

    ``code_reads`` is the census the delivery gates use to say a template row has a
    reader, and the call it now sees is ``int_env(NAME, DEFAULT)`` - no ``getenv``
    token survives at those sites. A recognition rule that only knew the inline
    spelling would report MYSQL_PORT, MINIO_PORT and the worker knobs as unread and
    certify a knob nobody consumes, so this leg is the witness that the derived
    ``_ENV_CONFIG_READERS`` rule fires on the shipped bytes: a scan of the source
    text for the helper spelling, then the census asked for the same pairs.
    """
    pattern = re.compile(
        r"\b(" + "|".join(_ENV_CONFIG_READERS) + r")\(\s*[\"'](" + _ENV_NAME.pattern + r")[\"']"
    )
    sites: set[tuple[str, str]] = set()
    for rel in tracked("*.py"):
        if rel.startswith("tests/") or rel == "storage/env_config.py":
            continue
        for _helper, name in pattern.findall(_text(rel)):
            sites.add((rel, name))
    assert sites, (
        f"no shipped file calls {'/'.join(_ENV_CONFIG_READERS)} with a literal knob, so "
        "this witness is watching nothing"
    )
    reads = code_reads()
    missing = [
        f"{rel}::{name}"
        for rel, name in sorted(sites)
        if not any(r == rel and d is not None for r, d in reads.get(name, []))
    ]
    assert not missing, (
        f"the census lost {missing}: a helper read with a declared default is an "
        "environment read, and an unread-looking knob is a fake lever this gate "
        "would wave through"
    )
    # The informative half: at least one of these names has no inline read of the
    # same knob left in the same file, so the pair above is proved by the helper
    # rule and not by a spelling the old census already recognised.
    helper_only = [
        f"{rel}::{name}"
        for rel, name in sorted(sites)
        if not re.search(
            r"""os\.(?:getenv|environ\.get|environ\[)\s*\(?\s*["']"""
            + re.escape(name)
            + r"""["']""",
            _text(rel),
        )
    ]
    assert helper_only, (
        "every site the census attributes to the helper also still spells the same "
        "knob inline, so this leg would pass on the pre-#471 rule alone and proves "
        "nothing about the new one"
    )
