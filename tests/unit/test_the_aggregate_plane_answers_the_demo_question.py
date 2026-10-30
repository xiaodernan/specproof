"""#542 — the aggregate plane has to answer the demo question too.

#525 gave the marker one owner and made MySQL ask for it as a bound parameter.
#526 moved the *column* to that owner and rostered the four reads that ship a
job row. Both numbers drew the line at the same place, and #526 wrote the reason
down: an aggregate "has no row to label; adding the column there would mean
paying for a predicate whose result nobody can read".

That reason is what this file files away. It is drawn along the wrong axis. The
question a read has to answer is not "does a row come out of me that somebody
could badge" — it is "does a *number* come out of me that somebody renders as
real work". Three statements aggregate ``verification_jobs``:

    search_jobs            COUNT(*) AS total            -> the list's own page count
    dashboard_snapshot     status, COUNT(*) AS n        -> 累计验收 / 验收通过 / 发现风险
    dashboard_snapshot     hour, COUNT(*), SUM(failed)  -> 交付动态 近 24 小时

and none of them asks the demo question, while ``api/routes/web.py`` folds the
second into ``jobs.total``, ``jobs.by_status`` and all three rates, and the third
into ``timeline_24h``. The seeded rows are the ones that make this bite rather
than theoretical: ``scripts/seed_demo.py`` writes no ``tenant_id``, so
``(tenant_id = %s OR tenant_id IS NULL)`` lets a seeded row into *every* tenant's
aggregate, and one of its three statuses is literally ``BLOCKED`` — a fresh
install therefore renders 发现风险 = 1 for a risk that was invented to teach the
page, while README and the dashboard's own footnote promise that a row labelled
演示 is sample data and not this repository's verification result.

So the line moves, and it moves in both directions at once:

* the two dashboard aggregates must answer the question — as a *count*
  (``SUM(flag) AS demo_jobs``), not as a per-row label;
* the list ``COUNT`` must keep answering only about the population it pages,
  which demonstrably *includes* seeded rows, because the rows next to that number
  carry their own 演示 badge. Leaving it silent is a decision with a reason in it,
  so this file pins that reason too, and a leg pins that the reason is not
  allowed to grow back into "aggregates don't need it".

The failure this closes is asymmetric in the way #525's was, and no exception
fires either way. A rename on the read side made seeded rows render as real
verifications; a missing column here makes a *statistic* claim that three
fabricated verifications happened — and the number is smaller than the truth it
replaced, so nothing about it looks wrong. Two further shapes are pinned because
they are the ones that would come back: the fold reading the column with a
default (a silently absent demo count is the same 0 as "no seeded rows"), and
the degraded branch answering a *different key set* than the happy branch.

Not folded in: ``api/agent_runtime.py``'s ``is_demo = not repo_path.strip()``
(the agent console's own table, never reached by this predicate), and any
frontend change — ``apps/web`` renders what the fold answers, and this number
deliberately adds no payload key the type does not already declare, so the split
is audited here rather than shipped unread.
"""

from __future__ import annotations

import ast
import contextlib
import re
import sys
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from api.routes.web import dashboard  # noqa: E402
from contracts import demo_marker  # noqa: E402
from contracts.demo_marker import (  # noqa: E402
    DEMO_NOTE_PREFIX,
    IS_DEMO_COLUMN,
    IS_DEMO_COUNT,
    IS_DEMO_FAILED,
    IS_DEMO_FLAG,
    seeded_demo_note,
)
from storage.mysql import MySQLStore  # noqa: E402
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope  # noqa: E402
from tests._scan_walk import product_python_files  # noqa: E402

REPO = _PROJECT_ROOT
MYSQL = REPO / "storage" / "mysql.py"
WEB = REPO / "api" / "routes" / "web.py"
API_TS = REPO / "apps" / "web" / "src" / "api.ts"
GATE_526 = REPO / "tests" / "unit" / "test_every_job_read_publishes_the_demo_fact.py"

VIEWER = TenantScope("tenant-a", user_id="u1", roles=frozenset({"viewer"}))

#: The alias the aggregate plane answers with. Typed here, not derived from the
#: owner: this string is the *contract* between the two SQL fragments and the
#: fold, so the gate that polices it has to be able to name it. ``IS_DEMO_COUNT``
#: is checked to end with it, and the fold is checked to read it.
DEMO_JOBS_KEY = "demo_jobs"
DEMO_FAILED_KEY = "demo_failed"

#: Methods whose aggregate reads put a number in front of a user, and the one
#: whose aggregate is the population of its own page. Both are rostered against a
#: census derived below, so neither list can be quietly widened or narrowed.
MUST_ANSWER = frozenset({"dashboard_snapshot"})
MUST_NOT_ANSWER = frozenset({"search_jobs"})

#: The three aggregates the premise measured, by shape rather than by line
#: number, so the census can be checked for having read what it claims.
AGGREGATE_MARKS = ("COUNT(*) AS total", "COUNT(*) AS n", "COUNT(*) AS count")


# ── helpers: fold the SQL the store would actually send ───────────────────────


class _Folder(ast.NodeVisitor):
    """Every ``cur.execute(sql, params)`` inside a node, SQL folded to text."""

    def __init__(self, source: str, constants: dict[str, Any]) -> None:
        self.source = source
        self.constants = constants
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
            value = self.constants.get(node.id)
            return value if isinstance(value, str) else "<var>"
        if isinstance(node, ast.JoinedStr):
            return "".join(
                v.value if isinstance(v, ast.Constant) else "<var>"
                for v in node.values)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.fold(node.left) + self.fold(node.right)
        if isinstance(node, ast.Tuple):
            return ",".join(self.fold(e) for e in node.elts)
        return "<var>"


def _module_constants(source: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                with contextlib.suppress(ValueError, SyntaxError):
                    out[target.id] = ast.literal_eval(node.value)
    return out


def _fold_map(source: str) -> dict[str, Any]:
    """This module's literals, seeded with the owner's exported strings.

    The fragments are f-strings built from one another, so ``literal_eval``
    cannot read them out of ``contracts/demo_marker.py`` — and a folded SQL that
    lost a fragment to ``<var>`` would let a leg assert about a statement the
    store never sends. Reading the values off the live owner module keeps the
    fold honest, and a fourth fragment the owner exports needs no edit here.
    """
    merged = {name: value for name, value in vars(demo_marker).items()
              if isinstance(value, str) and not name.startswith("_")}
    merged.update(_module_constants(source))
    return merged


def _store_method(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "MySQLStore":
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return sub
    raise AssertionError(f"MySQLStore.{name} is gone — the census has no subject")


def executed_in(method: str) -> list[tuple[str, str]]:
    """(sql, param-source) for every SELECT the store method performs."""
    source = MYSQL.read_text(encoding="utf-8-sig")
    folder = _Folder(source, _fold_map(source))
    folder.visit(_store_method(source, method))
    return folder.calls


def aggregate_census() -> list[tuple[str, str]]:
    """Every aggregate read over ``verification_jobs`` in the whole product plane.

    Derived from the index, so it is the same population in a normal checkout
    and in a worktree under ``.scratch`` — #541's finding is the reason this
    function does not hand-type a root list or a file name.
    """
    found: list[tuple[str, str]] = []
    for path, rel in product_python_files(REPO):
        source = path.read_text(encoding="utf-8-sig", errors="replace")
        if "verification_jobs" not in source:
            continue
        tree = ast.parse(source)
        constants = _fold_map(source)
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            folder = _Folder(source, constants)
            folder.visit(fn)
            for sql, _params in folder.calls:
                upper = sql.upper()
                if "FROM VERIFICATION_JOBS" not in upper:
                    continue
                if not any(mark in upper for mark in
                           ("COUNT(", "SUM(", "GROUP BY", "DATE_FORMAT")):
                    continue
                found.append((f"{rel}::{fn.name}", sql))
    return found


def answering_methods() -> set[str]:
    """Store methods that publish the demo *count* from an aggregate read."""
    suffix = f"AS {DEMO_JOBS_KEY}"
    return {
        name.split("::")[-1]
        for name, sql in aggregate_census()
        if suffix in sql
    }


def string_constants_holding(needle: str) -> list[tuple[str, int]]:
    """Where in the product plane a literal appears inside a string constant."""
    hits: list[tuple[str, int]] = []
    for path, rel in product_python_files(REPO):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - census floors
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and needle in node.value):
                hits.append((rel, node.lineno))
    return hits


def _placeholder_index(sql: str, fragment: str) -> int:
    """How many ``%s`` precede this occurrence of the fragment."""
    return sql[: sql.index(fragment)].count("%s")


def _flag_occurrences(sql: str) -> int:
    return sql.count(IS_DEMO_FLAG)


def _flag_occurrence_indexes(sql: str) -> list[int]:
    """The ordinal of every ``%s`` that belongs to a flag occurrence."""
    out: list[int] = []
    cursor = 0
    while True:
        at = sql.find(IS_DEMO_FLAG, cursor)
        if at < 0:
            return out
        out.append(sql[:at].count("%s"))
        cursor = at + len(IS_DEMO_FLAG)


class _RecordingCursor:
    def __init__(self, log: list[tuple[str, tuple[Any, ...]]]) -> None:
        self.log = log

    def execute(self, sql: str, params: Any = None) -> None:
        self.log.append((str(sql), tuple(params or ())))

    def fetchone(self) -> dict[str, Any]:
        return {"total": 3}

    def fetchall(self) -> list[dict[str, Any]]:
        return []

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
    """Patch the connection on the class, the way #525/#526's capture does."""
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


def declared_job_keys() -> set[str]:
    """The keys ``api.ts`` declares for the dashboard's ``jobs`` block."""
    text = API_TS.read_text(encoding="utf-8-sig", errors="replace")
    block = re.search(r"jobs:\s*\{(.*?)\n\s*\};", text, re.S)
    if not block:
        raise AssertionError("api.ts declares no jobs block — the probe broke")
    return {m.group(1) for m in re.finditer(r"(\w+)(?:\?)?:", block.group(1))}


def fold_rows() -> dict[str, list[dict[str, Any]]]:
    """A snapshot in the shape the fixed store answers: all-rows counts + demo."""
    hour = datetime.now().strftime("%Y-%m-%dT%H:00:00")
    return {
        "statuses": [
            {"status": "VERIFIED", "n": 4, DEMO_JOBS_KEY: 2},
            {"status": "BLOCKED", "n": 2, DEMO_JOBS_KEY: 2},
            {"status": "FAILED", "n": 1, DEMO_JOBS_KEY: 0},
        ],
        "timeline": [
            {"hour": hour, "count": 7, "failed": 3,
             DEMO_JOBS_KEY: 4, DEMO_FAILED_KEY: 2},
        ],
        "recent_jobs": [],
    }


# ── A: the census ─────────────────────────────────────────────────────────────


def test_the_aggregate_census_is_the_one_the_premise_measured() -> None:
    """Three aggregates read the whole table; the gate must still see three.

    A census that silently lost the timeline statement would report "the two
    reads that answer" as complete, which is the same blindness #541 filed —
    different subject, same shape.
    """
    census = aggregate_census()
    scanned = len(product_python_files(REPO))
    assert scanned >= 250, (
        f"only {scanned} product modules in the census — the walk read nothing"
    )
    assert census, "no aggregate read found over verification_jobs"
    marks = [mark for _name, sql in census for mark in AGGREGATE_MARKS
             if mark in sql]
    assert sorted(marks) == sorted(AGGREGATE_MARKS), (
        f"the census sees {marks}; the premise measured one of each of "
        f"{list(AGGREGATE_MARKS)} — a read left the population"
    )
    assert len(census) >= 3, f"only {len(census)} aggregate reads; expected >= 3"


def test_the_roster_and_the_census_of_who_answers_are_the_same_set() -> None:
    """Both directions, because either alone is a list somebody remembers.

    ``MUST_ANSWER`` is the claim; the census is the fact. A new aggregate that
    starts feeding a visible number has to be added here *and* implemented, and
    a method that stops answering cannot stay on the roster.
    """
    facts = answering_methods()
    missing = MUST_ANSWER - facts
    assert not missing, (
        f"{sorted(missing)} puts a visible number out and publishes no "
        f"'AS {DEMO_JOBS_KEY}': its counts still mix seeded rows with real work"
    )
    extra = facts - MUST_ANSWER
    assert not extra, (
        f"{sorted(extra)} publish a demo count that no leg accounts for — either "
        "the roster is stale or a new aggregate joined without a reason"
    )


def test_every_aggregate_read_is_rostered_as_answering_or_as_declining() -> None:
    """A fourth aggregate cannot join the plane without being accounted for.

    #541's lesson, applied to a roster: one direction of a list is a memory
    test. Here the census names the population and the two rosters name the
    decisions, so an unaccounted read fails in the same way a remembered-but-
    absent one does — and neither list can quietly become the truth.
    """
    facts = {name.split("::")[-1] for name, _sql in aggregate_census()}
    assert facts, "the census saw no aggregate at all — the walk is blind again"
    unaccounted = facts - MUST_ANSWER - MUST_NOT_ANSWER
    assert not unaccounted, (
        f"{sorted(unaccounted)} aggregate verification_jobs and answer neither "
        f"roster ({sorted(MUST_ANSWER)} publish the count, "
        f"{sorted(MUST_NOT_ANSWER)} decline with a reason)"
    )
    ghost = (MUST_ANSWER | MUST_NOT_ANSWER) - facts
    assert not ghost, (
        f"{sorted(ghost)} is rostered but the census sees no aggregate in it — "
        "the read moved and the reason stayed behind"
    )


def test_the_count_that_pages_a_window_answers_only_about_its_window() -> None:
    """The narrowed reason #526 stated too broadly, kept as a test.

    ``search_jobs``' COUNT is the population of the page it returns, and seeded
    rows are legitimately *on* that page — each with its own ``is_demo`` badge.
    Excluding them from that number would make the page count disagree with the
    rows it renders, which is a different lie than the dashboard's.
    """
    statements = executed_in("search_jobs")
    count = [(sql, params) for sql, params in statements if "COUNT(*) AS total" in sql]
    assert count, "search_jobs no longer counts with a COUNT(*) AS total"
    sql, _params = count[0]
    assert f"AS {DEMO_JOBS_KEY}" not in sql, (
        f"the list's total stopped answering about the rows it pages: {sql[:150]!r}"
    )
    assert IS_DEMO_FLAG not in sql, (
        f"the page count asks a predicate it then refuses to use: {sql[:150]!r}"
    )
    with captured(VIEWER) as log:
        MySQLStore().search_jobs(5, 0, "VERIFIED", "")
    executed = [(s, p) for s, p in log if "COUNT(*) AS total" in s]
    assert executed, "no page count executed under a tenant scope — capture broken"
    for executed_sql, params in executed:
        assert DEMO_NOTE_PREFIX not in params, (
            f"the page count binds the marker without reading it: {params!r}"
        )
        assert executed_sql.count("%s") == len(params), (
            f"arity mismatch in {executed_sql[:120]!r}: {params!r}"
        )


def test_the_two_dashboard_aggregates_publish_the_demo_count() -> None:
    """Not "the demo label" — a number, because what leaves the DB is a number."""
    statements = executed_in("dashboard_snapshot")
    status = [sql for sql, _ in statements if "COUNT(*) AS n" in sql]
    timeline = [sql for sql, _ in statements if "COUNT(*) AS count" in sql]
    assert len(status) == 1 and len(timeline) == 1, (
        f"expected one status and one timeline aggregate, got "
        f"{len(status)}/{len(timeline)}"
    )
    assert f"AS {DEMO_JOBS_KEY}" in status[0], (
        "the status GROUP BY still counts seeded rows as real verifications; "
        "累计验收/验收通过/发现风险 are read straight out of this statement"
    )
    assert f"AS {DEMO_JOBS_KEY}" in timeline[0] and f"AS {DEMO_FAILED_KEY}" in timeline[0], (
        "the hourly timeline still mixes seeded rows into 交付动态 and into the "
        "failure count rendered under it; it needs both halves of the split"
    )


# ── B: one owner, three shapes ────────────────────────────────────────────────


def test_the_flag_is_the_single_text_behind_all_three_shapes() -> None:
    """Column, count and failed-count must be spelled from one flag.

    #525 collapsed three copies of the marker *string*; #526 collapsed two copies
    of the column *expression*. This is the same repair one plane further out: if
    the aggregate's predicate were typed again, a rename could make the badge and
    the statistic disagree — the rows would say 示例数据 while the count kept
    including them, and both statements would be "correct".
    """
    assert f"{IS_DEMO_FLAG} AS is_demo" == IS_DEMO_COLUMN, (
        "the row label is no longer the flag plus an alias — two spellings again"
    )
    assert f"SUM({IS_DEMO_FLAG}) AS {DEMO_JOBS_KEY}" == IS_DEMO_COUNT, (
        f"the demo count is not built from the flag: {IS_DEMO_COUNT!r}"
    )
    assert (
        f"SUM({IS_DEMO_FLAG} AND status IN ('FAILED', 'ERROR')) AS {DEMO_FAILED_KEY}"
    ) == IS_DEMO_FAILED, f"the demo failure count drifted off the flag: {IS_DEMO_FAILED!r}"
    for needle in (f"AS {DEMO_JOBS_KEY}", f"AS {DEMO_FAILED_KEY}"):
        holders = sorted({rel for rel, _ in string_constants_holding(needle)})
        assert holders == ["contracts/demo_marker.py"], (
            f"{needle} is spelled in {holders}; the alias is part of the wire "
            "contract and a second copy can disagree with the fold"
        )
    inlined = [
        line.strip()[:90] for line in MYSQL.read_text(encoding="utf-8-sig").splitlines()
        if "CASE WHEN JSON_VALID(summary)" in line
    ]
    assert not inlined, f"storage/mysql.py writes the predicate again: {inlined}"


# ── C: executed parameters ────────────────────────────────────────────────────


def test_every_aggregate_binds_one_prefix_per_flag_and_nothing_hardcoded() -> None:
    """Arity and order, on the statement the driver would actually receive.

    mysqlclient formats against the arguments, so a flag added without its
    placeholder is a raised TypeError inside every dashboard request — and a
    placeholder filled by the tenant id is a predicate that silently answers 0
    for every row, which is the failure that makes the numbers look plausible.
    """
    with captured(VIEWER) as log:
        MySQLStore().dashboard_snapshot(datetime(2026, 9, 18))
    aggregates = [
        (sql, params) for sql, params in log
        if "FROM verification_jobs" in sql and f"AS {DEMO_JOBS_KEY}" in sql
    ]
    assert aggregates, (
        f"no executed aggregate publishes the demo count under a tenant scope — "
        f"the capture saw {len(log)} statements"
    )
    for sql, params in aggregates:
        flags = _flag_occurrences(sql)
        assert flags >= 1, f"the census said this reads the flag, the text does not: {sql[:120]!r}"
        assert sql.count("%s") == len(params), (
            f"arity mismatch: {sql.count('%s')} placeholders, {len(params)} params"
        )
        assert DEMO_NOTE_PREFIX not in sql, (
            f"the marker text is inside the executed SQL: {sql[:120]!r}"
        )
        for occurrence in range(flags):
            at = _flag_occurrence_indexes(sql)[occurrence]
            assert params[at] == DEMO_NOTE_PREFIX, (
                f"placeholder #{occurrence} of the flag is bound to "
                f"{params[at]!r}, not the owner's prefix"
            )


def test_the_flag_placeholders_bind_before_the_window_and_the_tenant() -> None:
    """The SELECT list is textually earlier than the WHERE it also parameterises.

    #525 pinned this for two window reads; a third shape (an aggregate that both
    filters by tenant and answers a demo count) inherits the rule, and getting it
    wrong is not an error — it binds the tenant id into ``LOCATE`` and answers 0.
    """
    for scope in (VIEWER, None):
        with captured(scope) as log:
            MySQLStore().dashboard_snapshot(datetime(2026, 9, 18))
        for sql, params in log:
            if f"AS {DEMO_JOBS_KEY}" not in sql:
                continue
            flag_indexes = _flag_occurrence_indexes(sql)
            for at in flag_indexes:
                assert params[at] == DEMO_NOTE_PREFIX
            if scope is not None:
                tenant_at = _placeholder_index(sql, "(tenant_id = %s")
                assert tenant_at == len(flag_indexes), (
                    f"under a tenant scope the tenant value must follow the "
                    f"{len(flag_indexes)} flag binding(s), got index {tenant_at} "
                    f"in {params!r}"
                )
            if "created_at >= %s" in sql:
                since_at = _placeholder_index(sql, "created_at >= %s")
                assert since_at == len(flag_indexes) + (1 if scope is not None else 0), (
                    f"the window value must bind last, at index {since_at} of {params!r}"
                )


# ── D: the fold must not be able to shrug ─────────────────────────────────────


def test_the_fold_reads_the_demo_columns_without_a_default() -> None:
    """``.get(key, 0)`` here is the bug wearing a different hat.

    An aggregate that stopped publishing the split would answer "zero seeded rows"
    — indistinguishable from the truth — and the dashboard would keep showing
    inflated numbers while every static check stayed green. Absence has to raise.
    """
    source = WEB.read_text(encoding="utf-8-sig")
    for key in (DEMO_JOBS_KEY, DEMO_FAILED_KEY):
        assert f'row["{key}"]' in source, (
            f"the fold no longer reads row[\"{key}\"] — it is guessing again"
        )
        assert f'.get("{key}"' not in source, (
            f"the fold defaults {key}: a read that publishes nothing would look "
            "like a database with no seeded rows in it"
        )


def test_the_degraded_answer_keeps_the_same_keys_as_the_real_one(
    monkeypatch: Any,
) -> None:
    """One branch, two shapes: the class #526 named "an absence and a zero".

    The happy path publishes ``needs_review_rate``; a degraded path that omits a
    key is not "unknown", it is a payload the consumer cannot type. The demo split
    must therefore be absent from *both*, or present in both — and since #542
    deliberately publishes no new key, this leg is what keeps that decision from
    rotting into a half-added field.
    """
    happy_keys = _jobs_keys_with(monkeypatch, ok=True)
    degraded_keys = _jobs_keys_with(monkeypatch, ok=False)
    assert happy_keys == degraded_keys, (
        f"the degraded jobs block answers {sorted(degraded_keys)} while a real "
        f"read answers {sorted(happy_keys)} — one of the two is a shape the UI "
        "cannot render honestly"
    )
    assert declared_job_keys() == happy_keys, (
        f"api.ts declares {sorted(declared_job_keys())} and the fold answers "
        f"{sorted(happy_keys)}; #542 adds no key nobody reads, and if one is "
        "added the type has to say so"
    )


def _jobs_keys_with(monkeypatch: Any, *, ok: bool) -> set[str]:
    if ok:
        monkeypatch.setattr(MySQLStore, "dashboard_snapshot",
                            lambda self, since: fold_rows())
    else:
        def _boom(self: MySQLStore, since: datetime) -> dict[str, Any]:
            raise RuntimeError("mysql is down")

        monkeypatch.setattr(MySQLStore, "dashboard_snapshot", _boom)
    payload = dashboard()
    return set(payload["jobs"])


def test_the_fold_subtracts_the_split_from_every_visible_number(
    monkeypatch: Any,
) -> None:
    """The arithmetic, without a database — so it is checkable when the schema is busy.

    ``fold_rows()`` answers seven rows across three statuses, four of them seeded:
    累计验收 has to be 3, 验收通过 2, 发现风险 0 (that status is *nothing but*
    sample data, and "0 real" is a different answer from "no such status"), and
    the hourly line has to lose both the four seeded rows and two of the failures.
    Reading the column is not the fix; subtracting it is, and the structural legs
    above stay green while a fold that reads and ignores keeps every card
    inflated.
    """
    monkeypatch.setattr(MySQLStore, "dashboard_snapshot",
                        lambda self, since: fold_rows())
    jobs = dashboard()["jobs"]
    assert jobs["total"] == 3, (
        f"4 of 7 rows are seeded, so the page has to answer 3; got {jobs['total']}"
    )
    assert jobs["by_status"] == {"VERIFIED": 2, "BLOCKED": 0, "FAILED": 1}, (
        f"the per-status card is still mixing sample data in: {jobs['by_status']}"
    )
    assert jobs["failure_rate"] == round(1 / 3, 4), (
        f"the denominator of the rate is the real population (3), not 7: "
        f"{jobs['failure_rate']}"
    )
    assert jobs["blocked_rate"] == 0.0, (
        "every BLOCKED row was seeded, so the risk card has to read 0"
    )
    assert dashboard()["timeline_24h"] == [
        {"hour": fold_rows()["timeline"][0]["hour"], "count": 3, "failed": 1},
    ], "the hourly line still counts the seeded rows and the seeded failures"


# ── E: behaviour, on the real schema ─────────────────────────────────────────


def test_seeded_rows_change_the_real_numbers_only_through_the_marker() -> None:
    """The promise, measured against the real schema.

    ``seed_demo`` writes no ``tenant_id``, so a seeded row clears every tenant's
    scope predicate, and one of its three statuses is ``BLOCKED``. The dashboard
    therefore has to answer as if those rows were not there — and when the marker
    is removed from one row's note, *that* row has to come back into the count.
    Deltas, not absolute numbers: the test schema is shared, and the claim is
    about the three rows this leg inserts.
    """
    store = MySQLStore()
    store.ensure_tables()
    token = TENANT_SCOPE_VAR.set(None)
    ids: list[str] = []
    try:
        before = _dashboard_numbers()
        ids.append(_seed_row(store, "VERIFIED", marker=False))
        ids.append(_seed_row(store, "VERIFIED", marker=True))
        ids.append(_seed_row(store, "BLOCKED", marker=True))
        _unmarked, demo_verified, demo_blocked = ids

        after = _dashboard_numbers()
        assert after["total"] - before["total"] == 1, (
            f"one real row plus two seeded rows moved the total by "
            f"{after['total'] - before['total']} — the dashboard is counting "
            "sample data as verifications"
        )
        assert _status_delta(after, before, "VERIFIED") == 1, (
            "the real VERIFIED row did not enter the count, or a seeded one did"
        )
        assert _status_delta(after, before, "BLOCKED") == 0, (
            f"a seeded BLOCKED row ({demo_blocked}) entered 发现风险: the page now "
            "advertises a risk that was invented to demonstrate the page"
        )
        assert after["window"] - before["window"] == 1, (
            "交付动态 counted the seeded rows created inside the 24h window"
        )

        _strip_marker(store, demo_verified)
        stripped = _dashboard_numbers()
        assert stripped["total"] - after["total"] == 1, (
            "removing the marker from a row did not move the number, so the "
            "exclusion is keyed on something other than the demo fact"
        )
        assert _status_delta(stripped, after, "VERIFIED") == 1, (
            "un-labelling a row did not make it real work: the marker is not "
            "the cause of the exclusion"
        )
        assert _status_delta(stripped, after, "BLOCKED") == 0, (
            "un-labelling a VERIFIED row changed 发现风险 — the split is being "
            "computed from the status, not from the marker"
        )
    finally:
        TENANT_SCOPE_VAR.reset(token)
        _drop_rows(store, ids)


def _dashboard_numbers() -> dict[str, Any]:
    """What the dashboard answers right now, in the shape the page reads it."""
    payload = dashboard()
    assert payload["degraded"] is False, (
        f"the route went degraded, so every number below is a placeholder: "
        f"{payload['degraded_reasons']}"
    )
    jobs = payload["jobs"]
    return {
        "total": int(jobs["total"]),
        "by_status": {str(status): int(n) for status, n in jobs["by_status"].items()},
        "window": sum(int(point["count"]) for point in payload["timeline_24h"]),
    }


def _status_delta(after: dict[str, Any], before: dict[str, Any], status: str) -> int:
    return after["by_status"].get(status, 0) - before["by_status"].get(status, 0)


def _seed_row(store: MySQLStore, status: str, *, marker: bool) -> str:
    job_id = str(uuid.uuid4())
    store.insert_job({
        "id": job_id,
        "repo_path": f"/test/542/{uuid.uuid4().hex[:8]}",
        "base_ref": "base",
        "head_ref": "head",
        "spec_path": "/test/spec.md",
        "status": status,
        "depth": "FAST",
    })
    note = (seeded_demo_note("aggregate (【演示】)") if marker
            else "real retrieval note for the aggregate gate")
    store.save_job_summary(job_id, {"retrieval_note": note})
    return job_id


def _strip_marker(store: MySQLStore, job_id: str) -> None:
    store.save_job_summary(job_id, {"retrieval_note": "retrieved 8 chunks"})


def _drop_rows(store: MySQLStore, ids: list[str]) -> None:
    """Tear the seeded rows down the way the product tears jobs down.

    #98 bans an in-place job delete in tests: `audit_logs` outlives the job on
    purpose, so removing the row here would leave a trail referencing a job that
    "never existed" — and these three rows produce exactly that residue, so the
    audit rows go too (test residue, not a compliance history).
    """
    for job_id in ids:
        store.delete_job_records(job_id)
    with store.connection() as conn:
        cur = conn.cursor()
        for job_id in ids:
            cur.execute("DELETE FROM audit_logs WHERE job_id = %s", (job_id,))


# ── F: the neighbourhood #542 had to change ───────────────────────────────────


def test_the_526_gate_no_longer_claims_aggregations_need_nothing() -> None:
    """A green leg that has stopped meaning what it says is still a hole.

    #526's ``test_the_aggregate_reads_do_not_publish_it`` asserted only
    ``"AS is_demo" not in sql``, so after #542 it keeps passing while the GROUP
    BYs it waved off now publish the fact under a different alias. The leg was
    narrowed to the statement it was actually about; this checks that happened,
    by reading the sibling gate's body rather than restating its rules here.
    """
    tree = ast.parse(GATE_526.read_text(encoding="utf-8-sig"))
    bodies = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }
    blanket = [
        name for name, node in bodies.items()
        if "aggregat" in name.lower() and "not_publish" in name.lower()
    ]
    assert not blanket, (
        f"{blanket} still asserts that aggregates publish nothing; #542 makes two "
        "of them answer the demo question as a count, so the leg either has to "
        "name the one statement it guards or be deleted"
    )
    narrowed = [
        name for name, node in bodies.items()
        if f"AS {DEMO_JOBS_KEY}" in ast.unparse(node)
    ]
    assert narrowed, (
        "nothing in #526's gate records that the list COUNT must stay a page "
        "count; the asymmetry would live only in this file and be invisible to "
        "the gate that used to own the question"
    )


def test_the_marker_still_reaches_the_aggregates_as_data_not_as_text() -> None:
    """#525's property, one plane further out.

    The bound parameter is what keeps a rename on the *read* side from being a
    silent no-op. With two more statements asking the question there are twice as
    many places for the prefix to be typed instead of passed, and a typed prefix
    that disagrees with the seeder's reads "no seeded rows" forever.
    """
    with captured(None) as log:
        MySQLStore().dashboard_snapshot(datetime.now() - timedelta(hours=24))
    assert log, "the store executed nothing — the capture is not reaching the read"
    flagged = [(sql, params) for sql, params in log if IS_DEMO_FLAG in sql]
    assert flagged, (
        f"no executed statement carries the owner's flag text; saw {len(log)} "
        "statements"
    )
    for sql, params in flagged:
        assert DEMO_NOTE_PREFIX not in sql
        assert DEMO_NOTE_PREFIX in params
