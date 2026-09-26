"""#95: an audit row whose job is gone must explain itself, or be called out.

Measured on 2026-09-26: the product schema held **822** audit rows whose
``job_id`` resolved to nothing, while ``verification_jobs`` itself had 0 rows —
and the test schema reproduced the same shape live (112 of 144 rows dangling).
Reading those rows as an operator is impossible: "job X went QUEUED→RUNNING"
and "X never existed" look identical, yet DATA_LIFECYCLE §3.1 keeps
``audit_logs`` on purpose when a job is purged, so dangling is *correct* here.

So the fix is not a foreign key and not a refusal to write. It is that the
deletion has to leave a sentence behind, and the reader has to say which of
four states a row is in. These tests lock that vocabulary from both sides:
the declaration in ``storage/mysql.py``, the AST-derived set of call sites that
actually write, the statement text the purge emits, and the table in
DATA_DICTIONARY §1.8. Grepping for a keyword would let a new writer invent an
action nobody registered — that is how #87 shipped five dead words.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

from storage import mysql as mysql_mod
from storage.mysql import (
    AUDIT_JOB_PRESENT,
    AUDIT_JOB_PURGED,
    AUDIT_JOB_SYSTEM_LEVEL,
    AUDIT_JOB_UNEXPLAINED,
    JOB_RECORDS_DELETED_ACTION,
    MySQLStore,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DICTIONARY = REPO_ROOT / "docs" / "architecture" / "DATA_DICTIONARY.md"

#: Lanes a production audit action may come from. ``tests`` and ``bench`` are
#: excluded because a test may write a synthetic action without joining the
#: vocabulary; ``scripts`` is excluded because the benchmark harnesses pass
#: ``action=`` to unrelated APIs (policy rules, edit ops).
PRODUCTION_LANES = ("agent", "api", "storage", "ops", "craft", "cli")

_SKIP_PARTS = {".venv", "node_modules", "bench", "tests", "scripts", ".git", "dist"}


def _production_files() -> list[Path]:
    files: list[Path] = []
    for lane in PRODUCTION_LANES:
        for path in (REPO_ROOT / lane).rglob("*.py"):
            if _SKIP_PARTS.intersection(p for p in path.parts):
                continue
            files.append(path)
    assert files, "no production sources found — the scan, not the code, is broken"
    return files


def _string_leaves(node: ast.expr, module: ast.Module) -> set[str]:
    """Every action a call site can pass: literals, and named constants.

    A value this cannot resolve is reported by the caller as a hole rather
    than silently dropped — an action that only exists at runtime is exactly
    the un-auditable write path this gate is supposed to forbid.
    """
    found: set[str] = set()
    consts = {
        t.id: stmt.value.value
        for stmt in module.body
        if isinstance(stmt, ast.Assign)
        for t in stmt.targets
        if isinstance(t, ast.Name) and isinstance(stmt.value, ast.Constant)
    }
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            found.add(sub.value)
        elif isinstance(sub, ast.Name) and sub.id in consts:
            value = consts[sub.id]
            if isinstance(value, str):
                found.add(value)
    return found


def _audit_writing_files() -> list[tuple[Path, ast.Module]]:
    parsed: list[tuple[Path, ast.Module]] = []
    for path in _production_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _is_record_audit(node)
        ]
        if calls:
            parsed.append((path, tree))
    assert len(parsed) >= 4, (
        f"only {len(parsed)} production modules write audits; the scanner "
        "stopped finding call sites and would pass vacuously"
    )
    return parsed


def _is_record_audit(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "record_audit"
    return isinstance(func, ast.Name) and func.id == "record_audit"


def _derived_actions() -> tuple[set[str], list[str]]:
    """(actions written by production code, unresolvable action arguments)."""
    actions: set[str] = set()
    opaque: list[str] = []
    for path, tree in _audit_writing_files():
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and _is_record_audit(node)):
                continue
            kw = next((k for k in node.keywords if k.arg == "action"), None)
            assert kw is not None, f"{path}: record_audit without action= is unlabelled"
            leaves = _string_leaves(kw.value, tree)
            if not leaves:
                opaque.append(f"{path.name}:{node.lineno}")
            actions |= leaves
    return actions, opaque


def test_every_audit_action_a_call_site_writes_is_declared() -> None:
    derived, opaque = _derived_actions()
    assert not opaque, (
        f"these record_audit call sites pass an action no scanner can resolve: "
        f"{opaque}; an action that only exists at runtime cannot be registered "
        "in AUDIT_ACTIONS or the data dictionary"
    )
    assert derived, "no audit actions derived from production code at all"
    undeclared = derived - set(mysql_mod.AUDIT_ACTIONS)
    assert not undeclared, (
        f"production writes audit actions that AUDIT_ACTIONS does not declare: "
        f"{sorted(undeclared)} — an operator reading DATA_DICTIONARY §1.8 "
        "would never learn these exist"
    )


def test_declaration_has_no_dead_entries() -> None:
    """The #87 lesson in the other direction: a word nobody writes is a lie."""
    derived, _ = _derived_actions()
    # delete_job_records passes its action positionally, so AST call-site
    # scanning cannot see it; it is declared and locked statement-wise below.
    dead = set(mysql_mod.AUDIT_ACTIONS) - derived - {JOB_RECORDS_DELETED_ACTION}
    assert not dead, f"AUDIT_ACTIONS declares actions no producer writes: {sorted(dead)}"


def test_action_name_constants_cannot_drift_into_a_second_vocabulary() -> None:
    """Each audit-writing module names its actions as constants, not prose.

    ``ops/drills.py`` filters on ``TRANSITION_ACTION``; if a module in this set
    ever writes an ``*_ACTION`` string the declaration does not carry, two
    vocabularies exist and only one of them is documented.
    """
    offenders: list[str] = []
    for path, tree in _audit_writing_files():
        for stmt in ast.walk(tree):
            if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, ast.Constant):
                continue
            if not isinstance(stmt.value.value, str):
                continue
            for target in stmt.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id.endswith("_ACTION")
                    and stmt.value.value not in mysql_mod.AUDIT_ACTIONS
                ):
                    offenders.append(f"{path.name}:{stmt.lineno} {target.id}")
    assert not offenders, (
        f"*_ACTION constants outside AUDIT_ACTIONS: {offenders}"
    )


_DOC_BLOCK_RE = re.compile(
    r"<!-- AUDIT_ACTIONS_BEGIN.*?-->\s*(.*?)<!-- AUDIT_ACTIONS_END -->", re.DOTALL
)


def test_data_dictionary_registers_exactly_the_declared_actions() -> None:
    doc = DATA_DICTIONARY.read_text(encoding="utf-8")
    block = _DOC_BLOCK_RE.search(doc)
    assert block is not None, (
        "DATA_DICTIONARY §1.8 no longer carries the AUDIT_ACTIONS block, so "
        "nothing keeps the document in step with the code"
    )
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", block.group(1), re.MULTILINE))
    assert documented, "the documented action table parsed zero rows"
    assert documented == set(mysql_mod.AUDIT_ACTIONS), (
        f"doc-only={sorted(documented - set(mysql_mod.AUDIT_ACTIONS))} "
        f"code-only={sorted(set(mysql_mod.AUDIT_ACTIONS) - documented)}"
    )


# ── the purge itself: statement-level contract ─────────────────


class _FakeCursor:
    """Records statements: FakeJobTable-style semantics cannot catch SQL text.

    ``rowcount`` is driven per statement by ``_FakeStore`` so the branch under
    test ("a job row actually went away") is the thing being exercised.
    """

    def __init__(self, recorder: _FakeStore) -> None:
        self._recorder = recorder
        self.rowcount = 0

    def execute(self, sql: str, params: Any = None) -> None:
        self._recorder.statements.append((sql, params))
        self.rowcount = self._recorder.rowcounts.get(
            len(self._recorder.statements) - 1, 0
        )

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._recorder.rows)

    def fetchone(self) -> dict[str, Any] | None:
        """Answer COUNT and the existence probe from scripted answers.

        Scripted per statement *kind* rather than by position, so a test that
        adds a query cannot silently re-point the answers.
        """
        sql = self._recorder.statements[-1][0]
        if sql.startswith("SELECT COUNT(*)"):
            return self._recorder.total_row
        if "FROM verification_jobs WHERE id" in sql:
            return {"hit": 1} if self._recorder.job_exists else None
        return None

    def close(self) -> None:
        return None


class _FakeStore(MySQLStore):
    """MySQLStore with the connection swapped out; one cursor, one session."""

    def __init__(self, rowcounts: dict[int, int] | None = None) -> None:
        self.statements: list[tuple[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.rowcounts = rowcounts or {}
        self.total_row: dict[str, Any] | None = None
        self.job_exists = False
        self._cursor = _FakeCursor(self)

    def connection(self):  # type: ignore[override]
        from contextlib import contextmanager

        @contextmanager
        def _conn() -> Any:
            yield self

        return _conn()

    def cursor(self) -> _FakeCursor:
        return self._cursor

    @property
    def statements_text(self) -> list[str]:
        return [s for s, _ in self.statements]


def test_purge_of_a_real_job_leaves_an_explaining_audit_row_in_the_same_session() -> None:
    store = _FakeStore(rowcounts={0: 2, 1: 1, 2: 1, 3: 1})
    counts = store.delete_job_records("job-1")
    assert counts["jobs"] == 1, counts
    inserts = [
        (sql, params)
        for sql, params in store.statements
        if "INSERT INTO audit_logs" in sql
    ]
    assert len(inserts) == 1, (
        f"expected exactly one audit insert, got {len(inserts)}; the surviving "
        "audit rows for this job need exactly one explanation"
    )
    sql, params = inserts[0]
    assert "attempted_tenant" not in sql, sql
    assert params[0] == "job-1", params
    assert params[2] == JOB_RECORDS_DELETED_ACTION, params
    assert params[1] == "lifecycle", params
    assert "audit_logs retained by design" in str(params[5]), params
    assert counts["audit"] == 1, counts
    deletes = [s for s in store.statements_text if s.startswith("DELETE FROM")]
    assert len(deletes) == 3, deletes
    assert store.statements_text.index(deletes[-1]) < min(
        i for i, s in enumerate(store.statements_text)
        if "INSERT INTO audit_logs" in s
    ), "the job must be gone before its deletion is announced"


def test_purge_of_a_missing_job_invents_no_explanation() -> None:
    """Idempotent delete: zero job rows must not add an audit row.

    A second ``job_records_deleted`` for a job that was already gone would
    make ``unexplained`` impossible to reach and turn the disposition column
    into a claim about the query, not about the data.
    """
    store = _FakeStore(rowcounts={0: 0, 1: 0, 2: 0})
    counts = store.delete_job_records("never-existed")
    assert counts["jobs"] == 0, counts
    assert not [s for s in store.statements_text if "INSERT INTO audit_logs" in s]
    assert not [s for s in store.statements_text if s.startswith("INSERT")], (
        "nothing was deleted, so nothing may be announced"
    )


def test_audit_insert_statement_is_not_copied_between_write_paths() -> None:
    """One statement text, two callers (#80's parity shape)."""
    store = _FakeStore(rowcounts={0: 0, 1: 0, 2: 1, 3: 1})
    store.delete_job_records("job-2")
    purge_sql = next(s for s in store.statements_text if "INSERT INTO audit_logs" in s)
    assert purge_sql == mysql_mod._AUDIT_INSERT_SQL  # noqa: SLF001
    store2 = _FakeStore()
    store2.record_audit(action="job_cancelled", job_id="job-2")
    assert store2.statements_text == [mysql_mod._AUDIT_INSERT_SQL]  # noqa: SLF001


# ── the reader: four dispositions, no fifth ────────────────────


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"job_id": None, "job_present": 0, "purge_recorded": 0}, AUDIT_JOB_SYSTEM_LEVEL),
        ({"job_id": "j", "job_present": 1, "purge_recorded": 0}, AUDIT_JOB_PRESENT),
        ({"job_id": "j", "job_present": 1, "purge_recorded": 1}, AUDIT_JOB_PRESENT),
        ({"job_id": "j", "job_present": 0, "purge_recorded": 1}, AUDIT_JOB_PURGED),
        ({"job_id": "j", "job_present": 0, "purge_recorded": 0}, AUDIT_JOB_UNEXPLAINED),
        ({"job_id": "j"}, AUDIT_JOB_UNEXPLAINED),
    ],
)
def test_job_disposition_table(row: dict[str, Any], expected: str) -> None:
    assert mysql_mod._job_disposition(row) == expected  # noqa: SLF001


def test_absent_marker_columns_never_conjure_present() -> None:
    """A row the query did not classify reads as unexplained, not present.

    If a missing marker defaulted to "present", the disposition column would
    reassure the operator exactly when the join silently stopped working.
    """
    store = _FakeStore()
    store.rows = [{"id": 1, "job_id": "j", "action": "job_status_transition"}]
    rows = store.list_audit_logs(10)
    assert rows[0]["job_disposition"] == AUDIT_JOB_UNEXPLAINED, (
        "a fake cursor returning no marker columns must not conjure 'present'"
    )


def test_read_side_asks_for_the_markers_it_classifies_on() -> None:
    store = _FakeStore()
    store.rows = []
    store.list_audit_logs(5)
    sql = store.statements_text[0]
    assert "LEFT JOIN verification_jobs" in sql, sql
    assert "job_present" in sql and "purge_recorded" in sql, sql
    assert "ORDER BY a.id DESC LIMIT %s" in sql, sql
    assert store.statements[0][1] == (JOB_RECORDS_DELETED_ACTION, 5), store.statements[0]


# ── #97: one job's trail, and how much history the page stands for ──


def test_a_job_filter_narrows_the_page_and_its_total_together() -> None:
    """The count beside the rows must count those rows' question.

    A total over the whole table while the page is filtered reads as "this
    job has 3421 audit events" — the exact kind of confident wrong number
    #67 was about.
    """
    store = _FakeStore()
    store.rows = [{"id": 1, "job_id": "job-1", "action": "job_cancelled"}]
    store.total_row = {"total": 1}
    trail = store.audit_trail(limit=10, job_id="job-1")
    page_sql, count_sql = store.statements_text[0], store.statements_text[1]
    assert mysql_mod._AUDIT_JOB_FILTER_SQL in page_sql  # noqa: SLF001
    assert mysql_mod._AUDIT_JOB_FILTER_SQL in count_sql, (  # noqa: SLF001
        f"the total ignored the filter: {count_sql}"
    )
    assert store.statements[0][1] == (JOB_RECORDS_DELETED_ACTION, "job-1", 10)
    assert store.statements[1][1] == ("job-1",), store.statements[1]
    assert trail["total"] == 1
    assert [r["job_id"] for r in trail["rows"]] == ["job-1"]


def test_a_filtered_read_probes_existence_and_an_unfiltered_one_does_not() -> None:
    """`None` and `False` are different answers and must stay different.

    `job_present: false` means "no such job — check the id"; `null` means the
    question was not asked (no filter). Collapsing them would make every
    unfiltered read claim the job is missing.
    """
    store = _FakeStore()
    store.rows = []
    store.total_row = {"total": 0}
    assert store.audit_trail(limit=10)["job_present"] is None, (
        "an unfiltered read must not answer a question it never probed"
    )
    assert len(store.statements) == 2, store.statements_text
    store2 = _FakeStore()
    store2.rows = []
    store2.total_row = {"total": 0}
    store2.job_exists = True
    filtered = store2.audit_trail(limit=10, job_id="job-9")
    assert filtered["job_present"] is True
    assert "FROM verification_jobs WHERE id" in store2.statements_text[2]


@pytest.mark.parametrize(
    ("total_row", "expected"),
    [
        (None, 0),
        ({"total": None}, 0),
        ({"total": 0}, 0),
        ({"total": 42}, 42),
    ],
)
def test_the_total_is_read_from_the_answer_not_the_page(
    total_row: dict[str, Any] | None, expected: int
) -> None:
    """A missing COUNT row reads as 0, never as len(rows).

    Falling back to the page length would report "all 3 of 3 audit events"
    for a job with 3 shown rows out of 900 — a truncation hidden by the
    number that exists to reveal it.
    """
    store = _FakeStore()
    store.rows = [{"id": n, "job_id": "j", "action": "job_cancelled"} for n in (1, 2, 3)]
    store.total_row = total_row
    assert store.audit_trail(limit=3)["total"] == expected


def test_a_real_miss_reads_absent_not_unknown() -> None:
    store = _FakeStore()
    store.rows = []
    store.total_row = {"total": 0}
    store.job_exists = False
    trail = store.audit_trail(limit=10, job_id="00000000-0000-4000-8000-000000000000")
    assert trail["job_present"] is False, (
        "a probe that found nothing must say so; `None` reads as 'unknown' "
        "and the page would have no basis for 'this job id does not exist'"
    )


def test_disposition_is_stamped_on_filtered_rows_too() -> None:
    """The filter must not bypass the #95 classification step."""
    store = _FakeStore()
    store.rows = [{"id": 1, "job_id": "job-1", "job_present": 0, "purge_recorded": 1}]
    store.total_row = {"total": 1}
    trail = store.audit_trail(limit=10, job_id="job-1")
    assert trail["rows"][0]["job_disposition"] == AUDIT_JOB_PURGED


def test_disposition_vocabulary_is_closed() -> None:
    declared = {
        AUDIT_JOB_PRESENT,
        AUDIT_JOB_PURGED,
        AUDIT_JOB_UNEXPLAINED,
        AUDIT_JOB_SYSTEM_LEVEL,
    }
    seen: set[str] = set()
    for row in (
        {"job_id": None, "job_present": 0, "purge_recorded": 0},
        {"job_id": "j", "job_present": 1, "purge_recorded": 0},
        {"job_id": "j", "job_present": 0, "purge_recorded": 1},
        {"job_id": "j", "job_present": 0, "purge_recorded": 0},
    ):
        seen.add(mysql_mod._job_disposition(row))  # noqa: SLF001
    assert seen == declared, f"declared {sorted(declared)}, reachable {sorted(seen)}"


# ── live schema: the whole point, end to end ──────────────────


def _live_store() -> MySQLStore:
    store = MySQLStore()
    try:
        with store.connection() as conn:
            conn.cursor().execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — no MySQL here is a coverage fact
        pytest.skip(f"MySQL is not reachable: {exc}")
    return store


def _purge_jobs_under(store: MySQLStore, repo_path: str) -> list[str]:
    """Remove every job row under ``repo_path`` via the product path (#98).

    Returns the ids whose audit trails the caller should then clear as test
    residue. Reaching for the job table directly here would leave those very
    rows dangling — the state #95 had to add a column to explain.
    """
    with store.connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM verification_jobs WHERE repo_path = %s", (repo_path,)
        )
        ids = [row["id"] for row in cur.fetchall()]
    for job_id in ids:
        store.delete_job_records(job_id)
    return ids


def test_purge_then_read_reports_purged_not_unexplained() -> None:
    """Insert → transition (audited) → purge → read, against the real schema.

    The claim being measured is that ``unexplained`` is unreachable *by
    normal use*: after the documented delete path the surviving transition
    row must read as ``purged_by_lifecycle``. Fake cursors cannot settle
    whether the EXISTS subquery is even valid SQL.
    """
    import uuid

    store = _live_store()
    job_id = str(uuid.uuid4())
    created = False
    try:
        store.insert_job(
            {
                "id": job_id,
                "repo_path": "/test/audit-purge",
                "base_ref": "base",
                "head_ref": "head",
                "spec_path": "spec",
                "status": "PENDING",
                "depth": 1,
                "github_check_json": None,
            }
        )
        created = True
        assert store.transition_job_status(job_id, "QUEUED", from_status="PENDING")
        dispositions = {
            r["job_id"]: r["job_disposition"]
            for r in store.list_audit_logs(1000)
            if r["job_id"] == job_id
        }
        assert dispositions == {job_id: AUDIT_JOB_PRESENT}, dispositions

        counts = store.delete_job_records(job_id)
        created = False
        assert counts["jobs"] == 1, counts
        assert counts["audit"] == 1, (
            "the purge committed without its explanation — the two statements "
            "must share one transaction or the trail goes silent again"
        )
        dispositions = {
            r["action"]: r["job_disposition"]
            for r in store.list_audit_logs(1000)
            if r["job_id"] == job_id
        }
        assert set(dispositions) == {"job_status_transition", JOB_RECORDS_DELETED_ACTION}
        assert set(dispositions.values()) == {AUDIT_JOB_PURGED}, dispositions
    finally:
        if created:
            store.delete_job_records(job_id)
        abandoned = _purge_jobs_under(store, "/test/audit-purge")
        with store.connection() as conn:
            cur = conn.cursor()
            for leftover in [job_id, *abandoned]:
                cur.execute("DELETE FROM audit_logs WHERE job_id = %s", (leftover,))


def test_one_job_can_be_asked_about_directly() -> None:
    """Filtering by job is the point of the disposition column (#96 → #97).

    Without it an operator holding one job id can only read the newest N rows
    of the whole table, so on any schema with real history the job's own trail
    is usually not on the page at all. The second half is the payoff: after the
    documented purge, asking about that job still answers in one query — its
    rows are there, they read ``purged_by_lifecycle``, and the job row is gone.
    """
    import uuid

    store = _live_store()
    mine, other = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        for job_id in (mine, other):
            store.insert_job(
                {
                    "id": job_id,
                    "repo_path": "/test/audit-filter",
                    "base_ref": "base",
                    "head_ref": "head",
                    "spec_path": "spec",
                    "status": "PENDING",
                    "depth": 1,
                    "github_check_json": None,
                }
            )
            store.transition_job_status(job_id, "QUEUED", from_status="PENDING")
            store.record_audit(
                action="job_cancelled", actor="test", job_id=job_id, detail="filtered"
            )

        global_total = store.audit_trail(limit=10)["total"]
        trail = store.audit_trail(limit=100, job_id=mine)
        assert trail["job_present"] is True, trail
        assert 0 < trail["total"] < global_total, (
            f"filtered total {trail['total']} vs whole table {global_total} — "
            "the count is not describing the rows it is shown beside"
        )
        assert {r["job_id"] for r in trail["rows"]} == {mine}, trail["rows"]
        assert len(trail["rows"]) == trail["total"], (
            "a total below the page length means the filter over-matched"
        )
        assert {r["job_disposition"] for r in trail["rows"]} == {AUDIT_JOB_PRESENT}

        assert store.delete_job_records(mine)["audit"] == 1
        after = store.audit_trail(limit=100, job_id=mine)
        assert after["job_present"] is False, after
        assert after["rows"], "the purge deleted the job, not its audit trail"
        assert {r["job_disposition"] for r in after["rows"]} == {AUDIT_JOB_PURGED}
        # The other tenant of rows is untouched by this job's filter.
        assert {r["job_id"] for r in store.audit_trail(limit=100, job_id=other)["rows"]} == {
            other
        }
    finally:
        abandoned = _purge_jobs_under(store, "/test/audit-filter")
        with store.connection() as conn:
            cur = conn.cursor()
            for leftover in [mine, other, *abandoned]:
                cur.execute("DELETE FROM audit_logs WHERE job_id = %s", (leftover,))


# ── #98: a test must never be a source of unexplained audit rows ──────

TESTS_ROOT = Path(__file__).resolve().parents[1]
STORAGE_MYSQL = REPO_ROOT / "storage" / "mysql.py"

#: The statement, lower-cased, because the ban is about the *write*, not about
#: how someone typed it.
JOB_ROW_DELETE = "delete from verification_jobs"


def _job_deletes_in_tests() -> list[str]:
    """Every test file that removes job rows without going through the store.

    Derived by walking ``tests/`` rather than from a hand-typed list: a new
    teardown is exactly what this gate exists to catch.
    """
    here = Path(__file__).resolve()
    hits: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if path.resolve() == here:
            continue  # this file declares the ban, so it has to name the statement
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if JOB_ROW_DELETE in line.lower():
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{number}")
    return hits


def test_no_test_reaches_past_the_product_delete_path() -> None:
    """Job rows may only leave via ``delete_job_records``.

    #95 measured 112 dangling audit rows in the test schema and attributed them
    to teardowns: audit_logs outlives the job on purpose, so removing a job row
    in place turns a documented deletion into data an operator has to
    investigate — and trains them to ignore the column that flags it.
    """
    hits = _job_deletes_in_tests()
    assert not hits, (
        f"{hits} delete job rows in place; call MySQLStore.delete_job_records "
        "(it writes its own explanation in the same transaction) and clear "
        "audit_logs for the id as well when the trail is only test residue"
    )


def test_the_ban_has_something_to_ban() -> None:
    """Reverse direction: the product path must still own exactly one job delete.

    Otherwise the scan above turns green by the protected statement vanishing,
    which is the vacuous-green failure mode #81 had to guard against.
    """
    text = STORAGE_MYSQL.read_text(encoding="utf-8")
    assert text.lower().count(JOB_ROW_DELETE) == 1, (
        "storage/mysql.py no longer holds exactly one in-place job delete — "
        "the #98 ban is protecting nothing and needs re-pointing"
    )
    assert "def delete_job_records" in text, (
        "the sole owner of the job-row delete is gone; #98's ban named it as "
        "the path tests must use"
    )
