"""P2 unit tests — contract candidate compiler + family mapping."""

import pathlib

import pytest

import tests.conftest as _isolation
from agent.contracts.compiler import (
    candidates_from_constitution,
    compile_candidates,
    coverage_gaps,
    dedupe_candidates,
    family_id_for,
)
from agent.contracts.parser import parse_requirements

SPEC = """1. Authentication
   - Must reject unauthenticated requests with 401.

2. Transactional integrity
   - Email update must be atomic with token invalidation.
"""

#: The isolation contract's verdict for THIS session, read at import time.
#: ``tests/conftest.py`` decides it in ``pytest_configure``, which runs before
#: collection, so the value is already final when this module is imported.
_MYSQL_STATE = _isolation.MYSQL_ISOLATION[0]

#: ``contract propose`` reaches MySQL through ``ContractRegistry()``, so the
#: two cases that get past the zero-candidate branch need a live database.
#: Without one they raised ``pymysql.err.OperationalError`` — a RED that said
#: "the product is broken" where the truth was "this session has no database".
#: Measured: CI run 40574430562, ``tests-no-infra``, exactly two reds from
#: this file, both ``(2003, "Can't connect to MySQL server on 'localhost'")``.
#: A case that cannot run must SKIP; the job that has the database runs them
#: for real (``.github/workflows/ci.yml``, ``tests-with-infra``).
requires_mysql = pytest.mark.skipif(
    _MYSQL_STATE not in ("dedicated", "redirected"),
    reason=(
        "contract propose writes to MySQL through ContractRegistry(), and this "
        f"session's isolation verdict is {_MYSQL_STATE!r}: there is no "
        "reachable database, so the case would fail instead of skipping"
    ),
)


def test_compile_candidates_from_spec():
    parsed = parse_requirements(SPEC)
    candidates = compile_candidates(parsed.requirements)
    types = {c.checker_type for c in candidates}
    assert "http" in types
    assert "sql" in types
    for c in candidates:
        assert c.result == "UNVERIFIED"
        assert not c.approved  # candidates are proposals, not contracts


def test_family_mapping():
    assert family_id_for("http", "must reject unauthenticated requests") == "AUTH-01"
    assert family_id_for("sql", "must be atomic within a transaction") == "TRANSACTION-01"
    assert family_id_for("sql", "email must be unique") == "UNIQUE-01"
    assert family_id_for("redis", "old tokens must be invalidated") == "TOKEN_INVALIDATION-01"
    assert family_id_for("openapi", "api must stay compatible") == "BACKWARD_COMPATIBLE-01"
    assert family_id_for("rabbitmq", "event exactly once") == "EVENT_ONCE-01"


def test_constitution_rules_become_candidates():
    policy = ["Repository policy:\n- Must keep all endpoints authenticated.\n"]
    candidates = candidates_from_constitution(policy)
    assert len(candidates) == 1
    assert candidates[0].source == "constitution"
    assert candidates[0].checker_type == "http"


def test_dedupe_merges_equivalent_behaviours():
    parsed = parse_requirements(SPEC)
    spec_cands = compile_candidates(parsed.requirements)
    policy = ["- Must reject unauthenticated requests with 401.\n"]
    const_cands = candidates_from_constitution(policy)
    merged = dedupe_candidates(spec_cands + const_cands)
    http_rows = [c for c in merged if c.checker_type == "http"]
    assert len(http_rows) == 1
    assert http_rows[0].source == "spec"  # spec beats constitution


# --- §2.5: requirements that compile to nothing must be reported ----------
#
# Before coverage_gaps() these requirements were simply omitted from the
# candidate list. Two requirements went in, one candidate came out, and the
# only trace of the other was a count the caller had to diff by hand. A
# dropped requirement means nobody verifies it at all.

UNCOMPILABLE_SPEC = """1. Invoice branding
   - The PDF letterhead must look professional.

2. Uniqueness
   - Duplicate email inserts must be rejected.
"""


def test_an_uncompilable_requirement_is_reported_not_omitted():
    parsed = parse_requirements(UNCOMPILABLE_SPEC)
    candidates = compile_candidates(parsed.requirements)
    gaps = coverage_gaps(parsed.requirements, candidates)

    compiled_refs = {c.requirement_ref for c in candidates}
    gap_refs = {g.requirement_ref for g in gaps}
    # Every requirement is accounted for exactly once: the partition this
    # feature exists to make visible. Before it, `len(requirements) !=
    # len(candidates)` was the only way to notice a hole.
    assert gap_refs == {r.id for r in parsed.requirements} - compiled_refs
    assert compiled_refs.isdisjoint(gap_refs)


def test_the_gap_names_the_families_that_were_tried():
    parsed = parse_requirements(UNCOMPILABLE_SPEC)
    candidates = compile_candidates(parsed.requirements)
    gap = coverage_gaps(parsed.requirements, candidates)[0]

    assert "The PDF letterhead must look professional." in gap.requirement
    # The suggestion must name what was actually searched, or "add a checker"
    # is indistinguishable from advice to fix the requirement's wording.
    assert gap.considered_families
    assert all(f in gap.suggestion for f in gap.considered_families)


def test_the_suggestion_distinguishes_no_criteria_from_unrecognised_wording():
    """The two causes need opposite fixes, so the advice must differ.

    A requirement with no acceptance criteria has nothing for the patterns to
    look at; one whose criteria use none of the family vocabulary has a real
    invariant stated in uncheckable terms. Telling either author the other
    one's fix sends them the wrong way.

    The zero-criteria arm is a requirement whose body has no ``-`` bullet at
    all: the parser reads every bullet as an AcceptanceCriterion, so
    ``- Search results must feel snappy.`` yields AC-01-1 (kind=behavioral)
    and is a *wording* gap, not a *missing criteria* gap. An earlier draft of
    this test used that bullet for the no-criteria arm and both sides produced
    the identical suggestion.
    """
    no_criteria = parse_requirements("1. Feel\n").requirements
    uncheckable_criteria = parse_requirements(
        "1. Branding\n   - The letterhead must look professional.\n"
    ).requirements

    assert not no_criteria[0].acceptance_criteria
    assert uncheckable_criteria[0].acceptance_criteria, (
        "the wording arm needs real criteria, or it is the other arm"
    )

    with_none = coverage_gaps(no_criteria, [])[0]
    with_some = coverage_gaps(uncheckable_criteria, [])[0]

    assert with_none.suggestion != with_some.suggestion
    assert "没有验收标准" in with_none.suggestion
    assert "改述" in with_some.suggestion


def test_a_requirement_dropped_by_dedupe_still_counts_as_a_gap():
    """Gaps are measured against the list the caller will actually use.

    coverage_gaps() takes the compiled list rather than re-deriving it, so a
    requirement whose only candidate was merged away is reported — otherwise
    the registry would hold one candidate standing for two requirements, and
    the second would silently lose its only verification.
    """
    parsed = parse_requirements(SPEC)
    candidates = compile_candidates(parsed.requirements)
    assert not coverage_gaps(parsed.requirements, candidates)

    keep = [c for c in candidates if c.checker_type == "http"]
    gaps = coverage_gaps(parsed.requirements, keep)
    assert gaps, "the requirement whose candidate was dropped must surface"
    assert all(g.requirement_ref not in {c.requirement_ref for c in keep}
               for g in gaps)


# ── §2.5 CLI surface ────────────────────────────────────────────────────
# The tests above call coverage_gaps() directly, which is exactly why #232
# could land wrong: the behaviour that changed is the *exit code* of
# `specproof contract propose`, and nothing here drives the command. A spec
# where nothing compiles used to print "No contract candidates extracted" and
# exit 0 — a caller reading the status line got "success, zero contracts",
# which is the one reading that makes the gaps invisible.

from click.testing import CliRunner  # noqa: E402

from cli.specproof.commands.contract import propose  # noqa: E402

#: No checker-family wording anywhere: every requirement is a gap, so the
#: candidate list is empty and the early return is the whole output.
NOTHING_COMPILES = "1. Feel\n   - It should feel right.\n\n2. Vibe\n   - Keep it clean.\n"

#: One compilable requirement and one that does not, so both branches print.
MIXED = SPEC + "\n3. Feel\n   - It should feel right.\n"


def _propose(spec_text: str):
    runner = CliRunner()
    with runner.isolated_filesystem():
        pathlib.Path("spec.md").write_text(spec_text, encoding="utf-8")
        return runner.invoke(
            propose, ["--repo", ".", "--spec", "spec.md"], catch_exceptions=False
        )


def test_a_spec_where_nothing_compiles_exits_nonzero() -> None:
    """Zero candidates is a real result, not a success.

    Returning before ContractRegistry() is what makes this testable without a
    database — the exit happens on the gap branch, which is also the point:
    the refusal must not depend on storage being reachable.
    """
    result = _propose(NOTHING_COMPILES)
    assert result.exit_code == 1, (
        f"exit {result.exit_code}: 'nothing compilable' must not read as "
        f"success\n{result.output}"
    )
    assert "[UNCOVERED]" in result.output, (
        "the gaps are the entire output of this case, so a run that omits "
        "them tells the caller nothing at all"
    )
    assert "FEEL" in result.output, "the gap must name the requirement"


@requires_mysql
def test_the_gap_branch_names_the_two_different_fixes() -> None:
    """§2.5's two suggestions are different edits, not one boilerplate line.

    'No acceptance criteria' means add an observable criterion; 'no checker
    family wording' means reword or add a family. Collapsing them to one
    message sends the reader to the wrong fix half the time.
    """
    result = _propose(MIXED)
    assert result.exit_code == 1
    out = result.output
    assert "[PROPOSED]" in out, "the compilable half must still be proposed"
    assert "[UNCOVERED]" in out, "the uncompilable half must be reported"
    assert "REQ-1" in out and "REQ-3" in out
    # One gap, naming the family vocabulary it looked for.
    assert "http" in out or "sql" in out, (
        "a gap caused by unrecognised wording must say which families were "
        "tried, or the reader cannot tell it from a missing criterion"
    )


@requires_mysql
def test_full_coverage_exits_zero() -> None:
    """The other half of the contract: the exit code must not become a blanket 1.

    Without this, a gate that simply returned 1 always would pass the two
    tests above — and every healthy spec would look broken.
    """
    result = _propose(SPEC)
    assert result.exit_code == 0, (
        f"exit {result.exit_code} on a fully compilable spec\n{result.output}"
    )
    assert "[UNCOVERED]" not in result.output
    assert "[PROPOSED]" in result.output

