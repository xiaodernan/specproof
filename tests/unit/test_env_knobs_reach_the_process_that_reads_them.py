"""#257: a knob the operator's inventory advertises must reach the process that
reads it — or the file must say why it does not.

#235 inventories the knobs compose interpolates and proves `.env.example` names
each one; #242 adds the `${X:?}` form and the guard cross-read. Both read
DECLARATIONS: a row that exists, a fallback that matches. Neither can see the
other half of the relation, which is the half an operator acts on — *does the
value I write into `.env` arrive in the container whose code reads it?* Measured
on the HEAD plane before this repair: **44 distinct names — 73 name×service
pairs — that a reachable app module reads and the template advertises had no
carrier in that service's `environment:` map at all** (api 43 pairs, worker 23,
outbox-relay 7). The headline was `ES_HOST`: worker modules build
`ElasticsearchStore()` from it, only api pinned the in-network endpoint, so the
deployed worker fell back to `http://localhost:9200` and every repository-context
retrieval reported the es-unavailable outcome while the operator's `ES_HOST` row
looked like it had been honoured. A stack that boots green, documents its knobs
and answers 200 for weeks can be running with one whole capability silently off.

The repair delivered 48 of those 73 pairs as behaviour-identical carriers (55
compose lines in the first pass, 6 more in the second) and leaves 25 pairs / 13
names deferred, each with a measured reason class and a `#257` sentence above its
row. Two defects in this unit's own instrumentation were found on the way and are
pinned below, because both let a first version of this gate pass while the gap it
exists to close was still open: a `command:` read element-by-element missed
outbox-relay's override and charged it the worker's whole graph, and a census
taken from either single reader scan missed names the other scan resolves
(`CRAFT_MAX_*`/`LLM_MAX_RETRIES`/`CRAFT_TOKEN_BUDGET` through `_env_int` wrappers;
`SPECPROOF_PROVIDER_POLICY` through `source.get(ENV_POLICY)` on an aliased
`os.environ`). The census is the UNION and D01 demands both differences stay real.

The eight clauses are all measured from the files, and the population each one
reads is derived rather than hand-typed:

  * D01 census health - which packages ship comes from `pyproject.toml`'s own
    include list, which process runs comes from compose's `command:` or the
    Dockerfile `CMD` compose does not override, and the import walk from each
    entry must leave no first-party import unresolved. A gate that walks a graph
    has to prove it walked one, and prove the walk is wide enough: per-service
    floors for (reachable modules, environment readers, distinct names).
  * D02 completeness - every name that (a) a module reachable from a service's
    entry reads and (b) `.env.example` rows must be delivered to THAT service,
    or appear in `_DEFERRED` with the reason class this file re-derives. Pinned
    both ways: a knob may not stop being deferred quietly, and a deferral may not
    be claimed for a name that is in fact delivered - or for a name nothing reads.
  * D03 the repair's own contract - each delivered `${X:-V}` (52 such deliveries)
    carries V equal to the template row AND equal to every resolved default the
    shipped readers of X declare. That is what makes the new compose lines
    behaviour-identical for a stack that never sets `.env`, and it is the only
    reason the diff is allowed. The one exemption is borrowed, not invented: a
    name #235's own `_DIVERGENT_DEFAULTS` documents with compose as the carrier.
  * D04 empty pass-throughs - `${X:-}` (14 of them) is the delivery form for an
    optional credential. It is safe only if the row is EMPTY (compose passes the
    literal through, so a `replace_me` row ships `replace_me` as the webhook HMAC
    key) and no shipped reader keys on presence rather than truthiness.
  * D05 pairing - a `_USER`/`_DATABASE` name delivered to an app service (14 of
    them) must also be read by a container that SERVES it, else one `.env` edit
    moves the client's half of a credential pair and not the server's.
  * D06 endpoint literals - the in-network endpoints the app services pin by
    literal must agree with each other, and the worker must be given `ES_HOST`.
  * D07 disclosures point where they exist - every deferred name carries this
    gate's marker in the comment block above its row, and no delivered name
    carries it: a stale "not delivered" note is the same lie told backwards.
  * D08 the backlog that is NOT this unit's repair - 47 names a reachable module
    reads that the template does not advertise at all (no row, not even a
    commented one, and no service pins them as a literal). Advertising each is
    its own argument; the ledger is pinned both ways so the gap cannot grow while
    this unit's headline number is quoted as closed.

Boundaries, stated rather than smoothed: this gate reads declarations and the
static import graph. It starts no container, so "arrives in the container" is
compose's documented `environment:` semantics applied to the parsed file, not a
live `docker compose up` observation - and `env_file:`, which would be a second
carrier, is asserted absent from the scanned set. A name read only through a
runtime `importlib` call is invisible to the walk, which is why D01 demands zero
unresolved first-party imports instead of trusting the graph's shape.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import tomllib
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env.example"
COMPOSE_APP = "compose.production.yml"
COMPOSES = ("compose.phase0.yml", COMPOSE_APP, "compose.observability.yml")
INTERP_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^{}]*))?\}")
NAME_RE = re.compile(r"[A-Z][A-Z0-9_]{2,}\Z")
IDENTITY_SHAPE = re.compile(r"_(USER|DATABASE)$")
# The marker a deferral must leave in the template: it is this gate's own number,
# because that is the artifact an operator follows to find out why a row is inert.
MARKER = "#257"
GATE235 = "tests/unit/test_env_template_binds_the_compose_knobs.py"

# Measured 2026-10-13 off the delivered tree. The reason class is not decoration:
# D02 re-derives each one from the files and reddens if a name stays deferred for
# a different reason than the one recorded here.
_DEFERRED = {
    "LLM_BASE_URL": "presence",
    "LLM_API_KEY": "presence",
    "LLM_MODEL": "presence",
    "LLM_PROTOCOL": "presence",
    "LLM_REASONING_EFFORT": "presence",
    "MYSQL_PORT": "port",
    "MONGODB_PORT": "port",
    "REDIS_PORT": "port",
    "RABBITMQ_PORT": "port",
    "MINIO_PORT": "port",
    "ES_USER": "unpaired",
    # craft/budget.py and craft/llm.py read one name with two caps (200000 / 500000),
    # so `${CRAFT_TOKEN_BUDGET:-200000}` would silence the LLM client's own larger
    # default: no single fallback keeps an untouched stack identical. #235 documents
    # the pair and names budget.py the binding reader; see that gate's table.
    "CRAFT_TOKEN_BUDGET": "mismatch",
    "SPECPROOF_PUBLIC_URL": "mismatch",
}

# Measured 2026-10-13: names a reachable app module reads that `.env.example`
# never advertised, before or after #257. A ledger, not a to-do list. 47 names;
# D08 compares it against a fresh reading of the tree in both directions.
_NO_ROW_LEDGER = frozenset(
    {
        "CRAFT_EXTRA_COMMANDS", "ES_VECTOR_DIMS", "JAVA_HOME",
        "LLM_EMBEDDING_API_KEY", "LLM_EMBEDDING_BASE_URL", "LLM_EMBEDDING_BATCH_SIZE",
        "LLM_EMBEDDING_MODEL", "METRICS_BIND_HOST", "MYSQL_URL",
        "REDIS_STREAM_MAXLEN", "REDIS_STREAM_TTL_SECONDS", "RERANK_CONTENT_CHARS",
        "RERANK_MAX_CANDIDATES", "RERANK_MODEL", "SPECPROOF_ALLOW_LOCAL_TEST_EXEC",
        "SPECPROOF_API_HOST", "SPECPROOF_BILLING_URL", "SPECPROOF_CAPSULE_DIR",
        "SPECPROOF_DATA_DIR", "SPECPROOF_DEEP_REPEATS", "SPECPROOF_EVAL_REPORT_PATH",
        "SPECPROOF_KEEP_VENV", "SPECPROOF_MAX_JSON_BYTES", "SPECPROOF_MAX_REPO_BYTES",
        "SPECPROOF_MODEL_CONFIG", "SPECPROOF_NOTIFY_OUTBOX", "SPECPROOF_NOTIFY_WEBHOOK_KIND",
        "SPECPROOF_NOTIFY_WEBHOOK_SECRET", "SPECPROOF_NOTIFY_WEBHOOK_URL",
        "SPECPROOF_OBJECT_METADATA_BACKEND", "SPECPROOF_OBJECT_METADATA_DB",
        "SPECPROOF_PREFLIGHT", "SPECPROOF_PROVIDER_POLICY", "SPECPROOF_RATE_LIMIT_PER_MIN",
        "SPECPROOF_REPORTS_DIR", "SPECPROOF_REVOCATION_LOG", "SPECPROOF_SANDBOX_CPUS",
        "SPECPROOF_SANDBOX_GO_IMAGE", "SPECPROOF_SANDBOX_GRADLE_IMAGE",
        "SPECPROOF_SANDBOX_MEMORY", "SPECPROOF_SANDBOX_NODE_IMAGE", "SPECPROOF_SANDBOX_PIDS",
        "SPECPROOF_SANDBOX_PYTHON_IMAGE", "SPECPROOF_SIGNING_KEY", "SPECPROOF_SIGNING_KEY_FILE",
        "WORKER_METRICS_PORT", "WORKER_PROVIDER_HOLD_SECONDS",
    }
)

# Measured 2026-10-13: (modules reachable, environment readers, distinct names read)
# per deployed process, as lower bounds. They are per service because the smallest is
# genuinely small - outbox-relay's own graph is 10 modules wide, since compose's
# `command:` override is the only thing separating it from the worker's Dockerfile CMD
# - and one shared floor would have to be set at 4 and would then prove nothing about
# api's 152.
_MIN_POPULATION = {
    "api": (140, 45, 100),
    "worker": (80, 25, 70),
    "outbox-relay": (10, 4, 14),
}


def _text(rel: Path | str) -> str:
    p = rel if isinstance(rel, Path) else ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def parsed(name: str) -> dict:
    doc = yaml.safe_load(_text(name))
    assert isinstance(doc, dict), f"{name} did not parse to a mapping"
    return doc


def shipped_packages() -> list[str]:
    """The packages an installed distribution ships, read from pyproject itself."""
    data = tomllib.loads(_text("pyproject.toml"))
    patterns = data["tool"]["setuptools"]["packages"]["find"]["include"]
    out = [p.rstrip("*") for p in patterns if p.endswith("*") and "*" not in p[:-1]]
    assert len(out) >= 10, f"pyproject include list parsed to {patterns}; the scan read nothing"
    return sorted(out)


def compose_env() -> dict[str, dict[str, str]]:
    """service -> {key: raw value} across the deployed compose set (later wins)."""
    out: dict[str, dict[str, str]] = {}
    for name in COMPOSES:
        for svc, spec in (parsed(name).get("services") or {}).items():
            env = spec.get("environment") or {}
            items = (
                [(str(k), str(v)) for k, v in env.items()]
                if isinstance(env, dict)
                else [(str(e).split("=", 1)[0], str(e)) for e in env]
            )
            for k, v in items:
                out.setdefault(svc, {})[k] = v
    return out


def is_app_service(spec: dict) -> bool:
    return "docker/" in str(spec.get("build", "")) or "python -m" in str(spec.get("command", ""))


def app_services() -> dict[str, dict]:
    services = parsed(COMPOSE_APP).get("services") or {}
    return {n: s for n, s in services.items() if is_app_service(s)}


def entry_module(svc: str) -> str:
    """The process this service runs, from compose or the Dockerfile it names.

    Compose overrides an image command with `command:`; when it does not, the
    image's own CMD is the entry, so a rename in either place moves this gate's
    population - which is why it is derived instead of pinned.
    """
    spec = parsed(COMPOSE_APP)["services"][svc]
    command = spec.get("command") or []
    # Join first: a list-form command is the same shell words, and searching them
    # one at a time never matches `python -m` (which straddles two elements), so
    # every list-form service would silently fall through to its image's CMD.
    # outbox-relay and worker share Dockerfile.worker, whose CMD IS the worker -
    # measuring the relay against it charges the relay the worker's whole graph.
    texts = [" ".join(str(c) for c in (command if isinstance(command, list) else [command]))]
    for text in texts:
        m = re.search(r"python\s+-m\s+([a-zA-Z_][\w.]*)", text)
        if m:
            return m.group(1)
    dockerfile = str(spec["build"]["dockerfile"])
    for line in _text(dockerfile).splitlines():
        if line.strip().upper().startswith("CMD"):
            m = re.search(r"python[\"',\s]+-m[\"',\s]+([a-zA-Z_][\w.]*)", line)
            if m:
                return m.group(1)
    raise AssertionError(f"{svc}: neither a compose command nor a Dockerfile CMD names a module")


@cache
def _tree(path_str: str) -> ast.Module:
    return ast.parse(Path(path_str).read_text(encoding="utf-8", errors="replace"))


def module_paths(packages: tuple[str, ...]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for pkg in packages:
        base = ROOT / pkg
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            rel = p.relative_to(ROOT)
            if rel.parts[-1] == "__init__.py":
                dotted = ".".join(rel.parts[:-1])
            else:
                dotted = ".".join(rel.with_suffix("").parts)
            out[dotted] = p
    return out


PATHS = module_paths(tuple(shipped_packages()))
# Tracked relative path -> dotted module name, so a read site reported by the
# sibling census can be tested against this gate's reach walk.
MODULE_BY_REL = {
    str(p.relative_to(ROOT)).replace("\\", "/"): mod for mod, p in PATHS.items()
}


def imports_of(path: Path, module: str) -> set[str]:
    tree = _tree(str(path))
    base_parts = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                up = (
                    base_parts[: len(base_parts) - (node.level - 1)]
                    if node.level > 1
                    else base_parts
                )
                anchor = ".".join(up)
                if node.module:
                    out.add(f"{anchor}.{node.module}")
                    out |= {f"{anchor}.{node.module}.{a.name}" for a in node.names}
                for a in node.names:
                    if a.name != "*":
                        out.add(f"{anchor}.{a.name}")
            elif node.module:
                out.add(node.module)
                out |= {f"{node.module}.{a.name}" for a in node.names}
    return {t for t in out if t}


def resolve(mod: str) -> str | None:
    parts = mod.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in PATHS:
            return cand
    return None


@cache
def reachable(entry: str) -> tuple[frozenset[str], frozenset[str]]:
    seen: set[str] = set()
    unresolved: set[str] = set()
    packages = {p.split(".")[0] for p in PATHS}
    stack = [entry]
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        path = PATHS.get(mod)
        if path is None or not path.is_file():
            continue
        for target in imports_of(path, mod):
            if target.split(".", 1)[0] not in packages:
                continue
            found = resolve(target)
            if found is None:
                unresolved.add(f"{mod} -> {target}")
            else:
                stack.append(found)
    return frozenset(seen), frozenset(unresolved)


@cache
def regex_reads_in(path_str: str) -> frozenset[str]:
    """Names this module reads through a literal getenv-shaped call.

    This scanner exists only as D01's witness that the census below is the wider
    one: it cannot see `_env_int("CRAFT_TOKEN_BUDGET", DEFAULT_TOKEN_BUDGET)`,
    which is how craft/budget.py reads four of its five knobs, and measuring the
    delivery gap with it alone is how this unit first under-counted its own
    headline number.
    """
    text = _text(path_str)
    names = set(
        re.findall(r"""(?:os\.getenv|os\.environ\.get)\(\s*["']([A-Z][A-Z0-9_]{2,})["']""", text)
    )
    names |= set(re.findall(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]{2,})["']\s*\]""", text))
    names -= set(re.findall(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]{2,})["']\s*\]\s*=""", text))
    consts: dict[str, str] = {}
    for node in _tree(path_str).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            consts[target.id] = node.value.value
    for node in ast.walk(_tree(path_str)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in {"getenv", "get"} or not node.args:
            continue
        first = node.args[0]
        if (
            isinstance(first, ast.Name)
            and first.id in consts
            and NAME_RE.fullmatch(consts[first.id])
        ):
            names.add(consts[first.id])
    return frozenset(n for n in names if NAME_RE.fullmatch(n))


@cache
def code_sites() -> dict[str, list[tuple[str, str | None]]]:
    """name -> [(module, resolved default)] from the repo's authoritative census.

    Gate #235's `code_reads()` walks every tracked production file and resolves
    the wrapper forms this codebase actually uses (`_env_int` / `_env_bool`,
    `os.environ[...]`, env-field mapping dicts, names held in module constants),
    so a knob read through a helper counts as read there. Delivering to a narrower
    private scan would leave a name like `LLM_MAX_RETRIES` advertised, read, and
    carrier-less while both gates stayed green. Sites outside the shipped packages
    (scripts, tools) are dropped: no app service runs them.
    """
    out: dict[str, list[tuple[str, str | None]]] = {}
    for name, sites in gate235().code_reads().items():
        scoped = [(MODULE_BY_REL[rel], default) for rel, default in sites if rel in MODULE_BY_REL]
        if scoped:
            out[name] = scoped
    assert len(out) >= 100, (
        f"the scoped census saw {len(out)} names; the read-site scan read nothing"
    )
    return out


def regex_read_names(svc: str) -> set[str]:
    reach, _unresolved = reachable(entry_module(svc))
    names: set[str] = set()
    for mod in reach:
        p = PATHS.get(mod)
        if p is not None and p.is_file():
            names |= set(regex_reads_in(str(p)))
    return names


def census_read_names(svc: str) -> set[str]:
    reach, _unresolved = reachable(entry_module(svc))
    names: set[str] = set()
    for name, sites in code_sites().items():
        if any(mod in reach for mod, _default in sites):
            names.add(name)
    return names


def read_by(svc: str) -> dict[str, frozenset[str]]:
    """module -> names, over the UNION of both reader scans.

    The two scans disagree in both directions and neither is a superset: the
    sibling census resolves `_env_int("CRAFT_TOKEN_BUDGET", …)` wrappers but not
    `source.get(ENV_POLICY)`, where `source` is a local alias of `os.environ`,
    which the literal-form scan does see. Delivering to either one alone leaves
    the other's names advertised, read, and carrier-less with two green gates, so
    D01 pins that the union is strictly wider than each side.
    """
    reach, _unresolved = reachable(entry_module(svc))
    out: dict[str, set[str]] = {}
    for mod in reach:
        p = PATHS.get(mod)
        if p is not None and p.is_file():
            found = regex_reads_in(str(p))
            if found:
                out.setdefault(mod, set()).update(found)
    for name, sites in code_sites().items():
        for mod, _default in sites:
            if mod in reach:
                out.setdefault(mod, set()).add(name)
    return {mod: frozenset(names) for mod, names in sorted(out.items())}


def read_names(svc: str) -> set[str]:
    names: set[str] = set()
    for r in read_by(svc).values():
        names |= set(r)
    return names


def env_rows() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in _text(ENV).splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def commented_rows() -> set[str]:
    return {
        m.group(1)
        for line in _text(ENV).splitlines()
        if (m := re.match(r"^#\s*([A-Z][A-Z0-9_]{2,})=(\S*)\s*$", line.strip()))
    }


def window_above(row_name: str, *, lines: int = 24) -> str:
    """The comment block directly above `ROW_NAME=`, and nothing else."""
    body = _text(ENV).splitlines()
    for i, line in enumerate(body):
        if line.strip().startswith(f"{row_name}="):
            block: list[str] = []
            for j in range(i - 1, max(-1, i - 1 - lines), -1):
                if body[j].strip().startswith("#"):
                    block.append(body[j])
                    continue
                break
            return "\n".join(reversed(block))
    return ""


def gate235():
    """Import the #235 gate by path for its resolved-default reader, and prove
    WHICH module answered."""
    target = ROOT / GATE235
    spec = importlib.util.spec_from_file_location("gate235_defaults", target)
    assert spec and spec.loader, "cannot load the #235 gate module"
    module = importlib.util.module_from_spec(spec)
    sys.modules["gate235_defaults"] = module
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve() == target.resolve(), (
        f"the sibling scan resolved to {module.__file__}, not {target}"
    )
    return module


@cache
def code_defaults() -> dict[str, frozenset[str]]:
    return {n: frozenset(d for _f, d in sites if d is not None) for n, sites in
            gate235().code_reads().items()}


@cache
def compose_documented_divergence() -> dict[str, str]:
    """Knobs #235 already records as multi-default WITH compose as the documented carrier.

    D03's only exemption, and it is borrowed rather than invented: a `${X:-V}` whose V
    is the template row and compose's documented reading is not this gate inventing a
    default, it is shipping the one the sibling table already names. A name #235
    documents against a code reader instead (CRAFT_TOKEN_BUDGET -> craft/budget.py)
    gets no exemption here, which is exactly why that knob is deferred rather than
    delivered.
    """
    table = gate235()._DIVERGENT_DEFAULTS
    return {
        n: str(spec["readings"]["compose"])
        for n, spec in table.items()
        if spec.get("documented") == "compose" and "compose" in spec.get("readings", {})
    }


@cache
def presence_keyed() -> dict[str, list[str]]:
    """Names a shipped module keys on PRESENCE (`X in os.environ`, `os.environ[X]`).

    An empty string satisfies presence, so such a name cannot be delivered as
    `${X:-}` at all: every container would always see it set.
    """
    out: dict[str, list[str]] = {}
    for _mod, p in sorted(PATHS.items()):
        if not p.is_file():
            continue
        try:
            tree = _tree(str(p))
        except SyntaxError:
            continue
        direct: set[str] = set()
        mapping: set[str] = set()
        iterates = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.In | ast.NotIn):
                comp = node.comparators[0]
                if isinstance(comp, ast.Attribute) and comp.attr == "environ":
                    if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                        direct.add(node.left.value)
                    iterates = True
            elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if node.value.attr == "environ":
                    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                        direct.add(node.slice.value)
                    else:
                        iterates = True
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (
                    node.func.attr == "get"
                    and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "environ"
                ):
                    iterates = True
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Dict):
                    vals = [
                        v for v in node.value.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    ]
                    keys = [str(v.value) for v in vals if NAME_RE.fullmatch(str(v.value))]
                    if keys and len(keys) == len(node.value.values):
                        mapping |= set(keys)
        if iterates:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            for n in direct | mapping:
                if NAME_RE.fullmatch(n):
                    out.setdefault(n, []).append(rel)
    return out


@cache
def published_port_knobs() -> frozenset[str]:
    """Names compose interpolates inside a `ports:` row - host-publish levers."""
    out: set[str] = set()
    for name in COMPOSES:
        for spec in (parsed(name).get("services") or {}).values():
            for row in spec.get("ports") or []:
                text = str(row) if isinstance(row, (str, int)) else str(row.get("published", ""))
                out |= set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", text))
    return frozenset(out)


@cache
def server_interpolated() -> frozenset[str]:
    """Names read by a container that is NOT an app service - the serving half."""
    out: set[str] = set()
    for name in COMPOSES:
        for _svc, spec in (parsed(name).get("services") or {}).items():
            if is_app_service(spec):
                continue
            env = spec.get("environment") or {}
            if isinstance(env, dict):
                out |= {str(k) for k in env}
                for v in env.values():
                    out |= {m.group(1) for m in INTERP_RE.finditer(str(v))}
            else:
                for e in env:
                    out |= {m.group(1) for m in INTERP_RE.finditer(str(e))}
    return frozenset(out)


def delivered(svc: str) -> dict[str, str]:
    return compose_env().get(svc, {})


def interpolated_values(svc: str) -> list[tuple[str, str, str]]:
    """[(name, whole value, fallback)] for a service's `${X:-V}` deliveries.

    The fallback is '' for `${X:-}` and this helper returns the raw compose value
    too, so a name interpolated twice is not silently collapsed.
    """
    out: list[tuple[str, str, str]] = []
    for name, value in sorted(delivered(svc).items()):
        for m in INTERP_RE.finditer(value):
            if m.group(2) is None:
                continue
            out.append((name, value, m.group(2)))
    return out


def defer_class(name: str) -> str:
    """Re-derive WHY this name cannot be delivered today."""
    if name in published_port_knobs():
        return "port"
    if name in presence_keyed():
        return "presence"
    if IDENTITY_SHAPE.search(name) and name not in server_interpolated():
        return "unpaired"
    defaults = code_defaults().get(name, frozenset())
    if defaults and defaults != {env_rows().get(name)}:
        return "mismatch"
    raise AssertionError(
        f"{name} is not deferrable by any measured rule: it is not a host-publish lever, not "
        f"presence-keyed, not an unpaired identity name, and its defaults match its row - "
        f"deliver it instead of recording it"
    )


# ---------------------------------------------------------------------------


def test_D01_the_walk_resolves_the_shipped_graph_it_claims_to_read() -> None:
    """Every number the other clauses quote is a reading of this graph.

    A gate that proves 73 advertised knobs arrived nowhere must first prove it saw
    the processes at all: the package list comes from pyproject, each service's
    entry module from compose or the Dockerfile it names, and the walk must leave no
    first-party import unresolved.
    """
    services = app_services()
    assert set(services) >= {"api", "worker", "outbox-relay"}, sorted(services)
    # outbox-relay and worker are built from the SAME Dockerfile, whose CMD is the
    # worker. Only compose's list-form `command:` separates the two processes, so
    # an entry reader that misses it measures the relay against the worker's whole
    # graph: 77 names instead of its own 14, 64 of them never imported by the relay.
    assert entry_module("outbox-relay") == "storage.outbox_relay", entry_module("outbox-relay")
    assert entry_module("outbox-relay") != entry_module("worker")
    assert {
        services[s]["build"]["dockerfile"] for s in ("worker", "outbox-relay")
    } == {"docker/Dockerfile.worker"}
    for svc in sorted(services):
        floor = _MIN_POPULATION.get(svc)
        assert floor is not None, (
            f"{svc} is an app service this gate has never measured - add its (reachable, "
            f"readers, names) floor after reading it, do not let a new process join the "
            f"census with no population claim"
        )
        entry = entry_module(svc)
        assert entry in PATHS, f"{svc}: entry {entry} is not a shipped module (of {len(PATHS)})"
        reach, unresolved = reachable(entry)
        assert not unresolved, (
            f"{svc}: unresolved first-party imports from {entry}: {sorted(unresolved)} - the "
            f"graph this gate measures is not the graph that ships"
        )
        readers = read_by(svc)
        assert len(reach) >= floor[0], (
            f"{svc}: only {len(reach)} modules reachable from {entry}, floor {floor[0]}"
        )
        assert len(readers) >= floor[1], (
            f"{svc}: only {len(readers)} of them read the environment, floor {floor[1]}"
        )
        assert len(read_names(svc)) >= floor[2], (
            f"{svc}: only {len(read_names(svc))} distinct names read, floor {floor[2]}"
        )
        # The census this gate delivers to must be the UNION of the two reader
        # scans and the difference on each side has to be real read sites: a
        # census that collapses back to either scanner is how this unit twice
        # missed its own gap (CRAFT_* under the literal form, the policy gate
        # under the sibling's call-name form).
        narrow, wide = regex_read_names(svc), census_read_names(svc)
        union = read_names(svc)
        assert narrow <= union and wide <= union, f"{svc}: the census lost a scanner"
        assert union == narrow | wide, f"{svc}: the census is neither scan plus the other"
    craft_only = sorted(read_names("api") - census_read_names("api"))
    assert "CRAFT_TOKEN_BUDGET" not in craft_only, (
        f"CRAFT_TOKEN_BUDGET is read through craft/budget.py's _env_int, so it belongs to the "
        f"sibling census; {craft_only} claims it came only from the literal form"
    )
    api_extra = sorted(read_names("api") - regex_read_names("api"))
    assert "CRAFT_TOKEN_BUDGET" in api_extra, (
        f"craft/budget.py reads CRAFT_TOKEN_BUDGET through _env_int, so its absence from "
        f"{api_extra} means the census no longer resolves wrapper call forms"
    )
    assert len(api_extra) >= 5, f"only {api_extra} census names come from a wrapper form"
    alias_only = sorted(read_names("api") - census_read_names("api"))
    assert "SPECPROOF_PROVIDER_POLICY" in alias_only, (
        f"providers/client_policy.py reads it as source.get(ENV_POLICY) on an aliased "
        f"os.environ, a form the sibling census does not resolve: {alias_only} says this "
        f"gate's own scan no longer contributes it"
    )
    assert len(shipped_packages()) >= 15, shipped_packages()
    with_env_file = [
        n for n in COMPOSES if re.search(r"^\s*env_file:", _text(n), re.M)
    ]
    assert not with_env_file, (
        f"{with_env_file} now carry env_file:, a second carrier this census does not read - "
        f"extend delivered() before trusting D02 again"
    )


def test_D02_every_advertised_knob_reaches_the_service_that_reads_it() -> None:
    """The headline defect class: a row the operator fills and no container sees.

    Per service, not per stack - api having the value is exactly what made
    `ES_HOST` look handled while the worker kept falling back to localhost.
    """
    rows = env_rows()
    for svc in sorted(app_services()):
        keys = set(delivered(svc))
        gap = sorted(n for n in read_names(svc) - keys if n in rows and n not in _DEFERRED)
        assert not gap, (
            f"{svc}: {len(gap)} knob(s) its own code reads and .env.example advertises reach "
            f"no container: {gap}"
        )
    for name, kind in sorted(_DEFERRED.items()):
        readers = [s for s in app_services() if name in read_names(s)]
        assert readers, (
            f"{name} is recorded as deferred but no app service reads it any more - retire "
            f"the ledger row, do not leave a deferral with no subject"
        )
        for svc in readers:
            assert name not in delivered(svc), (
                f"{name} is in the ledger yet {svc} delivers it: the repair landed and the "
                f"table was left behind"
            )
            assert name in rows, f"{name} is deferred but the template carries no row for it"
        measured = defer_class(name)
        assert measured == kind, (
            f"{name}: recorded as {kind!r}, the files say {measured!r} - the reason is part of "
            f"the claim, not decoration"
        )


def test_D03_a_fallback_may_not_invent_a_default_the_code_does_not_share() -> None:
    """The new lines are behaviour-preserving only while V == row == every reader's default."""
    rows = env_rows()
    divergence = compose_documented_divergence()
    exempt_used: set[str] = set()
    checked = 0
    for svc in sorted(app_services()):
        for name, _value, fallback in interpolated_values(svc):
            if name not in read_names(svc):
                continue  # delivered for another reason (a passthrough this process ignores)
            offenders: list[str] = []
            if rows.get(name) != fallback:
                offenders.append(f"the template row is {rows.get(name)!r}")
            defaults = code_defaults().get(name, frozenset())
            if defaults and defaults != {fallback}:
                offenders.append(f"shipped readers default {sorted(defaults)}")
            if offenders and name in divergence and rows.get(name) == fallback == divergence[name]:
                # Only the code-default half is excused, and only where #235 already
                # documents compose as the carrier this stack uses.
                exempt_used.add(name)
            else:
                assert not offenders, (
                    f"{svc}.{name}: compose falls back to {fallback!r} while "
                    f"{' and '.join(offenders)} - an operator who leaves the row alone and a "
                    f"stack with no .env at all would now behave differently from each other"
                )
            checked += 1
    for name in sorted(divergence):
        assert name in exempt_used, (
            f"#235 documents {name} as a compose-documented divergent default (compose reading "
            f"{divergence[name]!r}) but no delivery here relies on that exemption: either the "
            f"divergence has been unified - retire the row in #235 - or the carrier changed "
            f"shape, and D03 is now green about a claim it no longer checks"
        )
    assert checked >= 25, (
        f"only {checked} defaulted deliveries matched a reader: the population this clause "
        f"exists for collapsed - re-aim it rather than letting it pass about nothing"
    )


def test_D04_an_empty_pass_through_needs_an_empty_row_and_a_truthiness_reader() -> None:
    """`${X:-}` passes the operator's value through, and an empty string when unset.

    Two ways that becomes a lie: a row carrying a placeholder ships the
    placeholder (for `GITHUB_WEBHOOK_SECRET` that is a signing secret every
    reader of this repository can compute an HMAC with), and a presence-keyed
    reader cannot distinguish the pass-through from a set value.
    """
    rows = env_rows()
    presence = presence_keyed()
    empties = 0
    for svc in sorted(app_services()):
        for name, value, fallback in interpolated_values(svc):
            if fallback != "" or value != f"${{{name}:-}}":
                continue
            empties += 1
            assert rows.get(name, "") == "", (
                f"{svc} passes {name} through as an empty value while the template row carries "
                f"{rows.get(name)!r}: copying this file ships that string as the credential"
            )
            assert name not in presence, (
                f"{svc} delivers {name} as an empty pass-through but "
                f"{sorted(set(presence[name]))} keys on its presence, where an empty string is "
                f"a SET value - the delivery changes behaviour instead of defaulting it"
            )
    assert empties >= 8, f"only {empties} empty pass-throughs exist; this clause read nothing"


def test_D05_a_credential_identity_an_app_moves_is_a_lever_the_server_moves_too() -> None:
    """One `.env` edit must move both halves of an account, or neither.

    `MYSQL_USER` is interpolated by the mysql container as well as the app, so
    changing it renames the account and the client together. `ES_USER` is not -
    the phase0 server is seeded with `elastic` plus ELASTIC_PASSWORD only - which
    is why it is deferred rather than delivered.
    """
    servers = server_interpolated()
    checked = 0
    for svc in sorted(app_services()):
        for name in sorted(delivered(svc)):
            if not IDENTITY_SHAPE.search(name) or name not in read_names(svc):
                continue
            assert name in servers, (
                f"{svc} delivers {name} but no serving container reads that lever: the client "
                f"would be moved to an account the server was never given"
            )
            checked += 1
    assert checked >= 3, f"only {checked} identity deliveries: this clause read nothing"


def test_D06_the_in_network_endpoints_the_app_services_pin_agree() -> None:
    """Two services pinning one endpoint differently means one of them talks to a
    host that is not in the network.

    `ES_HOST` is the named witness: api pinned it, worker did not receive it at
    all, and the code's own default is `http://localhost:9200` - which inside a
    container is a different machine from the elasticsearch service.
    """
    literals: dict[str, dict[str, str]] = {}
    for svc in sorted(app_services()):
        for name, value in delivered(svc).items():
            if "${" not in value:
                literals.setdefault(name, {})[svc] = value
    for name, by_service in sorted(literals.items()):
        assert len(set(by_service.values())) == 1, (
            f"{name} is pinned to {by_service}: services that disagree about an in-network "
            f"endpoint cannot all be right"
        )
    assert "ES_HOST" in delivered("worker"), (
        "the worker no longer receives ES_HOST: agent/nodes/retrieve_repository_context.py "
        "builds its ElasticsearchStore from that name, so without a carrier it falls back to "
        "http://localhost:9200 and reports the es-unavailable outcome on every request"
    )
    assert literals["ES_HOST"]["worker"] == literals["ES_HOST"]["api"], literals["ES_HOST"]


def test_D07_a_deferral_must_be_written_where_the_operator_will_read_it() -> None:
    """A row that does nothing needs a sentence saying so - and a row that works
    must not keep one.

    Both halves are measured against the comment block directly above the row:
    every ledger name carries this gate's marker, no delivered name does.
    """
    rows = env_rows()
    for name in sorted(_DEFERRED):
        assert name in rows, f"{name} is deferred and must still be a row the operator can see"
        assert MARKER in window_above(name), (
            f"{name} is deferred but the comment block above its row does not disclose it - "
            f"the marker {MARKER} is what sends a reader to the reason"
        )
    read_anywhere = {n for svc in app_services() for n in read_names(svc)}
    for svc in sorted(app_services()):
        for name in sorted(set(delivered(svc)) & read_anywhere):
            if name in _DEFERRED:
                continue
            assert MARKER not in window_above(name), (
                f"{name} reaches {svc} while the block above its row still carries the "
                f"deferral marker: a stale disclosure is a lie told backwards"
            )


def test_D08_the_undeclared_levers_are_a_ledger_not_a_blind_spot() -> None:
    """The other half of the same relation: read by shipped code, un-advertised.

    #257 repairs the knobs the inventory already names. These are named by
    nothing at all - no row, not even a commented-out one - and are not pinned as
    a deployment literal either, so an operator cannot discover them from this
    repository. The ledger pins the set both ways so the gap cannot grow while
    this unit's headline number is quoted as closed.
    """
    declared = set(env_rows()) | commented_rows()
    literals = {k for svc in app_services() for k, v in delivered(svc).items() if "${" not in v}
    measured: set[str] = set()
    for svc in app_services():
        measured |= read_names(svc) - declared - literals
    # Two directions, two different repairs, so a red names its own cause. The
    # reading is of the WORKING TREE: a name this ledger carries can appear or
    # vanish because another lane commits or reverts a reader, and the honest
    # response is to recount at that ref, not to widen the pin.
    retired = sorted(set(_NO_ROW_LEDGER) - measured)
    assert not retired, (
        f"the ledger carries {retired}: that name is no longer an un-advertised lever of "
        f"app reach - either its reader left the tree, it gained a row in .env.example, or "
        f"compose now pins it as a literal. Retire the entry in the same change that did it"
    )
    added = sorted(measured - set(_NO_ROW_LEDGER))
    assert not added, (
        f"shipped code reads {added} with no row, no comment and no literal carrier, and the "
        f"ledger does not know it: an operator cannot discover these from this repository. "
        f"Add each to _NO_ROW_LEDGER (and decide, per #257's classes, whether it can be "
        f"delivered or must stay disclosed)"
    )
