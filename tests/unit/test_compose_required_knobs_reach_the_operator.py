"""#242: a knob compose REFUSES to boot without must reach the operator.

The #235 gate inventories the knobs compose interpolates as `${X:-default}` -
a lever with a fallback. Compose has a second form, `${X:?message}`, which has
no fallback at all: the stack does not start until the operator supplies the
value. That form was invisible to #235's scan, so the strongest lever in the
deployment - `SPECPROOF_API_KEY`, whose absence makes `api/auth.py` answer every
job call with 503 - had no row in `.env.example` and could not get one through
L01. Three claims, all measured from the files:

  * R01 census - only two interpolation operators are used in the compose VALUES
    (parsed, so a comment cannot count as a lever). A third form, or a bare
    `${X}` (which compose fills with an empty string), reddens this clause
    before any other clause can silently ignore it.
  * R02-R05 the required set - every `${X:?}` name has a template row, the set is
    pinned both ways, every refusal message is non-empty (an empty `:?` message
    is compose printing nothing where it should print an instruction), and each
    name is delivered through a service's parsed `environment:` value.
  * R06-R07 the two scans together cover the whole population, and prose cannot
    advertise a lever the inventory omits: a name production code reads and the
    template mentions in a comment must have a row (or a commented-out row an
    operator can uncomment). Admission is the strict row shape, because a
    disclosure sentence that happened to begin `# SPECPROOF_ENV=production ...`
    exempted that arming knob from its own missing row.
  * R08-R09 the guard cross-read - `storage/config_guard.py` refuses production
    boot on nine known default credentials. Two of the template's own rows carry
    exactly those values, so "copy this file and fill in the secrets" boots red
    on a row the file told you to write; those rows must say so. The guard's
    tenth check is presence-only (`if not os.getenv("SPECPROOF_API_KEY")`), so
    its row must stay EMPTY - a `replace_me` placeholder would satisfy a
    truthiness test and ship a publicly known credential.

Boundaries, stated rather than smoothed: this gate reads declarations. It starts
no container, so "compose refuses" is compose's documented `:?` semantics applied
to the parsed file, not a live `docker compose up` observation. The knob's
DELIVERY plane (which rows reach which container) is wider than this unit and is
measured by #243.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / ".env.example"
GATE235 = ROOT / "tests" / "unit" / "test_env_template_binds_the_compose_knobs.py"
GUARD = "storage/config_guard.py"
AUTH = "api/auth.py"
COMPOSES = ("compose.phase0.yml", "compose.production.yml", "compose.observability.yml")

# Every `${NAME...}` in a parsed value, with its operator and its message.
INTERP_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:[-+?]([^{}]*)|\+([^{}]*)|)?\}")

# Names compose requires with no fallback (measured 2026-10-12 off
# compose.production.yml). Pinning the set both ways means a new required knob
# cannot arrive un-inventoried, and a knob relaxed to `:-` cannot go unnoticed.
REQUIRED_KNOBS = frozenset(
    {
        "ES_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "MINIO_ROOT_USER",
        "MONGODB_PASSWORD",
        "MYSQL_PASSWORD",
        "MYSQL_USER",
        "RABBITMQ_PASSWORD",
        "REDIS_PASSWORD",
        "SPECPROOF_API_KEY",
    }
)

# The three names whose ONLY interpolation form is `:?`, so #235's `:-` scan
# never saw them. This is the seam between the two gates; if either regex is
# widened, R06 reddens and says so.
SIBLING_BLIND_SPOT = frozenset({"MINIO_ROOT_PASSWORD", "MINIO_ROOT_USER", "SPECPROOF_API_KEY"})

# Template rows that equal a credential the production guard refuses by value.
# MYSQL_USER/ROOT_USER are not `_PASSWORD`-suffixed, so #235's L03 keeps them
# pinned to compose's fallback - the two rules can only coexist if the file
# says which rows the guard will reject.
GUARD_REFUSED_ROWS = frozenset({"MYSQL_USER", "MINIO_ROOT_USER"})
# The disclosure each of those rows must carry: the artifact that refuses.
DISCLOSES = "storage/config_guard.py"


def _text(rel: Path | str) -> str:
    p = rel if isinstance(rel, Path) else ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def tracked(pattern: str = "") -> list[str]:
    cmd = ["git", "ls-files"] + ([pattern] if pattern else [])
    out = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return [line for line in out.stdout.splitlines() if line]


def _walk_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value)
    elif isinstance(node, str):
        yield node


def parsed(path: Path | str):
    return yaml.safe_load(_text(path))


def operator_of(clause: str | None) -> str:
    """':-d' -> '-', ':?msg' -> '?', '${X}' -> '' (bare)."""
    if not clause:
        return ""
    if clause.startswith(":"):
        return clause[1:2]
    return clause[:1]


def message_of(match: re.Match) -> str:
    return match.group(3) or match.group(4) or ""


def interpolations() -> list[tuple[str, str, str, str]]:
    """[(file, name, operator, message)] for every `${...}` in a parsed value.

    operator is '' for the bare `${NAME}` form and ':' is dropped from `:-`,
    ':?', ':+' so callers key on the operator character.
    """
    out: list[tuple[str, str, str, str]] = []
    for name in COMPOSES:
        doc = parsed(name)
        assert isinstance(doc, dict), f"{name} did not parse to a mapping"
        for text in _walk_strings(doc):
            for m in INTERP_RE.finditer(text):
                out.append((name, m.group(1), operator_of(m.group(2)), message_of(m)))
    assert out, "no ${...} interpolation found in any compose value; the scan read nothing"
    contributed = {f for f, _n, _o, _m in out}
    assert contributed == set(COMPOSES), (
        f"scanned compose files {sorted(set(COMPOSES) - contributed)} contributed no "
        f"interpolation: the walk is not reaching their values"
    )
    return out


def required_names() -> dict[str, list[tuple[str, str]]]:
    """name -> [(file, message)] for the `:?` (no-fallback) form.

    The floor here is what keeps R02 from going green about an empty population:
    if the `:?` form disappears, every other clause in this file reads nothing.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for f, name, operator, message in interpolations():
        if operator == "?":
            out.setdefault(name, []).append((f, message))
    assert out, (
        "no compose knob uses the `:?` required form any more; this gate exists for that "
        "form - re-aim or retire it instead of passing on an empty set"
    )
    return out


def env_rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in _text(ENV).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        rows[key.strip()] = value.strip()
    return rows


# A commented row is a line that IS a row with the `#` added, and nothing else
# on it. The admission is structural on purpose: measured 2026-10-12, a prose
# line inside another row's disclosure happened to begin `# SPECPROOF_ENV=production
# while ...`, so a looser match read that sentence as the arming knob's
# declaration and R07 passed while a live lever stayed un-inventoried.
COMMENTED_ROW_RE = re.compile(r"^#\s*([A-Z][A-Z0-9_]{2,})=(\S*)\s*$")
# Same assignment shape, but the line keeps talking: prose that mimics a row.
LOOKALIKE_RE = re.compile(r"^#\s*([A-Z][A-Z0-9_]{2,})=(\S+)\s+\S")


def commented_rows() -> set[str]:
    """Names the template carries as an uncommented-out row (`# NAME=value`).

    That shape is an inventory entry an operator can enable by deleting a
    character, unlike a name that only appears inside prose.
    """
    return {
        m.group(1)
        for line in _text(ENV).splitlines()
        if (m := COMMENTED_ROW_RE.match(line.strip()))
    }


def row_lookalikes() -> set[str]:
    """Names whose ONLY appearance in a comment begins like an assignment.

    These are deliberately NOT declarations - see `COMMENTED_ROW_RE`. R07
    consumes the set so the mimicry itself cannot become a hiding place.
    """
    return {
        m.group(1)
        for line in _text(ENV).splitlines()
        if (m := LOOKALIKE_RE.match(line.strip()))
    }


def comment_prose_names() -> set[str]:
    """ALL-CAPS tokens the template's comments name, in any shape."""
    out: set[str] = set()
    for line in _text(ENV).splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        for m in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", stripped):
            out.add(m.group(1))
        for m in re.finditer(r"\b([A-Z][A-Z0-9_]{4,})\b", stripped):
            out.add(m.group(1))
    return out


def window_above(row_name: str, *, lines: int = 14) -> str:
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
    """Import the #235 gate by path and prove WHICH module answered."""
    spec = importlib.util.spec_from_file_location("gate235_reader", GATE235)
    assert spec and spec.loader, "cannot load the #235 gate module"
    module = importlib.util.module_from_spec(spec)
    sys.modules["gate235_reader"] = module
    spec.loader.exec_module(module)
    assert Path(module.__file__).resolve() == GATE235.resolve(), (
        f"the sibling scan resolved to {module.__file__}, not {GATE235}"
    )
    return module


def guard_defaults() -> dict[str, str]:
    """{(var, default)} from storage/config_guard.py's own table."""
    tree = ast.parse(_text(GUARD))
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "_DEFAULT_CREDENTIALS":
            for element in node.value.elts:
                if isinstance(element, ast.Tuple) and len(element.elts) == 2:
                    out[element.elts[0].value] = element.elts[1].value
    assert out, f"{GUARD} declares no _DEFAULT_CREDENTIALS; the guard scan read nothing"
    return out


def guard_presence_checks() -> set[str]:
    """Env names validate_production_config() checks for presence only."""
    tree = ast.parse(_text(GUARD))
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "validate_production_config"
        ),
        None,
    )
    assert fn is not None, f"{GUARD} no longer defines validate_production_config; re-aim R09"
    in_table = set(guard_defaults())
    reads: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in {"getenv", "get"}):
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            reads.add(first.value)
    # the table-driven loop reads its names from a variable, not a constant, so
    # it contributes nothing here: what IS a literal in this function is exactly
    # the presence-only family.
    return reads - in_table


def env_names_read_by(file: str) -> set[str]:
    tree = ast.parse(_text(file))
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"getenv", "get"}
        ):
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                out.add(first.value)
        elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            value = node.slice.value
            if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", value):
                out.add(value)
    return out


# --------------------------------------------------------------------------


def test_R01_the_interpolation_operator_census_is_the_two_known_forms():
    """A third operator would make every other clause in this file half-blind.

    `:-` has a fallback, `:?` has none, and a bare `${X}` is neither: compose
    fills it with an empty string, which is how a required secret becomes an
    anonymous one. Measured 2026-10-12: `:-` x33, `:?` x22, nothing else.
    """
    census: dict[str, int] = {}
    for _f, _n, operator, _m in interpolations():
        census[operator or "bare"] = census.get(operator or "bare", 0) + 1
    assert set(census) == {"-", "?"}, (
        f"compose now interpolates with forms {sorted(census)}; this gate only knows "
        f"how to inventory `-` (defaulted) and `?` (required) - extend the clauses "
        "instead of widening the regex alone"
    )
    assert census["?"] >= 9 and census["-"] >= 20, f"form census collapsed: {census}"


def test_R02_every_required_knob_has_a_template_row():
    """The operator's inventory must name the levers that gate the boot.

    Measured before the repair: SPECPROOF_API_KEY is required by
    compose.production.yml (`${SPECPROOF_API_KEY:?set SPECPROOF_API_KEY}`) and
    fail-closed by api/auth.py (503 on every job call), yet appeared in
    .env.example only inside a sentence - no row to fill in.
    """
    rows = env_rows()
    missing = sorted(set(required_names()) - set(rows))
    assert not missing, (
        f"compose refuses to start without {missing}, and .env.example declares no row "
        f"for them; the operator learns the name only from a startup error"
    )


def test_R03_the_required_set_is_pinned_in_both_directions():
    """A knob may not quietly stop being required, nor become required quietly."""
    measured = set(required_names())
    assert measured == set(REQUIRED_KNOBS), (
        f"required (`:?`) knobs are {sorted(measured)} but the table pins "
        f"{sorted(REQUIRED_KNOBS)} - either the deployment stopped demanding one, or "
        f"a new one arrived; both change what a stack needs to boot"
    )


def test_R04_every_refusal_carries_a_message():
    """`${X:?}` with empty text makes compose fail without saying what to do."""
    silent = sorted({(f, n) for f, n, op, m in interpolations() if op == "?" and not m.strip()})
    assert not silent, f"required knobs with an empty `:?` refusal message: {silent}"


def test_R05_a_required_knob_is_delivered_to_the_process_that_needs_it():
    """The requirement must live in a service's environment, not a comment.

    Reading only parsed values is what makes this clause able to see a lever
    being demoted into prose: comment the line out and the requirement is gone.
    """
    delivered: dict[str, set[str]] = {}
    for name in COMPOSES:
        doc = parsed(name)
        for service, body in (doc.get("services") or {}).items():
            env = body.get("environment")
            values = list(env.values()) if isinstance(env, dict) else [str(e) for e in (env or [])]
            for value in values:
                for m in INTERP_RE.finditer(str(value)):
                    if operator_of(m.group(2)) == "?":
                        delivered.setdefault(m.group(1), set()).add(f"{name}:{service}")
    assert delivered, "no `:?` requirement found in any service environment"
    for knob in sorted(required_names()):
        assert knob in delivered, f"{knob} is required somewhere in the file but reaches no service"
    api_receives = delivered["SPECPROOF_API_KEY"]
    assert "compose.production.yml:api" in api_receives, (
        f"api no longer receives SPECPROOF_API_KEY as a required value: {api_receives}"
    )


def test_R06_the_two_knob_scans_together_cover_the_whole_population():
    """#235 sees `:-`; this file sees `:?`; neither alone sees everything.

    Pinned as a partition, so the coverage claim survives someone fixing the
    sibling regex - which would red this clause and say where the coverage moved.
    """
    gate = gate235()
    sibling = set(gate.compose_knobs())
    everyone = {n for _f, n, _o, _m in interpolations()}
    required_only = set(required_names())
    assert sibling | required_only == everyone, (
        f"knob population is {sorted(everyone - sibling - required_only)} served by neither scan"
    )
    blind = required_only - sibling
    assert blind == set(SIBLING_BLIND_SPOT), (
        f"the `:?`-only set #235 cannot see is now {sorted(blind)}, table says "
        f"{sorted(SIBLING_BLIND_SPOT)}: if the sibling regex was widened, move this "
        f"coverage into that gate instead of re-pinning the number here"
    )


def test_R07_prose_may_not_advertise_a_lever_the_inventory_omits():
    """A name the code reads and the file mentions must be fillable in that file.

    Declaration is structural: a row, or a comment line that is exactly
    `# NAME=value` and can be enabled by deleting one character. A sentence that
    merely begins with an assignment is not a declaration. Measured 2026-10-12:
    SPECPROOF_ENV - the switch storage/config_guard.py arms the whole credential
    guard on - appeared only inside another row's disclosure prose, and a loose
    `starts with # NAME=` match read that sentence as its inventory entry.
    """
    gate = gate235()
    code_read = set(gate.code_reads())
    declared = set(env_rows()) | commented_rows()
    advertised = comment_prose_names() & code_read
    undeclared = sorted(advertised - declared)
    assert not undeclared, (
        f"the template's comments name production-read levers it never declares: {undeclared}"
    )
    assert "SPECPROOF_API_KEY" in advertised, (
        "the prose pointer to SPECPROOF_API_KEY disappeared; R07 lost its reason to exist "
        "- re-aim it at the remaining advertised-but-undeclared shape instead of deleting it"
    )
    mimics = sorted(row_lookalikes() - declared)
    assert not mimics, (
        f"comment lines begin `NAME=` for {mimics} while no row or commented row declares "
        f"them: prose that looks like a row is not one, so give the name a real line"
    )


def test_R08_guard_refused_values_in_the_template_are_disclosed():
    """`copy this file` must not boot a production refusal it never warned about.

    storage/config_guard.py refuses SPECPROOF_ENV=production while a credential
    still equals a shipped default. Two template rows are exactly those values:
    MYSQL_USER=specproof (kept there by #235 L03, which pins non-credential rows
    to compose's fallback) and MINIO_ROOT_USER=minioadmin. The refusal is correct;
    the silence is not.
    """
    defaults = guard_defaults()
    clash = {k for k, v in env_rows().items() if k in defaults and v == defaults[k]}
    assert clash == set(GUARD_REFUSED_ROWS), (
        f"template rows carrying a value the production guard refuses by name are "
        f"{sorted(clash)}, table says {sorted(GUARD_REFUSED_ROWS)}"
    )
    for name in sorted(clash):
        window = window_above(name)
        assert DISCLOSES in window, (
            f"{name}= is a value {GUARD} refuses in production, but the comment above the "
            f"row does not name that guard: an operator copying the template gets a boot "
            f"failure pointing at a value the template told them to write"
        )


def test_R09_a_presence_only_credential_is_left_empty_not_placeholdered():
    """`replace_me` passes an existence test, so for this row it is a live key.

    The guard compares nine credentials against known defaults; SPECPROOF_API_KEY
    is not one of them - it is checked as `if not os.getenv(...)`. A template row
    of `replace_me` would therefore satisfy the guard AND make the API accept the
    literal that every reader of this file can guess. The row stays empty, and
    compose's `:?` (which fires on empty as well as unset) keeps the boot honest.
    """
    presence = guard_presence_checks()
    assert presence == {"SPECPROOF_API_KEY"}, (
        f"validate_production_config() now presence-checks {sorted(presence)}; this clause "
        f"was written for the truthiness-only family"
    )
    rows = env_rows()
    offenders = {k: rows[k] for k in sorted(presence) if rows.get(k, "") != ""}
    assert not offenders, (
        f"presence-checked credentials carrying a copyable literal: {offenders} - a "
        f"placeholder here is an accepted production credential, not a hole to fill"
    )
    assert "SPECPROOF_API_KEY" in env_names_read_by(AUTH), (
        f"{AUTH} no longer reads SPECPROOF_API_KEY; the 503 fail-close this row exists for "
        f"may have moved"
    )
