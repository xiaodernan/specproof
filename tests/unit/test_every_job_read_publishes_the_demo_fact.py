"""#526 — every read that ships a verification-job row publishes the demo fact.

``#525`` gave the demo marker one owner and made the SQL ask for it as a bound
parameter. It left the *where* unanswered: ``is_demo`` is a computed column, so
whether a page can show the 演示 badge depends on which query produced its row.
Measured on the commit before this one (probe + arms in
docs/operations/DEEP_OPTIMIZATION_PLAN.md ## #526): four reads under ``MySQLStore``
hand job rows to the web API, and they project three different key sets —

    search_jobs            11 schema columns + is_demo   (explicit list)
    dashboard_snapshot     11 schema columns + is_demo   (explicit list)
    get_job                all 18 schema columns, NO is_demo   (SELECT *)
    _get_job_unscoped      all 18 schema columns, NO is_demo   (SELECT *)

so the same seeded row is "示例数据" on the list and an ordinary verification on
its own detail page, and ``api.ts`` cannot express that: of the 14 fields in
``interface Job``, 13 are optional, and 11 of those are in fact published by every
one of the four reads. The type therefore documents "the server might not tell
you", and the code that decides whether to label fake data is
``!!job.is_demo`` — an absence and a zero that live in the same branch.

Two measurements from the baseline arms changed what this file had to be. The
first: applying the fix to the *scoped* detail read -- the branch a tenant
deployment actually takes -- and running the whole 545-test population produced
**zero** reds (arm P3, survived). The byte-equality leg in ``test_tenant_auth``
only ever executes the unscoped branch, so no witness in the repository had
looked at the scoped detail projection's column list. That is why group A counts
both ``SELECT *`` reads as production surfaces and why the population it asserts
against is derived from ``api/``, not remembered.

The second: deleting the predicate from ``search_jobs`` (arm P4) turned four
lights red, and all four were the same leg counting statements — three
``len(demo) == 2`` assertions and one ``demo[1]`` index that ``IndexError``'d.
Not one of them was about the predicate. #525 had already made an observation
into a contract, which is how a gate goes red on a *correct* extension and green
on a missing one. Group F keeps that from being re-introduced here, and the two
legs that genuinely guard the demo predicate's shape were amended in place.

This gate pins the contract in the order the planes sit:

  A census     which store methods ship a job row to an HTTP response is DERIVED
               (walk ``api/`` for calls into ``MySQLStore``, keep the ones whose
               reads return job rows) and this file must exercise exactly that
               set; every statement in it that ships a row must carry the column;
  B owner      the predicate text has one definition, in ``contracts/demo_marker``,
               and no read re-inlines it;
  C parameters executed against a fake cursor under three tenant scopes: arity,
               the owner's prefix at the ``LOCATE`` placeholder, nothing hardcoded;
  D the column  answers only 0 or 1 — COALESCE over the NULL that a summary
               without ``retrieval_note`` produces, and no migration may name a
               real ``is_demo`` column, which would silently shadow the alias;
  E cross-plane  every REQUIRED field of ``api.ts``'s ``Job`` is published by every
               read in A, ``is_demo`` is required, and each of the three pages
               that can label a job actually reads the field;
  F neighbours  the two assertions this number had to change still guard the
               property they were written for.
"""

from __future__ import annotations

import ast
import contextlib
import re
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_PROJECT_ROOT),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from contracts.demo_marker import DEMO_NOTE_PREFIX, IS_DEMO_COLUMN  # noqa: E402
from storage.mysql import MySQLStore  # noqa: E402
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope  # noqa: E402
from tests._scan_walk import product_python_files  # noqa: E402

REPO = _PROJECT_ROOT
MYSQL = REPO / "storage" / "mysql.py"
API_TS = REPO / "apps" / "web" / "src" / "api.ts"
PAGES = REPO / "apps" / "web" / "src" / "pages"
MIGRATIONS = REPO / "infra" / "mysql" / "migrations"

#: The production plane a second copy of the predicate could appear in. #541
#: removed the hand-typed tuple: this gate's list held 13 roots and #525's held
#: 14, the difference being `experiments`, and neither opened `mcp`, `ops`,
#: `devtools` or `plugins` — so "exactly one definition in the product" was a
#: claim about two different planes. The roots are now derived from the index by
#: one owner, and the exclusion test reads the path below the walk root, because
#: the old `any(part in SKIP_DIRS for part in path.parts)` returned 302 modules
#: in a normal checkout and 0 in a worktree under `.scratch`.
PRODUCTION_FILES = product_python_files(REPO)

VIEWER = TenantScope("tenant-a", user_id="u1", roles=frozenset({"viewer"}))
#: Columns of ``verification_jobs`` a projection may name. Used to tell a job-row
#: read from a one-column probe; the list is the schema, not a wish.
JOB_COLUMNS = (
    "id", "repo_path", "base_ref", "head_ref", "spec_path", "status", "depth",
    "retry_count", "max_retries", "stale_replaced_by", "last_error", "worker_id",
    "created_at", "updated_at", "summary", "github_check_json", "tenant_id",
    "max_execution_seconds", "is_demo",
)


# ── helpers: fold what the driver would actually send ────────────────────────


class _Folder(ast.NodeVisitor):
    """Every cur.execute(a, b) inside a node, with a and b folded to text."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.calls: list[tuple[str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "execute" and node.args:
            sql = self.fold(node.args[0])
            args = self.fold(node.args[1]) if len(node.args) > 1 else ""
            if "SELECT" in sql.upper():
                self.calls.append((sql, args))
        self.generic_visit(node)

    def fold(self, node: ast.expr) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            # a module-level fragment: resolve it, that is the point of an owner
            value = _module_constants.get(node.id)
            return value if isinstance(value, str) else "<var>"
        if isinstance(node, ast.JoinedStr):
            return "".join(
                v.value if isinstance(v, ast.Constant) else "<var>"
                for v in node.values)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.fold(node.left) + self.fold(node.right)
        return "<var>"


_module_constants: dict[str, Any] = {}


def _load_module_constants(source: str) -> None:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = node.targets[0]
            if isinstance(name, ast.Name):
                with contextlib.suppress(ValueError, SyntaxError):
                    _module_constants[name.id] = ast.literal_eval(node.value)


def _store_method_source(source: str, name: str) -> str:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "MySQLStore":
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    seg = ast.get_source_segment(source, sub)
                    if seg:
                        return seg
    raise AssertionError(f"MySQLStore.{name} is gone")


def executes_in(method: str) -> list[tuple[str, str]]:
    """(sql, param-source) for every SELECT the store method performs."""
    source = MYSQL.read_text(encoding="utf-8")
    _load_module_constants(source)
    return _fold(source, _store_method_source(source, method))


def _fold(source: str, fragment: str) -> list[tuple[str, str]]:
    _load_module_constants(source)
    folder = _Folder(source)
    folder.visit(ast.parse(fragment))
    return folder.calls


def _split_top(cols: str) -> list[str]:
    """Split a SELECT list on depth-0 commas, so `LOCATE(a, b)` stays one item."""
    out, depth, current = [], 0, ""
    for ch in cols:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return [o.strip() for o in out if o.strip()]


def ships_job_rows(sql: str) -> bool:
    """A read over ``verification_jobs`` that returns a row, not a number.

    Aggregate reads (COUNT / GROUP BY) and one-column probes (`tenant_id`,
    `summary`) are excluded: they cannot be a job row, and demanding the demo
    column from them is how a gate starts lying about its own population.
    """
    if "FROM verification_jobs" not in sql:
        return False
    if "COUNT(" in sql.upper() or "GROUP BY" in sql.upper():
        return False
    m = re.search(r"\bSELECT\s+(.*?)\s+FROM\s+verification_jobs", sql, re.S | re.I)
    if not m:
        return False
    cols = m.group(1)
    if re.search(r"^\s*\*", cols):
        return True
    named = [c for c in _split_top(cols)
             if re.search(rf"\b({'|'.join(JOB_COLUMNS)})\b", c)]
    return len(named) >= 2


# ── helpers: execute the store against a cursor that only records ────────────


class _RecordingCursor:
    def __init__(self, log: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.log = log

    def execute(self, sql: str, params: Any = None) -> None:
        self.log.append((str(sql), tuple(params or ())))

    def fetchone(self) -> dict[str, Any]:
        return {"total": 3, "id": "job-1", "status": "QUEUED", "is_demo": 1}

    def fetchall(self) -> list[dict[str, Any]]:
        return [{"id": "job-1", "status": "QUEUED", "is_demo": 1}]

    def close(self) -> None:
        return None


class _RecordingConnection:
    def __init__(self, log: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._log = log

    def __enter__(self) -> _RecordingConnection:
        return self

    def __exit__(self, *_a: Any) -> bool:
        return False

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self._log)


@contextlib.contextmanager
def captured(scope: TenantScope | None) -> Iterator[list[tuple[str, tuple[Any, ...]]]]:
    """Patch the connection on the CLASS, the way #525's capture does.

    An instance-level patch would only be seen by the store this helper built,
    and the legs below construct their own inside the context — the log would
    stay empty and every leg would read that as "the read ships nothing".
    """
    log: list[tuple[str, tuple[Any, ...]]] = []

    @contextlib.contextmanager
    def connection(self: MySQLStore) -> Iterator[_RecordingConnection]:
        yield _RecordingConnection(log)

    original = MySQLStore.connection
    MySQLStore.connection = connection  # type: ignore[method-assign]
    token = TENANT_SCOPE_VAR.set(scope)
    try:
        yield log
    finally:
        TENANT_SCOPE_VAR.reset(token)
        MySQLStore.connection = original  # type: ignore[method-assign]


#: The producers this file exercises. `test_the_exercised_set_equals_the_census`
#: makes this list and the derived census the same set, so a new API-facing job
#: read cannot join the population by being forgotten here.
CALLS: list[tuple[str, Any]] = [
    ("search_jobs", lambda s, _p: s.search_jobs(25, 0, "BLOCKED", "checkout")),
    ("dashboard_snapshot", lambda s, _p: s.dashboard_snapshot(datetime(2026, 9, 18))),
    ("get_job", lambda s, _p: s.get_job("job-1")),
]


# ── helpers: the derived census ──────────────────────────────────────────────


def api_facing_job_reads() -> set[str]:
    """Store methods that an HTTP route reaches AND whose SQL ships a job row."""
    store_source = MYSQL.read_text(encoding="utf-8")
    names = {
        sub.name
        for node in ast.walk(ast.parse(store_source))
        if isinstance(node, ast.ClassDef) and node.name == "MySQLStore"
        for sub in node.body
        if isinstance(sub, ast.FunctionDef)
    }
    called: set[str] = set()
    for path in sorted((REPO / "api").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in names:
                called.add(node.attr)
    ships = set()
    for name in sorted(called):
        for sql, _args in executes_in(name):
            if ships_job_rows(sql):
                ships.add(name)
                break
    return ships


def internal_row_readers() -> set[str]:
    """Private readers reachable from the census within one hop (`get_job`'s
    unscoped branch is the only one that exists today)."""
    source = MYSQL.read_text(encoding="utf-8")
    reachable = set()
    for name in api_facing_job_reads():
        body = _store_method_source(source, name)
        for call in re.findall(r"self\.(_\w+)\(", body):
            try:
                seg = _store_method_source(source, call)
            except AssertionError:
                continue
            if any(ships_job_rows(sql) for sql, _ in _fold(source, seg)):
                reachable.add(call)
    return reachable


# ── helpers: the TS plane ────────────────────────────────────────────────────


def job_interface() -> dict[str, bool]:
    """field -> is_optional, read out of api.ts's `export interface Job`."""
    text = API_TS.read_text(encoding="utf-8")
    body = re.search(r"export interface Job \{(.*?)\n\}", text, re.S)
    assert body, "api.ts no longer exports interface Job — the probe is stale"
    out: dict[str, bool] = {}
    for line in body.group(1).splitlines():
        f = re.match(r"\s*(\w+)(\??):", line)
        if f:
            out[f.group(1)] = f.group(2) == "?"
    return out


def string_constants_containing(needle: str) -> list[tuple[str, int]]:
    """(relpath, lineno) of every executed string constant holding `needle`.

    Docstrings are excluded on purpose: #524 queue ⑤ is about a census saying
    which plane it reads, and prose about the predicate is not a copy of it.
    """
    hits: list[tuple[str, int]] = []
    for path, rel in PRODUCTION_FILES:
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        docs = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef))
            and node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        lines = source.splitlines()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and needle in node.value and id(node) not in docs):
                hits.append((rel, lines[node.lineno - 1].strip()[:110]))
    return hits


def coalesce_column(locate: int, note: str | None, summary_valid: bool) -> int:
    """What the landed column answers, in Python: 0 or 1, never None.

    `LOCATE(x, y) = 1` is `y.startswith(x)` under a case-sensitive collation, and
    SQL NULL propagates: `LOCATE(x, NULL)` is NULL, `NULL = 1` is NULL, and the
    CASE then answers NULL unless COALESCE is in the way.
    """
    if not summary_valid:
        return 0
    if note is None:
        return 0
    return 1 if note.startswith(locate) else 0


# ── A: the census ────────────────────────────────────────────────────────────


def test_the_census_of_api_facing_job_reads_is_not_empty() -> None:
    census = api_facing_job_reads()
    assert {"search_jobs", "dashboard_snapshot", "get_job"} <= census, (
        f"the walk found {sorted(census)}; these three are the reads that put a "
        "job row on the wire — if the walk stopped seeing them, every leg below "
        "is prose"
    )


def test_the_exercised_set_equals_the_census() -> None:
    """The population is derived, and this file must run all of it.

    The point of the equality is the direction that bites when somebody adds a
    fifth read: the census learns it from `api/`, this list does not, and until
    someone adds the call the gate says "you are not covering what ships rows".
    """
    census = api_facing_job_reads()
    exercised = {name for name, _ in CALLS}
    assert exercised == census, (
        f"exercised={sorted(exercised)} but api-facing job reads are "
        f"{sorted(census)} — either a read joined the wire, or the walk broke"
    )


def test_every_statement_that_ships_a_job_row_publishes_the_column() -> None:
    for scope_label, scope in (("viewer", VIEWER), ("auditor", TenantScope(
        "tenant-a", user_id="u2", roles=frozenset({"auditor"}))), ("no scope", None)):
        for name, call in CALLS:
            with captured(scope) as log:
                call(MySQLStore(), DEMO_NOTE_PREFIX)
            rows = [sql for sql, _ in log if ships_job_rows(sql)]
            assert rows, f"{name} shipped no job row under {scope_label}"
            offenders = [sql[:120] for sql in rows if "AS is_demo" not in sql]
            assert not offenders, (
                f"{name} under {scope_label} ships a job row without the demo "
                f"column: {offenders} — a page fed by this read cannot tell "
                "seeded sample data from a real verification"
            )


def test_the_single_job_read_publishes_it_with_no_tenant_scope_too() -> None:
    """`get_job` forks: scoped SQL inline, unscoped through a private helper."""
    helpers = internal_row_readers()
    assert "_get_job_unscoped" in helpers, (
        f"reachable private row readers are {sorted(helpers)}; if the fork moved, "
        "the unscoped branch may be publishing nothing again"
    )
    with captured(None) as log:
        MySQLStore().get_job("job-1")
    rows = [sql for sql, _ in log if ships_job_rows(sql)]
    assert len(rows) == 1, rows
    assert "AS is_demo" in rows[0]


def test_the_aggregate_reads_do_not_publish_it() -> None:
    """The COUNT and the GROUP BYs have no row to label; adding the column there
    would mean paying for a predicate whose result nobody can read."""
    with captured(VIEWER) as log:
        MySQLStore().search_jobs(25, 0, "BLOCKED", "checkout")
        MySQLStore().dashboard_snapshot(datetime(2026, 9, 18))
    aggregates = [sql for sql, _ in log
                  if "FROM verification_jobs" in sql and not ships_job_rows(sql)]
    assert aggregates, "no aggregate read found — this leg stopped meaning anything"
    for sql in aggregates:
        assert "AS is_demo" not in sql, sql[:120]


# ── B: one owner ─────────────────────────────────────────────────────────────


def test_the_census_is_not_blind() -> None:
    """#541: this gate used to floor nothing, so a collapsed walk was invisible.

    In a worktree under ``.scratch`` the hand-typed plane yielded 0 modules and
    four legs of this file answered "there is exactly one owner" about a census
    that had read nothing. #525's gate carried a floor and therefore admitted it
    was blind; the asymmetry is the finding, and the floor is the repair.
    """
    scanned = len(PRODUCTION_FILES)
    rels = {rel for _, rel in PRODUCTION_FILES}
    assert scanned >= 250, f"only {scanned} product modules in the census"
    assert "contracts/demo_marker.py" in rels, (
        "the owner is not even inside the plane the census reads — 'no stray copy' "
        "would then mean 'no scan'"
    )


def test_the_predicate_text_has_exactly_one_definition() -> None:
    hits = string_constants_containing("AS is_demo")
    rels = sorted({rel for rel, _ in hits})
    assert rels == ["contracts/demo_marker.py"], (
        f"the demo column is spelled out in {hits}; #526's whole point is that "
        "which reads compute it is one question with one answer"
    )


def test_no_read_re_inlines_the_predicate() -> None:
    source = MYSQL.read_text(encoding="utf-8")
    inlined = [
        line.strip()[:100] for line in source.splitlines()
        if "CASE WHEN JSON_VALID(summary)" in line
    ]
    assert not inlined, (
        f"storage/mysql.py writes the CASE again ({inlined}); with two spellings "
        "the sites can disagree about what is_demo means and stay green"
    )


def _lookalikes_of_the_525_gate() -> set[str]:
    """The keys of PREFIX_LOOKALIKES, read out of the gate that declares them."""
    gate = (REPO / "tests" / "unit"
            / "test_the_demo_marker_has_one_owner_on_both_sides_of_the_sql.py")
    for node in ast.walk(ast.parse(gate.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if (len(targets) == 1 and isinstance(targets[0], ast.Name)
                and targets[0].id == "PREFIX_LOOKALIKES"):
            return set(ast.literal_eval(value))
    raise AssertionError("the #525 gate no longer declares PREFIX_LOOKALIKES")


def test_the_owner_is_the_only_holder_of_the_prefix_in_sql() -> None:
    offenders = [
        (rel, line) for rel, line in string_constants_containing(DEMO_NOTE_PREFIX)
        if rel != "contracts/demo_marker.py"
    ]
    # Derived, not restated: #525's gate owns the documented lookalikes (the
    # seeder's fallback spec body spells the phrase NOT at position 1, so it is
    # data about the marker rather than a second copy of it). Copying that list
    # here would make this file a second owner of an allowlist — the exact shape
    # this number is filing.
    allowed = _lookalikes_of_the_525_gate()
    assert allowed, "the #525 gate's PREFIX_LOOKALIKES is gone — probe broken"
    extra = {rel for rel, _ in offenders} - allowed
    assert not extra, (
        f"the marker text reached {sorted(extra)} as executed data; #525 allows "
        f"{sorted(allowed)}"
    )


# ── C: executed parameters ───────────────────────────────────────────────────


#: The start of the computed column, used to locate its placeholder. Deliberately
#: not "LOCATE(": the fragment is COALESCEd in #526, and CASE WHEN... is the half
#: #525 already pins, so both gates anchor on the same text.
PROJECTION_ANCHOR = "CASE WHEN JSON_VALID(summary)"


def _placeholder_index(sql: str, fragment: str) -> int:
    return sql[: sql.index(fragment)].count("%s")


def test_the_prefix_arrives_bound_at_the_locate_placeholder() -> None:
    for scope in (VIEWER, None):
        with captured(scope) as log:
            for _name, call in CALLS:
                call(MySQLStore(), DEMO_NOTE_PREFIX)
        # "AS is_demo", not "LOCATE(": search_jobs' COUNT also carries LOCATE(
        # — four of them, for the free-text filter — and its first bound value is
        # the search term. Selecting by the verb instead of the projection is how
        # this leg would have reported 'checkout' as the demo marker forever.
        demo = [(sql, params) for sql, params in log if "AS is_demo" in sql]
        assert demo, f"no is_demo statement executed under scope={scope}"
        for sql, params in demo:
            assert sql.count("%s") == len(params), (
                f"arity mismatch: {sql.count('%s')} placeholders, "
                f"{len(params)} params — mysqlclient raises at the server, not here"
            )
            at = _placeholder_index(sql, PROJECTION_ANCHOR)
            assert params[at] == DEMO_NOTE_PREFIX, (
                f"the value reaching LOCATE is {params[at]!r}, not the owner's "
                f"{DEMO_NOTE_PREFIX!r}"
            )


def test_the_marker_text_appears_in_no_executed_statement() -> None:
    with captured(VIEWER) as log:
        for _name, call in CALLS:
            call(MySQLStore(), DEMO_NOTE_PREFIX)
    offenders = [sql[:90] for sql, _ in log if DEMO_NOTE_PREFIX in sql]
    assert not offenders, f"the marker reached executed SQL text: {offenders}"


def test_the_scoped_single_job_read_keeps_the_tenant_predicate_bound() -> None:
    """The order the driver sees: prefix (SELECT list), then id, then tenant."""
    with captured(VIEWER) as log:
        MySQLStore().get_job("job-1")
    sql, params = log[0]
    assert "(tenant_id = %s OR tenant_id IS NULL)" in sql, sql[:160]
    at = _placeholder_index(sql, "(tenant_id = %s")
    assert params[at] == "tenant-a", (
        f"the tenant reaching the predicate is {params[at]!r}: the demo prefix now "
        "leads the parameter list, and a leg that assumed index 0 would be "
        "witnessing the wrong thing"
    )
    assert params[0] == DEMO_NOTE_PREFIX


# ── D: the column answers 0 or 1 ─────────────────────────────────────────────


def test_the_column_is_coalesced_so_it_cannot_answer_null() -> None:
    assert "COALESCE(" in IS_DEMO_COLUMN, (
        "the predicate lost its COALESCE: a summary that is valid JSON without a "
        "retrieval_note key answers LOCATE(x, NULL) = 1 -> NULL, so the column "
        "would be NULL and `is_demo` required in the API type would be a lie"
    )
    assert "= 1, 0)" in IS_DEMO_COLUMN, IS_DEMO_COLUMN


def test_the_column_shape_agrees_with_startswith_over_note_shapes() -> None:
    notes = [
        (None, False, 0),
        ("", True, 0),
        ("seeded demo data (\u3010\u6f14\u793a\u3011)", True, 1),
        ("Seeded demo data", True, 0),
        ("see the seeded demo note", True, 0),
        ("seeded-demo data", True, 0),
        ("anything", True, 0),
    ]
    for note, valid, expected in notes:
        got = coalesce_column(DEMO_NOTE_PREFIX, note, valid)
        assert got == expected, (note, got, expected)
        assert got in (0, 1)


def test_no_migration_names_an_is_demo_column() -> None:
    """A real column with the alias's name would shadow it, silently.

    `SELECT *, CASE ... AS is_demo` is legal while no such column exists; the
    moment one does, the row dict keeps whichever the driver last saw, and the
    badge starts answering a different question than the predicate.
    """
    offenders = []
    for sql in sorted(MIGRATIONS.glob("*.sql")):
        text = sql.read_text(encoding="utf-8")
        for line in text.splitlines():
            if re.search(r"\bis_demo\b", line) and "verification_jobs" in text:
                offenders.append(f"{sql.name}: {line.strip()[:90]}")
    assert not offenders, (
        f"is_demo is becoming a stored column ({offenders}); fold the predicate "
        "into it and delete the alias, do not let both exist"
    )


# ── E: across the planes ─────────────────────────────────────────────────────


def test_every_required_job_field_is_published_by_every_read() -> None:
    """The contract `api.ts` claims: the type mirrors the response.

    Measured before #526: 14 fields, 1 required, and 13 keys that only some of
    the four reads produce — so the comment "Response shapes (mirror
    api/routes/web.py)" was true of one read out of four.
    """
    optional = {f for f, opt in job_interface().items() if opt}
    required = set(job_interface()) - optional
    assert required, "interface Job has no required field at all"
    for scope in (VIEWER, None):
        for name, call in CALLS:
            with captured(scope) as log:
                call(MySQLStore(), DEMO_NOTE_PREFIX)
            for sql, _params in log:
                if not ships_job_rows(sql):
                    continue
                projected = projection_keys(sql)
                missing = sorted(required - projected)
                assert not missing, (
                    f"{name} ships a job row without required field(s) {missing} "
                    f"under scope={scope}"
                )


def projection_keys(sql: str) -> set[str]:
    m = re.search(r"\bSELECT\s+(.*?)\s+FROM\s+verification_jobs", sql, re.S | re.I)
    assert m, sql[:120]
    cols = m.group(1)
    keys = set()
    for part in _split_top(cols):
        alias = re.search(r"\bAS\s+(\w+)\s*$", part, re.I)
        if alias:
            keys.add(alias.group(1))
        elif re.fullmatch(r"\w+", part):
            keys.add(part)
    if re.search(r"^\s*\*", cols):
        # `SELECT *` carries every column the DDL has; name them from the
        # migrations, not from what the projection happens to spell out.
        keys |= _schema_columns()
    return keys


def _schema_columns() -> set[str]:
    text = (MIGRATIONS / "0001_init.sql").read_text(encoding="utf-8")
    body = text[text.index("CREATE TABLE IF NOT EXISTS verification_jobs"):]
    body = body[: body.index("\n) ENGINE")]
    cols = {
        line.strip().split()[0] for line in body.splitlines()[1:]
        if line.strip() and not line.strip().startswith(
            ("INDEX", "FOREIGN", "PRIMARY KEY", ")"))
    }
    for sql in sorted(MIGRATIONS.glob("0*.sql")):
        if sql.name == "0001_init.sql":
            continue
        for m in re.finditer(r"ALTER TABLE verification_jobs(.*?);",
                             sql.read_text(encoding="utf-8"), re.S):
            for line in m.group(1).splitlines():
                add = re.match(r"ADD COLUMN (\w+) ", line.strip())
                if add:
                    cols.add(add.group(1))
    return cols


def test_is_demo_is_required_in_the_type_the_pages_read() -> None:
    fields = job_interface()
    assert "is_demo" in fields, "interface Job no longer declares is_demo"
    assert not fields["is_demo"], (
        "is_demo is optional again. Every read in the census publishes it, which "
        "is what makes required true; optional is the shape that let a page treat "
        "`absent` and `0` as one branch"
    )
    assert re.search(r"is_demo:\s*boolean \| number;", API_TS.read_text("utf-8")), (
        "the column answers 0/1 from MySQL and a boolean from fakes; the union is "
        "the honest type, deleting it would invent a guarantee"
    )


def test_the_pages_that_can_label_a_job_read_the_field() -> None:
    for page in ("Jobs.tsx", "Dashboard.tsx", "JobDetail.tsx"):
        text = (PAGES / page).read_text(encoding="utf-8")
        assert "demo-label" in text, (
            f"{page} no longer renders the badge: the seeded rows there are "
            "indistinguishable from real verifications"
        )
        assert re.search(r"job\.is_demo", text), f"{page} does not read the column"
        assert "!!job.is_demo" not in text, (
            f"{page} coerces the flag with `!!` again while the type calls it "
            "required — use the value"
        )


#: The product sentence that makes a wrong is_demo a lie rather than a
#: cosmetic miss. Written as escapes so this file stays byte-stable in a
#: tree whose editors disagree about full-width punctuation.
DEMO_PROMISE = (
    r"标有“演示”"
    r"的记录为示例数据"
)


def test_the_promise_still_sits_next_to_a_badge() -> None:
    text = (PAGES / "Dashboard.tsx").read_text(encoding="utf-8")
    assert DEMO_PROMISE in text, (
        "the sentence promising that 演示-labelled records are sample data moved; "
        "the badge and the promise are one contract, not two decorations"
    )


# ── F: the neighbours this number had to change ──────────────────────────────


def test_the_unscoped_read_still_proves_it_has_no_tenant_predicate() -> None:
    """`test_tenant_auth.py` used to pin the SQL byte-for-byte.

    That assertion was the only witness of the detail projection — and it
    witnessed the OLD shape, so the fix could not be made without editing it.
    The property it stood in for is `no scope => no tenant predicate`, which this
    leg re-proves directly, and the neighbour keeps its own version.
    """
    with captured(None) as log:
        MySQLStore().get_job("job-1")
    sql = log[0][0]
    assert "tenant_id" not in sql, sql[:160]
    path = REPO / "tests" / "unit" / "test_tenant_auth.py"
    source = path.read_text(encoding="utf-8")
    # A whole-statement EQUALITY, read out of the syntax tree rather than by
    # grepping the file: the amended leg's own docstring quotes the string it
    # replaced, and a probe that reads prose would make honest documentation
    # impossible — #524's queue (5) is the same distinction.
    tree = ast.parse(source)
    # The shape being forbidden is a whole-statement EQUALITY against the old
    # text, not any mention of it: the amended leg asserts a substring of the
    # projection it now sends, which is exactly the kind of witness #526 needs.
    byte_pins = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq)):
            continue
        comparator = node.comparators[0]
        if (isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
                and "verification_jobs WHERE id = %s" in comparator.value
                and "queries" in ast.unparse(node.left)):
            byte_pins.append(ast.unparse(node))
    assert not byte_pins, (
        f"the byte-identity leg is back ({byte_pins}): it makes the detail "
        "projection's old shape load-bearing, which is the thing #526 had to move"
    )
    assert "tenant_id" in source, (
        "the neighbour no longer asserts anything about scoping — trading a "
        "witness for a pass is not an amendment"
    )


def test_the_525_gate_no_longer_hardcodes_the_statement_count() -> None:
    gate = (REPO / "tests" / "unit"
            / "test_the_demo_marker_has_one_owner_on_both_sides_of_the_sql.py"
            ).read_text(encoding="utf-8")
    hard = re.findall(r"len\(demo\) == \d", gate)
    assert not hard, (
        f"the #525 gate pins the count of demo statements ({hard}); that number "
        "was an observation about which reads existed on #525's base, and a "
        "literal it is a wall against exactly this kind of extension"
    )
    assert ">= 2" in gate, "the count floor went too: now the leg cannot fail loudly"


def test_the_star_reads_are_still_star_reads() -> None:
    """Deliberate: the detail plane keeps `SELECT *`, so a migration's new column
    reaches it without a code edit. Only the demo column is added by name."""
    source = MYSQL.read_text(encoding="utf-8")
    scoped = [sql for sql, _ in executes_in("get_job") if ships_job_rows(sql)]
    unscoped = [
        sql for sql, _ in _fold(
            source, _store_method_source(source, "_get_job_unscoped"))
        if ships_job_rows(sql)
    ]
    assert len(scoped) == 1 and len(unscoped) == 1
    for sql in scoped + unscoped:
        assert re.search(r"SELECT \*, ", sql), sql[:140]
