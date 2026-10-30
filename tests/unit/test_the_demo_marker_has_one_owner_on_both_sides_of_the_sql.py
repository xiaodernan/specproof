"""#525 — the marker that separates seeded demo data has one owner, on both sides.

``summary.retrieval_note`` is the only field the database is asked about when it
decides whether a verification job is sample data:

    CASE WHEN JSON_VALID(summary) THEN LOCATE(prefix, JSON_UNQUOTE(
        JSON_EXTRACT(summary, '$.retrieval_note'))) = 1 ELSE 0 END AS is_demo

``apps/web`` renders that column as the 演示 badge, beside a sentence promising
"标有“演示”的记录为示例数据". Before #525 the prefix was written down three times
in two files — once by the seeder that puts it in the row, once inside each of
the two SELECT lists that read it back — and there was no test on either side of
that coupling.

#525 measured how invisible that was, on the commit before it landed (arm P0/P1
in docs/operations/DEEP_OPTIMIZATION_PLAN.md ## #525): the seed note's prefix and
both SQL literals were each renamed in turn, and the 23-file population of tests
that can name the marker, the field, the badge or either query answered with
zero reds. A drift that makes three fabricated verifications render as ordinary
real work is not caught by anything that runs offline.

This gate is the pair of claims that closes it:

  A ownership   the marker is one constant, in one module, and it appears in no
                  executed SQL text anywhere;
  B read side   both statements are EXECUTED here against a fake cursor, so the
                  prefix is proven to arrive as a bound parameter at the
                  placeholder that ``LOCATE`` occupies — with placeholder/param
                  arity checked on every statement, because an argument added in
                  the wrong position is a type error at the server, not a red;
  C write side  the seeded note is built by the owner, and its marker is at
                  position 1 for all three demo templates;
  D semantics   ``LOCATE(x, y) = 1`` and ``y.startswith(x)`` are shown to agree
                  over a table of note shapes, and shown to DIFFER from
                  ``> 0`` — which is what makes the ``= 1`` load-bearing rather
                  than decorative;
  E direction   what a drift costs: the badge's only feed is this column, no
                  second authority recomputes it in the API process, and the
                  promise text is still next to the badge;
  F neighbours  the two existing tests that used to assert "the tenant id is
                  params[0]" now derive the index from the placeholder order, so
                  a leading parameter cannot silently flip them into witnesses of
                  the wrong thing.

Legs that need MySQL to be believed are marked as such in the ledger, not here:
everything below runs offline against this repository's own text and code paths.
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

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
for _p in (str(_PROJECT_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import seed_demo  # noqa: E402

from contracts.demo_marker import DEMO_NOTE_PREFIX, seeded_demo_note  # noqa: E402
from storage.mysql import MySQLStore  # noqa: E402
from storage.tenant_scope import TENANT_SCOPE_VAR, TenantScope  # noqa: E402
from tests._scan_walk import product_python_files  # noqa: E402

REPO = _PROJECT_ROOT
MYSQL = REPO / "storage" / "mysql.py"
OWNER = REPO / "contracts" / "demo_marker.py"
SEEDER = REPO / "scripts" / "seed_demo.py"

#: The plane a second copy of the predicate could appear in. #541 replaced the
#: hand-typed tuple (14 roots, five packages short of what the repo actually
#: tracks) with the one derived owner: the roots come from `git ls-files`, and
#: the exclusion test reads the path below the walk root, because
#: `any(part in SKIP_DIRS for part in path.parts)` returned 302 modules in a
#: normal checkout and 0 in a worktree nested under `.scratch`.
PRODUCTION_FILES = product_python_files(REPO)

#: Files whose executed constants may contain the owner's prefix besides the
#: owner itself, because their text is ordinary prose that happens to spell it.
#: The rule below is a SUBSET, not an equality: a new file anywhere in the
#: production plane is red, while the decoy dropping out (if the prefix is
#: renamed and this phrase stops matching) is not.
PREFIX_LOOKALIKES: dict[str, str] = {
    "scripts/seed_demo.py": (
        "_requirements_text()'s fallback spec body — it holds the prefix NOT at "
        "position 1, so the predicate reads such a row as real work; leg D builds "
        "that shape from the owner rather than depending on this string's spelling"
    ),
}

#: The fragment the tenant predicate is built from, and the fragment LOCATE is
#: built from. Kept as text on purpose: leg B looks up a parameter's index by
#: counting placeholders BEFORE these fragments, which is the only index that
#: stays true when a leading parameter is added.
TENANT_FRAGMENT = "(tenant_id = %s OR tenant_id IS NULL)"
LOCATE_FRAGMENT = "LOCATE("


# ── helpers ──────────────────────────────────────────────────────────────────


def _docstring_nodes(module: ast.Module) -> set[int]:
    """id() of every string constant that is a docstring, not executed data."""
    out: set[int] = set()
    for node in ast.walk(module):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            out.add(id(first.value))
    return out


def _string_constants_containing(marker: str) -> list[tuple[str, int, str]]:
    """(file, line, value) for executed string constants holding *marker*.

    Docstrings are excluded: a sentence about the marker is not a second copy of
    it (#524's queue ⑤ is about exactly this distinction — a census that reads
    prose witnesses claims the code never made).
    """
    hits: list[tuple[str, int, str]] = []
    for path, module_rel in PRODUCTION_FILES:
        module = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = _docstring_nodes(module)
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and marker in node.value
                and id(node) not in docstrings
            ):
                hits.append((module_rel, node.lineno, node.value))
    return hits


def _placeholder_index(sql: str, fragment: str) -> int:
    """How many ``%s`` appear before *fragment* — which parameter it occupies."""
    position = sql.index(fragment)
    return sql[:position].count("%s")


class _Cursor:
    def __init__(self, sink: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._sink = sink

    def execute(self, sql: str, params: Any) -> None:
        self._sink.append((sql, tuple(params)))

    def fetchone(self) -> dict[str, Any]:
        return {"total": 1}

    def fetchall(self) -> list[dict[str, Any]]:
        return []


@contextlib.contextmanager
def _capturing_store(scope: TenantScope | None) -> Iterator[list[tuple[str, tuple[Any, ...]]]]:
    """Run both real query paths offline; every statement they emit is captured."""

    class _Connection:
        def cursor(self) -> _Cursor:
            return _Cursor(cap)

    cap: list[tuple[str, tuple[Any, ...]]] = []

    @contextlib.contextmanager
    def connection(self: MySQLStore) -> Iterator[_Connection]:
        yield _Connection()

    original = MySQLStore.connection
    MySQLStore.connection = connection  # type: ignore[method-assign]
    token = TENANT_SCOPE_VAR.set(scope)
    try:
        store = MySQLStore()
        store.search_jobs(25, 25, "BLOCKED", "checkout")
        store.dashboard_snapshot(datetime(2026, 9, 18))
        yield cap
    finally:
        TENANT_SCOPE_VAR.reset(token)
        MySQLStore.connection = original  # type: ignore[method-assign]


VIEWER = TenantScope("tenant-a", user_id="u1", roles=frozenset({"viewer"}))


def _demo_statements(
    cap: list[tuple[str, tuple[Any, ...]]],
) -> list[tuple[str, tuple[Any, ...]]]:
    return [(sql, params) for sql, params in cap if "AS is_demo" in sql]


#: On #525's base exactly two executed statements computed ``is_demo``. That was
#: an observation about which methods ``_capturing_store`` happens to call, not a
#: contract about the column — and the gap it hid is what #526 filed: the detail
#: page's two reads computed nothing at all, and a leg that counted statements
#: could not see a statement that was never issued. So these legs keep a FLOOR
#: (the blindness check: did the capture reach the window reads?) and the
#: question "does every surface that ships a job row publish the fact" moved to
#: ``test_every_job_read_publishes_the_demo_fact.py``, which derives its
#: population from the API call graph rather than from a remembered number.
MIN_DEMO_STATEMENTS = 2


def _require_demo_statements(demo: list[Any], label: str) -> None:
    assert len(demo) >= MIN_DEMO_STATEMENTS, (
        f"{label}: expected at least {MIN_DEMO_STATEMENTS} executed statements "
        f"computing is_demo, got {len(demo)} — the capture stopped reaching the "
        "window reads, and every leg below would iterate over nothing"
    )


# ── A: ownership ─────────────────────────────────────────────────────────────


def test_the_prefix_is_one_executed_constant_in_the_production_plane() -> None:
    hits = _string_constants_containing(DEMO_NOTE_PREFIX)
    owner_files = {rel for rel, _, _ in hits if rel == "contracts/demo_marker.py"}
    strays = {rel for rel, _, _ in hits if rel != "contracts/demo_marker.py"}
    assert owner_files == {"contracts/demo_marker.py"}, (
        f"the owner no longer executes its own prefix as a constant: {hits}"
    )
    assert strays <= set(PREFIX_LOOKALIKES), (
        f"{sorted(strays - set(PREFIX_LOOKALIKES))} executes the prefix as data; "
        f"only {sorted(PREFIX_LOOKALIKES)} is a documented lookalike. "
        f"Full census: {[(rel, line, value[:60]) for rel, line, value in hits]}. "
        "A second copy is the drift #525 found — the seeder and the SQL each "
        "carried their own, and no test could see them disagree."
    )
    for rel in strays:
        assert len(PREFIX_LOOKALIKES[rel]) >= 30, (
            f"{rel} is allowlisted with a reason too short to review"
        )


def test_the_owner_holds_exactly_one_definition_of_the_prefix() -> None:
    module = ast.parse(OWNER.read_text(encoding="utf-8"))
    assigned = [
        node
        for node in ast.walk(module)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Name) and t.id == "DEMO_NOTE_PREFIX"
            for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
    ]
    assert len(assigned) == 1, f"DEMO_NOTE_PREFIX is assigned {len(assigned)} times in the owner"
    value = assigned[0].value
    assert isinstance(value, ast.Constant) and value.value == DEMO_NOTE_PREFIX, (
        "the owner's prefix must be a literal constant — a computed prefix would "
        "make the census above unable to name what it is guarding"
    )


def test_the_prefix_appears_in_no_executed_sql_text() -> None:
    """The drift-proof half: SQL text carries a placeholder, not the contract."""
    text = MYSQL.read_text(encoding="utf-8")
    assert DEMO_NOTE_PREFIX not in text, (
        "storage/mysql.py hardcodes the prefix again — with a literal inside the "
        "SELECT list it has a second owner and the seeder can no longer move it"
    )
    assert "IS_DEMO_COLUMN" in text, (
        "storage/mysql.py no longer builds its demo projection from the owner's "
        "fragment — an inline copy is the second owner #525 was filed against, "
        "and #526 moved the text out so a read cannot re-type it differently"
    )
    owner_text = OWNER.read_text(encoding="utf-8")
    assert "LOCATE(%s, JSON_UNQUOTE(" in owner_text, (
        "the demo predicate no longer binds its prefix as a parameter; either the "
        "shape moved (update this gate and say why) or the value went back into text"
    )


def test_the_seeder_builds_its_note_through_the_owner() -> None:
    module = ast.parse(SEEDER.read_text(encoding="utf-8"))
    called: list[int] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if (
                isinstance(key, ast.Constant)
                and key.value == "retrieval_note"
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "seeded_demo_note"
            ):
                called.append(node.lineno)
    assert called, (
        "seed_demo writes retrieval_note without seeded_demo_note() — the writer "
        "must go through the owner or the read side drifts behind its back"
    )


def test_the_census_is_not_blind() -> None:
    """A census that read nothing would report 'no stray copies' for free."""
    scanned = len(PRODUCTION_FILES)
    quote_chars = sum(
        path.read_text(encoding="utf-8").count('"') for path, _ in PRODUCTION_FILES
    )
    # Measured on #541's derived plane: 317 modules over 18 roots, 105249+ quote
    # characters (the 14-root list #525 typed reached 302 of those modules). The
    # floors sit well under the measurement so they only fire if the walk starts
    # skipping real code — which is what a worktree nested under `.scratch` did
    # to the old absolute-path filter: 302 became 0 and this leg said so.
    assert scanned >= 250, f"only {scanned} production modules scanned — census read nothing"
    assert quote_chars >= 40000, f"only {quote_chars} string characters seen; the walk is shallow"


def test_the_marker_shape_is_a_plain_prefix() -> None:
    assert DEMO_NOTE_PREFIX.strip() == DEMO_NOTE_PREFIX
    assert "%" not in DEMO_NOTE_PREFIX and "'" not in DEMO_NOTE_PREFIX
    assert " " in DEMO_NOTE_PREFIX, (
        "the prefix is a phrase, not a token — 'demo' alone would match ordinary "
        "notes and label real work as sample data"
    )


# ── B: the read side, executed ───────────────────────────────────────────────


def test_both_demo_statements_bind_the_prefix_at_the_locate_placeholder() -> None:
    with _capturing_store(VIEWER) as cap:
        demo = _demo_statements(cap)
        _require_demo_statements(demo, "the viewer capture")
        for sql, params in demo:
            at = _placeholder_index(sql, LOCATE_FRAGMENT)
            assert params[at] == DEMO_NOTE_PREFIX, (
                f"the parameter that reaches LOCATE is {params[at]!r}, not the "
                f"owner's {DEMO_NOTE_PREFIX!r} — the badge would be computed from "
                "a different string than the one the seeder writes"
            )


def test_the_executed_predicate_reads_a_placeholder_not_a_literal() -> None:
    """Arm A1's blind spot, closed: an index leg cannot see a placeholder vanish.

    ``_placeholder_index`` counts ``%s`` before ``LOCATE(``, and hardcoding the
    prefix back into the text leaves that count at zero while the owner is still
    the statement's first parameter — so the leg above passes on a broken read
    side. This leg reads the executed statement's own shape instead of its grid.
    """
    with _capturing_store(VIEWER) as cap:
        for sql, _ in _demo_statements(cap):
            assert "LOCATE(%s," in sql, (
                "the executed demo predicate no longer binds its prefix: "
                f"{sql[:150]!r}"
            )


def test_every_statement_sends_one_parameter_per_placeholder() -> None:
    """The mutation that would otherwise only fail at the server.

    mysqlclient formats the statement against its arguments, so an argument
    added without a placeholder — or a placeholder without an argument — is not a
    wrong answer, it is a raised TypeError inside every paginated list request.
    Arity is checked on all five statements, not only the demo ones.
    """
    with _capturing_store(VIEWER) as cap:
        assert len(cap) == 5, f"expected 5 statements (2 + 3), got {len(cap)}"
        for index, (sql, params) in enumerate(cap):
            assert sql.count("%s") == len(params), (
                f"statement {index} has {sql.count('%s')} placeholders and "
                f"{len(params)} parameters: {sql[:120]!r}"
            )


@pytest.mark.parametrize("statement", ["search_jobs list", "recent_jobs"])
def test_the_demo_predicate_is_caseguarded_and_answers_zero_elsewhere(
    statement: str,
) -> None:
    with _capturing_store(VIEWER) as cap:
        demo = _demo_statements(cap)
        _require_demo_statements(demo, statement)
        # keyed, not positional: with two window reads a [0]/[1] split works, and
        # with four production surfaces it silently reads the wrong statement.
        # The list window is the only demo statement that pages with an OFFSET.
        want_offset = statement.startswith("search")
        matches = [sql for sql, _ in demo if ("OFFSET" in sql) == want_offset]
        assert len(matches) == 1, (
            f"{statement}: {len(matches)} demo statements have the window shape"
        )
        sql = matches[0]
        assert "CASE WHEN JSON_VALID(summary) THEN" in sql, (
            f"{statement}: is_demo stopped guarding a non-JSON summary column"
        )
        assert "ELSE 0 END AS is_demo" in sql, (
            f"{statement}: a summary the database cannot parse now answers "
            "non-zero for is_demo — unreadable data would be labelled sample data"
        )
        # #526 wrapped the comparison in COALESCE(..., 0) so a summary that is
        # valid JSON without a retrieval_note answers 0, not NULL. The position-1
        # property is unchanged; the probe moved with the text, and it still
        # rejects "= 1" replaced by "> 0" (arm A5), which is the whole point.
        assert re.search(r"\)\)\) = 1[, ]", sql), (
            f"{statement}: the predicate is no longer position-1; see leg D for "
            "what '= 1' versus '> 0' costs"
        )
        assert "LIKE" not in sql, f"{statement}: the prefix match became a LIKE pattern"


def test_the_tenant_value_is_bound_at_the_tenant_placeholder_not_at_index_zero() -> None:
    """Derived index, so a leading parameter cannot silently move the witness."""
    with _capturing_store(VIEWER) as cap:
        for index, (sql, params) in enumerate(cap):
            if TENANT_FRAGMENT not in sql:
                assert "tenant_id" not in sql, f"statement {index}: tenant text without a value"
                continue
            at = _placeholder_index(sql, TENANT_FRAGMENT)
            assert params[at] == "tenant-a", (
                f"statement {index}: the placeholder that the tenant predicate "
                f"occupies is bound to {params[at]!r}"
            )


def test_the_count_statement_does_not_carry_the_demo_parameter() -> None:
    """Only the statements that PROJECT is_demo may pay for it.

    The COUNT shares the WHERE fragments with the list; if the prefix were
    prepended there too, arity would still match and the total would be computed
    against a stray argument — the kind of change that survives a text-only gate.
    """
    with _capturing_store(VIEWER) as cap:
        count_sql, count_params = cap[0]
        assert "COUNT(*) AS total" in count_sql
        assert "LOCATE(%s, JSON_UNQUOTE(" not in count_sql, (
            "the total query started computing is_demo; it never returns that column"
        )
        assert DEMO_NOTE_PREFIX not in count_params, count_params
        assert _placeholder_index(count_sql, TENANT_FRAGMENT) == 0
        assert count_params[0] == "tenant-a"


def test_an_auditor_scope_keeps_the_prefix_first_and_the_tenant_absent() -> None:
    """The demo predicate must not become scope-dependent."""
    auditor = TenantScope("tenant-a", user_id="u2", roles=frozenset({"auditor"}))
    with _capturing_store(auditor) as cap:
        demo = _demo_statements(cap)
        _require_demo_statements(demo, "the auditor capture")
        for sql, params in demo:
            assert "tenant_id" not in sql
            assert params[0] == DEMO_NOTE_PREFIX, (
                f"without a tenant predicate the prefix is no longer the first "
                f"parameter actually sent: {params!r}"
            )
            assert sql.count("%s") == len(params)


def test_no_scope_keeps_the_demo_predicate_working() -> None:
    """Tenant mode off is the deployed default for the local stack."""
    with _capturing_store(None) as cap:
        demo = _demo_statements(cap)
        _require_demo_statements(demo, "the scopeless capture")
        for sql, params in demo:
            assert params[0] == DEMO_NOTE_PREFIX
            assert sql.count("%s") == len(params)


def test_the_marker_text_appears_in_neither_executed_statement() -> None:
    with _capturing_store(VIEWER) as cap:
        offenders = [sql[:90] for sql, _ in cap if "seeded demo" in sql]
        assert not offenders, (
            f"the marker reached executed SQL text, so it has a second owner: {offenders}"
        )


# ── C: the write side ────────────────────────────────────────────────────────


@pytest.mark.parametrize("template_index", [0, 1, 2])
def test_every_seeded_summary_starts_with_the_owner_prefix(template_index: int) -> None:
    templates = seed_demo.demo_verify_templates()
    template = templates[template_index]
    job_id = str(seed_demo.stable_demo_uuid(f"verify:{template['key']}"))
    note = seed_demo._summary_for(template, job_id)["retrieval_note"]  # noqa: SLF001
    assert note.startswith(DEMO_NOTE_PREFIX), (
        f"seeded note {note!r} does not begin with the owner's prefix — LOCATE "
        "matches at position 1 only, so this row would render as real verification"
    )


def test_the_seeded_note_text_is_the_one_the_product_documents() -> None:
    templates = seed_demo.demo_verify_templates()
    template = templates[0]
    job_id = str(seed_demo.stable_demo_uuid(f"verify:{template['key']}"))
    note = seed_demo._summary_for(template, job_id)["retrieval_note"]  # noqa: SLF001
    assert note == "seeded demo data (\u3010\u6f14\u793a\u3011)", (
        f"the seeded note changed to {note!r}; JobDetail renders this field "
        "verbatim, so a rewrite is a user-visible copy change, not a refactor"
    )


def test_the_note_helper_cannot_move_the_marker_off_position_one() -> None:
    assert seeded_demo_note("data") == f"{DEMO_NOTE_PREFIX} data"
    assert seeded_demo_note("").startswith(DEMO_NOTE_PREFIX)
    for detail in ("", "x", "【演示】", "seeded demo elsewhere"):
        assert seeded_demo_note(detail).startswith(DEMO_NOTE_PREFIX), detail


def test_the_writer_and_the_reader_agree_on_every_seeded_row() -> None:
    """Round trip: what the seeder writes is what the predicate would match."""
    for template in seed_demo.demo_verify_templates():
        job_id = str(seed_demo.stable_demo_uuid(f"verify:{template['key']}"))
        note = seed_demo._summary_for(template, job_id)["retrieval_note"]  # noqa: SLF001
        assert locate_at_one(DEMO_NOTE_PREFIX, note) is True, note


# ── D: what '= 1' is doing ───────────────────────────────────────────────────


def locate_at_one(needle: str, haystack: str) -> bool:
    """MySQL's ``LOCATE(needle, haystack) = 1`` at a case-sensitive collation."""
    return haystack.find(needle) == 0


#: Note shapes spelled FROM the owner's prefix, so arm C1 (renaming it) moves
#: this table with the prefix instead of breaking it. The last column is what
#: both ``LOCATE(prefix, note) = 1`` and ``note.startswith(prefix)`` must answer.
_PREFIX_SHAPE_CASES: list[tuple[str, bool]] = [
    (f"{DEMO_NOTE_PREFIX} data", True),
    (DEMO_NOTE_PREFIX, True),
    ("", False),
    (f"{DEMO_NOTE_PREFIX.capitalize()} data", False),
    (f"  {DEMO_NOTE_PREFIX} data", False),
    ("demo data", False),
    (f"real note; {DEMO_NOTE_PREFIX} inside it", False),
    ("【演示】", False),
    (DEMO_NOTE_PREFIX[:-2], False),
    (f"{DEMO_NOTE_PREFIX}o", True),
    ("no match at all", False),
]


@pytest.mark.parametrize(("note", "expected"), _PREFIX_SHAPE_CASES)
def test_the_prefix_predicate_matches_at_position_one_only(
    note: str, expected: bool
) -> None:
    assert locate_at_one(DEMO_NOTE_PREFIX, note) is expected
    assert note.startswith(DEMO_NOTE_PREFIX) is expected, (
        "startswith and LOCATE(...)=1 must agree, or the two readings of the "
        "contract mean different rows"
    )


def test_the_shape_table_is_big_enough_to_be_a_witness() -> None:
    """A one-row table proves the shape of one row."""
    assert len(_PREFIX_SHAPE_CASES) >= 10
    assert sum(1 for _, expected in _PREFIX_SHAPE_CASES if expected) >= 2
    assert sum(1 for _, expected in _PREFIX_SHAPE_CASES if not expected) >= 5


def test_the_mid_string_shape_is_what_makes_the_equal_sign_load_bearing() -> None:
    """``> 0`` would label a real job whose note merely *mentions* the phrase.

    Built from the owner's prefix rather than from any file's text, so arm C1
    (renaming the prefix) moves this falsifier with it instead of breaking it.
    """
    decoy = f"Repository retrieval ok; {DEMO_NOTE_PREFIX} appears here only as prose"
    assert decoy.find(DEMO_NOTE_PREFIX) > 0, "the falsifier must be mid-string"
    assert locate_at_one(DEMO_NOTE_PREFIX, decoy) is False
    assert (DEMO_NOTE_PREFIX in decoy) is True, (
        "a mid-string occurrence is exactly what '> 0' would accept — this is the "
        "row shape arm A5 (= 1 -> > 0) has to go red on"
    )


def test_a_seeded_real_note_stays_on_the_correct_side_of_the_predicate() -> None:
    """The node's own notes are the rows that must NEVER get the badge."""
    with _capturing_store(VIEWER) as cap:
        assert cap, "the capture ran nothing"
    for note in (
        "No head workspace — repository retrieval skipped",
        "hybrid_rrf mode=hybrid_rrf hits=3",
        "Indexed 3 symbol chunks; 1 retrieved",
        "",
    ):
        assert locate_at_one(DEMO_NOTE_PREFIX, note) is False, note


def test_the_owner_prefix_is_ascii_lowercase_so_ci_servers_agree() -> None:
    """Boundary, not decoration: MySQL's default collation folds case.

    Under ``utf8mb4_0900_ai_ci`` the server's ``LOCATE`` is case-insensitive, so
    ``"Seeded demo data"`` would be labelled sample data by SQL while
    ``startswith`` says no. Pinning the prefix lowercase keeps the server and any
    Python reader of the same field answering the same rows today; widening the
    marker would silently re-open that gap.
    """
    assert DEMO_NOTE_PREFIX.lower() == DEMO_NOTE_PREFIX
    assert DEMO_NOTE_PREFIX.isascii(), "an ascii marker keeps both readings identical"


# ── E: what a drift costs ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "page", ["apps/web/src/pages/Jobs.tsx", "apps/web/src/pages/Dashboard.tsx"]
)
def test_the_badge_is_rendered_from_this_column_alone(page: str) -> None:
    text = (REPO / page).read_text(encoding="utf-8")
    assert "job.is_demo" in text, f"{page}: the badge no longer reads is_demo"
    # #526 made the field required, so the `!!` that used to sit here is no
    # longer guarding an absent property — but a ternary still has to be, and
    # this leg is the reason: MySQL answers 0, so `{job.is_demo && <span/>}`
    # evaluates to 0 and React draws a literal "0" on every real row.
    assert re.search(r"job\.is_demo\s*\?", text), (
        f"{page}: the badge stopped being a ternary; the comment above says "
        "what the && form draws for is_demo = 0"
    )
    assert "{job.is_demo &&" not in text, (
        f"{page}: the && form returns 0 for a real row and React renders it"
    )
    assert 'className="demo-label"' in text, f"{page}: the badge lost its class"


def test_the_promise_sitting_next_to_the_badge_is_still_there() -> None:
    """The sentence that makes a wrong is_demo a lie rather than a cosmetic miss."""
    text = (REPO / "apps/web/src/pages/Dashboard.tsx").read_text(encoding="utf-8")
    assert "示例数据" in text, (
        "Dashboard.tsx no longer tells the reader that badged records are sample "
        "data; if the copy moved, this gate and the product sentence must move together"
    )


def test_no_route_recomputes_is_demo_in_the_api_process() -> None:
    """One authority. A second definition in Python would drift from the SQL."""
    offenders: list[str] = []
    for path in sorted((REPO / "api" / "routes").rglob("*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(module):
            if isinstance(node, ast.Assign) and "is_demo" in ast.unparse(node.targets):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        f"{offenders} build is_demo in the route layer — the store's column is the "
        "single answer and a second one needs its own coupling test"
    )


def test_the_console_flag_is_a_different_question_and_stays_separate() -> None:
    """Measured, then deliberately not folded: agent_jobs has its own demo test.

    ``api/agent_runtime.py`` answers ``is_demo = not repo_path.strip()`` for the
    agent console. That column never reaches this predicate (different table), and
    renaming it to share the marker would make one word mean "no repo was given"
    and "this row was seeded" at the same time.
    """
    source = (REPO / "api" / "agent_runtime.py").read_text(encoding="utf-8")
    assert "is_demo = not repo_path.strip()" in source, (
        "the console's demo test changed shape; re-read this leg — it exists to "
        "record that this plane is NOT the one the SQL predicate reads"
    )
    assert "DEMO_NOTE_PREFIX" not in source, (
        "the console started importing the seeded-note marker; the two planes have "
        "different storage and must not share a rename"
    )


# ── F: neighbours ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["tests/unit/test_product_setup.py", "tests/unit/test_dashboard_performance.py"]
)
def test_the_neighbourhood_asserts_the_tenant_by_placeholder_not_by_index_zero(
    path: str,
) -> None:
    """Both files used to say "params[0] == 'tenant-a"' / params[:2] == (...).

    #525 added a leading parameter, so a literal index-0 witness would now be
    asserting that the *marker* is the tenant — red for the wrong reason, or worse,
    quietly edited back to green. They now count placeholders before the tenant
    fragment. This leg refuses the weak form so a later lane cannot reinstate it.
    """
    text = (REPO / path).read_text(encoding="utf-8")
    weak = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"params\[0\]\s*==\s*[\"']tenant-a", line)
        or re.search(r"params\[:2\]\s*==\s*\(", line)
    ]
    assert not weak, f"{path}: positional witness is back: {weak}"
    assert "tenant" in text and "%s" in text, (
        f"{path}: it no longer asserts tenant scoping at all"
    )


def test_the_neighbourhood_still_checks_both_queries_are_scoped() -> None:
    """The property they own must survive the move, or #525 traded a witness for a pass."""
    product = (REPO / "tests/unit/test_product_setup.py").read_text(encoding="utf-8")
    dashboard = (REPO / "tests/unit/test_dashboard_performance.py").read_text(encoding="utf-8")
    assert product.count("tenant_id = %s") >= 1
    assert "params[:2]" not in product
    assert dashboard.count("tenant_id") >= 2
    # Both witnesses still run the real store methods against a fake cursor; if
    # either stopped executing them, the scoping claim above is prose again.
    assert "MySQLStore().search_jobs(" in product
    assert "MySQLStore().dashboard_snapshot(" in dashboard
    assert "monkeypatch.setattr(MySQLStore" in dashboard + product


def test_the_gate_has_teeth_on_its_own_floor() -> None:
    """Self-check: the prefix census is capable of reporting a hit at all."""
    hits = _string_constants_containing(DEMO_NOTE_PREFIX)
    assert len(hits) >= 1, (
        f"the census found {len(hits)} executed constants carrying the owner's own "
        "prefix; even the owner must show up, or 'no stray copies' means 'no scan'"
    )
    owner_hits = [(rel, line) for rel, line, _ in hits if rel == "contracts/demo_marker.py"]
    assert len(owner_hits) >= 1, owner_hits
    # And the census still reports what it excluded: the node's docstring sentence
    # about the prefix is prose, not a copy (that distinction is #524 queue ⑤).
    prose = SEEDER.read_text(encoding="utf-8")
    assert "seeded demo" in prose, "the seeder's lookalike text moved; update the allowance"


def test_the_floor_of_this_file_is_not_a_vacuous_pass() -> None:
    """A copy of the drift scenario, run here rather than only as an arm."""
    broken_note = "demo data (\u3010\u6f14\u793a\u3011)"
    assert locate_at_one(DEMO_NOTE_PREFIX, broken_note) is False
    with _capturing_store(VIEWER) as cap:
        for sql, params in _demo_statements(cap):
            at = _placeholder_index(sql, LOCATE_FRAGMENT)
            assert params[at] != broken_note
            assert locate_at_one(str(params[at]), broken_note) is False, (
                "arm P0's drift: the seeded note would answer is_demo = 0 and the "
                "three fabricated jobs would render as ordinary real verification"
            )
