"""#541: the plane a census reads must be derived, and its exclusion test must
stop at the checkout's own root.

Two failures, one disease. A scanning gate answers "how many copies of X are
there in the product?" and to do that it has to know two things: which
directories count as the product, and which directories to skip inside them.
#525 and #526 each typed both by hand, and #541 measured what that costs:

* the two typed planes disagreed with each other (14 roots vs 13, the difference
  being ``experiments``) and neither opened ``mcp``, ``ops``, ``devtools`` or
  ``plugins`` — so "exactly one definition in the product" was a claim about two
  different products;
* the skip test read **absolute** path components, so the same code that counted
  302 product modules in a normal checkout counted **0** in a worktree under
  ``.scratch`` — which is where every lane runs its arms. Four legs of #526's
  gate then reported "no stray copy" about a census that had read nothing, while
  #525's floored leg admitted it was blind.

A third blindness turned up while writing this file, and it is the same disease
one level down: a census is also a *reader*, and one tracked file began with a
UTF-8 BOM, so the ``read_text(encoding="utf-8")`` + ``ast.parse`` that 188
modules under ``tests/`` write raised on it and the ones with
``except SyntaxError: continue`` dropped it in silence.

The repair is the owner in ``tests/_scan_walk.py``; the legs below hold the
repair's properties and keep the remaining hand-typed planes visible as a roster
instead of letting them become invisible again.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_PROJECT_ROOT),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests._scan_walk import (  # noqa: E402
    NON_PRODUCT_ROOTS,
    PRUNE_DIRS,
    product_python_files,
    product_roots,
    tracked_python_roots,
    walk_files,
)

REPO = _PROJECT_ROOT
TESTS = REPO / "tests"
THIS_FILE = "tests/unit/test_the_plane_a_scan_reads_is_derived_not_typed.py"

#: The demo-marker family: the gates that census "how many copies of this
#: predicate does the product hold". They are the population #541 lands in, so
#: they are the population the floor rule is enforced on.
DEMO_FAMILY = (
    "tests/unit/test_every_job_read_publishes_the_demo_fact.py",
    "tests/unit/test_the_demo_marker_has_one_owner_on_both_sides_of_the_sql.py",
    THIS_FILE,
)

#: Gates that still read a narrower plane than the derived one. The number is
#: the debt register, not an endorsement: every entry says what its census asks
#: and what its plane therefore cannot see. A gate joins this roster by stating
#: a reason, and `test_a_typed_plane_is_a_roster_not_a_forgotten_file` fails if a
#: new declarer appears without joining — which is how #525 and #526 both ended up
#: typing a plane nobody checked.
TYPED_PLANES: dict[str, str] = {
    "tests/conftest.py": (
        "_SCAN_DIRS is 6 roots for the fixture sweep; it cannot see a violation "
        "anywhere else in the plane and does not claim to"
    ),
    "tests/unit/test_audit_action_parity.py": (
        "PRODUCTION_LANES is 6 roots: the audit-action vocabulary is only written "
        "by lanes that emit one; #541 measured that its 166-module plane leaves "
        "152 product modules unopened, and fixed its skip test to read relative parts"
    ),
    "tests/unit/test_checker_type_parity.py": (
        "PRODUCER_PACKAGES is 6 roots: the checker-type vocabulary is only written "
        "by the lanes that hand a verdict to the checker"
    ),
    "tests/unit/test_evidence_vocabulary_parity.py": (
        "PRODUCER_PACKAGES is 7 roots: evidence-kind writers only, so an "
        "evidence kind minted in `storage` outside those lanes is invisible here"
    ),
    "tests/unit/test_observability_metric_parity.py": (
        "EMIT_DIRS is 9 roots: metric emitters only; a metric in `contracts` or "
        "`retrieval` is not its question, but this gate cannot see one either"
    ),
    "tests/unit/test_severity_vocabulary_parity.py": (
        "PRODUCER_PACKAGES is 7 roots: severity writers only"
    ),
    "tests/unit/test_silent_broad_catches_carry_a_reason.py": (
        "_ROOTS is 13 roots and omits `contracts`, `devtools`, `ops`, `plugins` "
        "and `scripts`; #541 measured that widening it to the derived plane moves "
        "its floor count by exactly +1, so the CI-red floor is not this hole"
    ),
    "tests/unit/test_sql_text_static.py": (
        "PACKAGES is 10 roots of SQL-bearing code; #526 already changed its count "
        "floor, and an SQL literal in `mcp` or `ops` would not be seen here"
    ),
    "tests/unit/test_subprocess_text_encoding.py": (
        "PINNED_SCOPES names 13 roots to enumerate subprocess sites, not to census "
        "copies of a predicate"
    ),
    "tests/unit/test_verdict_channel_parity.py": (
        "SCAN_ROOTS is 13 roots; another lane holds this file open at #541's "
        "baseline, so #541 registers it in ABSOLUTE_PARTS instead of editing it"
    ),
}

#: Scans that still test a pruned name against **absolute** path components.
#: One entry each, with why #541 did not fix it in this number. Both real entries
#: are characterisation helpers over a `tmp_path` fixture rather than over the
#: checkout: rewriting them would change *what they replay*, which is the opposite
#: of a repair. The hazard is still theirs — a pytest tmp directory that happened to
#: sit under a pruned name would empty the reference census the same way #541
#: measured for the demo gates — so they are recorded as debt, not as clean.
ABSOLUTE_PARTS: dict[str, str] = {
    "tests/unit/test_craft_gates_serve_every_language_the_product_names.py": (
        "`target.parts` inside `_reference_detector`, whose own docstring says "
        "it is 'What craft did before #423: one glob per pattern, filtered afterwards'. "
        "It walks a fixture `workspace` built by the test, not the checkout, and its "
        "prune list is `craft.gates._SKIPPED_DIR_PARTS` — the product's own list, read "
        "so the legacy answer is the legacy answer. Making it relative would edit the "
        "thing under characterisation"
    ),
    "tests/unit/test_the_plane_a_scan_reads_is_derived_not_typed.py": (
        "`path.parts` in `test_an_absolute_exclude_test_blinds_a_nested_checkout`, "
        "the leg whose whole assertion is that the old absolute rule returns [] on the "
        "fixture checkout at `.scratch/wt999`. It is the deleted shape, replayed on "
        "purpose; the sibling leg `test_pruning_ignores_where_the_checkout_lives` is "
        "the repair, and the pair is what makes this file's claim measurable rather "
        "than asserted"
    ),
    "tests/unit/test_verdict_channel_parity.py": (
        "`SKIP_DIR_PARTS & set(path.parts)` — the list names `.git`, `.venv`, "
        "`node_modules`, `__pycache__`, so a checkout nested under any of them "
        "collapses this census exactly the way #541 measured for the demo gates. "
        "The file is dirty in the shared checkout at this baseline: another lane "
        "owns the edit, so the shape is registered rather than silently kept"
    ),
}


# ── helpers ───────────────────────────────────────────────────────────────────


def _module(path: Path) -> ast.Module:
    """Parse a source file the way a scanner must: `utf-8-sig`, not `utf-8`.

    #541 found one tracked file — `tests/unit/test_eval_resume_reuses_measured_cases.py`
    — whose first bytes are a UTF-8 BOM, which makes `read_text(encoding="utf-8")`
    followed by `ast.parse` raise `SyntaxError: invalid non-printable character
    U+FEFF`. 188 modules under `tests/` write exactly that read shape, so the file
    was invisible to every AST census in the repo, and the ones that write
    `except SyntaxError: continue` dropped it without a word. This is the third way
    a census goes blind — not the roots, not the geography, the reader's own decode.
    #541 stripped the BOM and
    `test_no_module_a_census_reads_defeats_the_census_reader` keeps it from coming back.
    """
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def _root_name_lists(tree: ast.Module) -> list[tuple[str, tuple[str, ...]]]:
    """Module-level tuple/list/set literals of >=6 strings that are all tracked roots."""
    roots = set(tracked_python_roots(REPO))
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in tree.body:
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
            continue
        vals = tuple(
            e.value for e in value.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        )
        if len(vals) >= 6 and set(vals) <= roots:
            target = (
                node.targets[0]
                if isinstance(node, ast.Assign) and node.targets
                else getattr(node, "target", None)
            )
            name = getattr(target, "id", "?")
            found.append((name, vals))
    return found


def _exclusion_literals(tree: ast.Module) -> bool:
    """Does this module name a directory the owner prunes?

    Any string constant, not only a container literal: a gate that writes
    `if "__pycache__" in path.parts` prunes exactly as surely as one that writes
    a SKIP_DIRS set, and #541's finding is about the *shape* of the test, not
    how many names it carries.
    """
    prune = set(PRUNE_DIRS)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and (node.value in prune or node.value.startswith(".venv"))):
            return True
    return False


def _walks(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Attribute) and node.attr in {"rglob", "glob"}
        or isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"walk_files", "walk"}
        for node in ast.walk(tree)
    )


def _relative_names(tree: ast.Module) -> set[str]:
    """Names bound to something already made repo-relative, anywhere in the module."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)
            and v.func.attr == "relative_to" for v in ast.walk(node.value)
        ):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.add(t.id)
    return out


def _is_relative_read(receiver: ast.expr, relative: set[str]) -> bool:
    """Whether a `.parts` receiver was built below the checkout root.

    A chain counts: `rel.with_suffix("").parts` is as repo-relative as
    `rel.parts`, and the walk-root call itself (`p.relative_to(ROOT).parts`) is the
    shape the rule asks for. Dropping `with_suffix`/`parent`/`as_uri`-style hops
    would instead roster a false positive, and a roster full of those is a roster
    nobody reads.
    """
    for node in ast.walk(receiver):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "relative_to":
            return True
        if isinstance(node, ast.Name) and (node.id in relative or node.id.startswith("rel")):
            return True
    return False


def _absolute_parts_lines(tree: ast.Module) -> list[int]:
    """`.parts` reads that are not on a repo-relative path.

    `parents` is excluded on purpose: `Path(__file__).resolve().parents[2]` is how
    a module *finds* the checkout, which is the one place an absolute path is the
    right answer.
    """
    relative = _relative_names(tree)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "parts"):
            continue
        if _is_relative_read(node.value, relative):
            continue
        offenders.append(node.lineno)
    return sorted(set(offenders))


def _test_bodies(path: Path) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in _module(path).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def _has_numeric_floor(fn: ast.FunctionDef) -> bool:
    """An `assert <expr> >= <int>` where the int is large enough to be a census floor."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            for op, comparator in zip(node.test.ops, node.test.comparators, strict=True):
                if isinstance(op, (ast.GtE, ast.Gt)) and isinstance(comparator, ast.Constant) \
                        and isinstance(comparator.value, int) and comparator.value >= 100:
                    return True
    return False


# ── A: the plane is derived ───────────────────────────────────────────────────


def test_the_product_plane_is_derived_from_the_index() -> None:
    """The roots come from what the repo tracks, not from what someone typed."""
    tracked = tracked_python_roots(REPO)
    plane = product_roots(REPO)
    assert plane == tracked - NON_PRODUCT_ROOTS, (
        f"the plane is not `tracked - classified`: {sorted(tracked - plane)} are "
        "named excluded and the rest of the arithmetic does not close"
    )
    assert len(tracked) >= 15, f"root census collapsed: {sorted(tracked)}"
    for root in sorted(plane):
        assert (REPO / root).is_dir(), f"{root} is tracked but has no directory"
    missing = NON_PRODUCT_ROOTS - tracked
    assert not missing, (
        f"{sorted(missing)} are excluded from the plane but hold no tracked Python — "
        "an exclusion that no longer names anything is how a stale list hides a root"
    )


def test_the_three_owners_of_the_plane_agree() -> None:
    """Shipped, tracked and classified are three answers about one repo.

    #541 found the plane had nine answers. It does not need a tenth: the
    packaging allow-list is the definition of "ships", the index is the
    definition of "is in the repo", and the owner is the definition of "a census
    reads this". They must nest.
    """
    from tests.unit.test_packaging_ships_every_imported_package import shipped_packages

    shipped = set(shipped_packages())
    plane = set(product_roots(REPO))
    assert shipped, "probe broken: the shipping allow-list parsed empty"
    assert shipped <= plane, (
        f"{sorted(shipped - plane)} ship in the product but are outside the plane a "
        "census reads — a copy there is invisible to every derived census"
    )


def test_the_derived_plane_is_not_empty_where_a_gate_claims_a_census() -> None:
    """The floor is the discovery, not the formality: #526 had no floor leg."""
    rows = product_python_files(REPO)
    assert len(rows) >= 250, f"only {len(rows)} product modules — the walk read nothing"
    rels = {rel for _, rel in rows}
    assert len(rels) == len(rows), "the walk yielded one path twice: two roots overlap"
    assert any(rel.startswith("mcp/") for rel in rels), (
        "`mcp` is back outside the plane: #525/#526 typed 13 and 14 roots and "
        "neither opened it, which is the hole this file exists to close"
    )


def test_no_module_a_census_reads_defeats_the_census_reader() -> None:
    """A file the reader cannot decode is a file the census does not contain.

    The populations are the two a scanning gate can read: the derived product
    plane and the test tree the meta-scans census. Both are parsed the way 188
    modules under ``tests/`` parse — ``read_text(encoding="utf-8")`` bytes, then
    ``ast.parse`` — and anything that raises is reported rather than skipped.
    """
    unreadable: list[tuple[str, str]] = []
    paths = [path for path, _rel in product_python_files(REPO)]
    paths += [
        path for path in sorted(TESTS.rglob("*.py"))
        if "__pycache__" not in path.relative_to(REPO).as_posix().split("/")
    ]
    seen: set[str] = set()
    for path in paths:
        rel = path.relative_to(REPO).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        try:
            ast.parse(path.read_bytes().decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            unreadable.append((rel, f"{type(exc).__name__}: {exc}".split("\n")[0][:90]))
    assert not unreadable, (
        f"{unreadable} cannot be parsed the way the repo's scanners parse: an AST "
        "census silently omits them (`except SyntaxError: continue` reports 'no copy "
        "found'), so a BOM or a bad byte makes a whole file un-censusable"
    )


# ── B: the checkout's own address is not evidence ─────────────────────────────


def _nested_checkout(tmp_path: Path) -> Path:
    """A checkout whose *ancestor* is a name the walk prunes.

    That is not a hypothetical: every lane of this project runs its arms in
    ``.scratch/wtNNN``, and #541 measured the two demo gates reading 0 modules
    there while reading 302 in the shared checkout.
    """
    checkout = tmp_path / ".scratch" / "wt999"
    (checkout / "agent").mkdir(parents=True)
    (checkout / "agent" / "job_control.py").write_text(
        "X = 'SELECT 1 AS is_demo FROM t'\n", encoding="utf-8"
    )
    (checkout / "agent" / "__pycache__").mkdir()
    (checkout / "agent" / "__pycache__" / "job_control.py").write_text(
        "X = 'cached'\n", encoding="utf-8"
    )
    return checkout


def test_pruning_ignores_where_the_checkout_lives(tmp_path: Path) -> None:
    checkout = _nested_checkout(tmp_path)
    rows = walk_files(checkout, frozenset({".py"}))
    rels = sorted(rel for _, rel in rows)
    assert rels == ["agent/job_control.py"], (
        f"a checkout under a pruned directory name yielded {rels}; the walk is "
        "supposed to prune by directory NAME, never by the checkout's own address"
    )


def test_an_absolute_exclude_test_blinds_a_nested_checkout(tmp_path: Path) -> None:
    """The same files, the rule #541 removed: the census is empty, the scan says so.

    This leg is a characterisation of the deleted shape, so it passes when the
    shape is *absent from production code* and would keep passing if it were
    restored — its job is to prove the leg above measures ancestry, not luck.
    """
    checkout = _nested_checkout(tmp_path)
    rows = walk_files(checkout, frozenset({".py"}))
    kept_by_the_old_rule = [
        rel for path, rel in rows if not any(part in PRUNE_DIRS for part in path.parts)
    ]
    assert kept_by_the_old_rule == [], (
        f"the absolute rule kept {kept_by_the_old_rule}; then `.scratch` in an "
        "ancestor is no longer enough to collapse a census and this file's reason "
        "for existing needs re-measuring"
    )


# ── C: the family this number landed in ──────────────────────────────────────


def test_the_two_demo_gates_read_one_derived_plane() -> None:
    """#525 typed 14 roots and #526 typed 13 of them — for the same question."""
    from tests.unit import (
        test_every_job_read_publishes_the_demo_fact as gate_526,
    )
    from tests.unit import (
        test_the_demo_marker_has_one_owner_on_both_sides_of_the_sql as gate_525,
    )

    expected = len(product_python_files(REPO))
    for label, census in (
        ("gate525", gate_525.PRODUCTION_FILES),
        ("gate526", gate_526.PRODUCTION_FILES),
    ):
        assert len(census) == expected, (
            f"{label} reads {len(census)} modules, the owner reads {expected}: "
            "two censuses of one plane is the state #541 opened on"
        )


def test_a_census_gate_that_reads_the_plane_floors_it() -> None:
    """Every member of the demo family must be able to say 'I read nothing'."""
    unfloored = []
    for rel in DEMO_FAMILY:
        bodies = _test_bodies(REPO / rel)
        if not any(_has_numeric_floor(fn) for fn in bodies.values()):
            unfloored.append(rel)
    assert not unfloored, (
        f"{unfloored} census the product plane with no numeric floor anywhere: "
        "a blind walk would then report 'no stray copy' for free, which is exactly "
        "what #541 measured in a nested checkout (4 legs of "
        "test_every_job_read_publishes_the_demo_fact.py passed over an empty census "
        "while #525's floored leg went red)"
    )


# ── D: the rest of the typed planes stay visible ─────────────────────────────


def test_a_typed_plane_is_a_roster_not_a_forgotten_file() -> None:
    declarers = _declarers()
    unregistered = sorted(set(declarers) - set(TYPED_PLANES))
    stale = sorted(set(TYPED_PLANES) - set(declarers))
    assert not unregistered, (
        f"{unregistered} declare a production plane of their own without a reason "
        "here. Either read the derived plane through tests/_scan_walk.py or state "
        "what narrower question this census asks"
    )
    assert not stale, (
        f"{stale} are on the roster but no longer type a plane; delete the entry "
        "so the register describes the tree"
    )
    for rel, reason in TYPED_PLANES.items():
        assert len(reason) >= 40, f"{rel}'s reason is not a measurement: {reason!r}"


def test_every_typed_plane_names_real_roots() -> None:
    """A typed plane may be narrow; it may not be fictional."""
    plane = set(product_roots(REPO))
    for rel, names in _declarers().items():
        declared = {root for _name, roots in names for root in roots}
        invented = sorted(declared - plane)
        assert not invented, (
            f"{rel} scans {invented}: not a tracked Python root outside the two "
            "classified non-product roots — the name is stale or the file is not "
            "product code"
        )


def test_no_scan_may_test_a_pruned_name_against_an_absolute_path() -> None:
    offenders: dict[str, list[int]] = {}
    for path in sorted(TESTS.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if "__pycache__" in rel.split("/"):
            continue
        tree = _module(path)
        if not (_walks(tree) and _exclusion_literals(tree)):
            continue
        lines = _absolute_parts_lines(tree)
        if lines:
            offenders[rel] = lines
    unregistered = sorted(set(offenders) - set(ABSOLUTE_PARTS))
    assert not unregistered, (
        f"{unregistered} prune on absolute components {[(r, offenders[r]) for r in unregistered]}: "
        "#541 measured that this reads the checkout's ancestors, so the same gate "
        "counts 302 modules in one directory and 0 in another. Register a reason or "
        "read the path below the walk root"
    )
    stale = sorted(set(ABSOLUTE_PARTS) - set(offenders))
    assert not stale, (
        f"{stale} are registered as absolute-part scanners but no longer are — "
        "fix the register so the next reader can trust it"
    )


def _declarers() -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    out: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for path in sorted(TESTS.rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        if "__pycache__" in rel.split("/"):
            continue
        try:
            tree = _module(path)
        except SyntaxError:
            continue
        lists = _root_name_lists(tree)
        if lists:
            out[rel] = lists
    return out
