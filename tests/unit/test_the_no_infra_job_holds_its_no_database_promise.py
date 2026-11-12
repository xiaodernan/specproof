"""#600 — the job that promises no database must not be run by a case that needs one.

WHAT HAPPENED. ``test_the_aggregate_plane_answers_the_demo_question.py`` (#542)
shipped with one leg that writes three job rows into a live MySQL and reads the
dashboard back. Every other leg in that file folds SQL text or captures the
connection, so the file answered offline — except that one, which in CI's
``tests-no-infra`` job raised ``pymysql.err.OperationalError``. Nothing was wrong
with the product: that job has no database, and having no database is its whole
promise.

#499 repaired exactly this shape once, for two ``contract propose`` cases, and
every ruler it wrote names that one file. Nothing in the repository noticed a
SECOND file growing the same shape, because the population was a remembered list
and a remembered list only carries what whoever typed it last knew. Measured on
the clean tree before this fix — the #120 census cut by the paths
``tests-no-infra`` collects, run against a port that refuses every connection —
exactly one leg failed, and it was the #542 one.

THE RULERS, each one sentence:

  P1  the population is the #120 census cut by the no-infra job's OWN path list,
      derived here rather than remembered, and the file doing the judging is
      demonstrably not inside it;
  P2  a live-database leg really is red in the environment this gate's children
      run in, measured on a planted case rather than argued;
  P3  no case in the population fails when no database answers;
  P4  the leg this unit guarded skips, and its reason names the isolation verdict;
  P5  the verdict-to-skip decision has one owner, so a third file states the
      same reason instead of writing the predicate again;
  P6  every case that skips because no database answers either runs in the job
      that has one, or is on a disclosed list of files that run nowhere;
  P7  this gate knows what the census cannot see, and says so.

P6 is #499's G4 rule — "a skip that is never accompanied by a run is a coverage
hole wearing a green checkmark" — applied to a derived population instead of to
one remembered file. Applying it originally found four files that had been
skipping in CI all along and running in no job at all; they were given a database
home in tests-with-infra on 2026-11-08 (the #1531-era CI consolidation), the roster
below was emptied rather than worked around, and the gate derives the list again
— any file newly joining the list reds it, because the hole would be new.

WHAT IS DELIBERATELY OUT OF SCOPE. This gate does not judge whether the guarded
leg PASSES — that belongs to the job with the database, and the leg is written to
be measured there. It also does not re-judge the contract CLI cases, which reach
MySQL through ``ContractRegistry()`` and so never appear in the census (P7); those
two cases are #499's G2 and G4.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from itertools import takewhile
from pathlib import Path

import pytest
import yaml

import tests.conftest as _contract
from tests._mysql_gate import dead_database_env

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_REL = ".github/workflows/ci.yml"
NO_INFRA_JOB = "tests-no-infra"
WITH_INFRA_JOB = "tests-with-infra"

AGGREGATE_TESTS = "tests/unit/test_the_aggregate_plane_answers_the_demo_question.py"
SEEDED_LEG = (
    f"{AGGREGATE_TESTS}::test_seeded_rows_change_the_real_numbers_only_through_the_marker"
)

#: A child that never returns is a hang, not a red, and a hang inside a merge
#: gate is the worse of the two. The population is bounded, so this is far above
#: what the census run costs and still finite.
CHILD_TIMEOUT_SECONDS = 900

#: How many times a child session is asked before this gate calls its death a
#: fact about the product. See ``_child_run``.
CHILD_ATTEMPTS = 2

#: The files that skip because no database answered and that no job with a
#: database collects. Empty since 2026-11-08: #600 found four
#: (test_agent_jobs_migration_parity, test_audit_action_parity,
#: test_data_dictionary_covers_migrations, test_feedback_store_read) which were
#: given a home in tests-with-infra — the #120 census-derived P6 leg below now
#: derives their absence-or-presence from the workflow rather than a roster.
#: A new file appearing here reds the gate, which is what stops the hole growing
#: back silently.
SKIPS_WITHOUT_A_HOME: dict[str, str] = {}

#: Files that answer "no database here" with their own run-time check instead of
#: the session's isolation verdict. Empty since 2026-11-08: all six former members
#: (test_agent_jobs_migration_parity, test_audit_action_parity,
#: test_data_dictionary_covers_migrations, test_feedback_store_read,
#: test_job_state_machine, test_migrations) were folded onto the shared owner
#: (tests/_mysql_gate.py::requires_mysql) — the skip decision is now taken once,
#: at collection time, from the same verdict every other gate reads. The naming
#: gate below holds the invariant: any file that starts deciding for itself
#: again reds it.
LEGACY_RUN_TIME_SKIPS: frozenset[str] = frozenset()

#: The live leg P2 plants, in a file outside the repository. ``MySQLStore`` is
#: imported under another name on purpose: the #120 census looks for that word
#: followed by a call, and a census that counted the file policing it would move
#: its own population every time this comment was edited (P1 pins that it does
#: not, which is the claim worth having).
#: The planted leg's name, used for the case body, the file name and the verdict
#: below, so the three cannot drift apart and leave the gate asserting on a leg
#: that no longer exists.
PLANTED_LEG = "test_planted_live_database_leg"
PLANTED_CASE = f"""import sys

sys.path.insert(0, {{root!r}})

from storage.mysql import MySQLStore as live_store


def {PLANTED_LEG}():
    live_store().ensure_tables()
"""

#: A test file that lives outside the repository has no node-id file part at all:
#: ``_pytest/nodes.py`` builds it with ``path.relative_to(config.rootpath)``, the
#: ``ValueError`` fallback yields nothing for a foreign path, and the item ends up
#: spelled ``::test_name``. Requiring a character before ``::`` therefore read the
#: planted child as a session that reported no outcomes — which ``_child_ran``
#: calls a death, so a run that genuinely failed was retried and then blamed on
#: the environment. Measured on the development machine with pytest 9.1.1.
_OUTCOME = re.compile(r"^(\S*::\S+?)\s+(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
#: ``-rs`` writes ``SKIPPED [n] <path>:<line>: <reason>`` — the colon after the
#: line number is part of the format, and dropping it makes every read below
#: return an empty dict, which is how a gate that claims "nobody skipped" would
#: be green on a ruler that never looked.
_SKIP_REPORT = re.compile(r"SKIPPED \[\d+\] (\S+?):\d+: (.*?)(?=SKIPPED \[\d+\]|\Z)")


# ---------------------------------------------------------------------------
# the workflow, read rather than retyped
# ---------------------------------------------------------------------------


def _workflow() -> dict:
    return yaml.safe_load((ROOT / WORKFLOW_REL).read_text(encoding="utf-8"))


def _pytest_path_args(job_id: str) -> list[str]:
    """The path arguments one job's own pytest command collects.

    Both jobs write their paths before their flags, so the collect set is
    everything between ``pytest`` and the first option — and every token kept is
    then checked to exist, which is what stops ``-m`` or ``not slow_eval`` from
    being read as a path and a renamed job from reading as an empty one.
    """
    jobs = _workflow()["jobs"]
    assert job_id in jobs, f"the workflow has no job {job_id!r}: {sorted(jobs)}"
    scripts = [
        str(step["run"])
        for step in jobs[job_id].get("steps", [])
        if "pytest" in str(step.get("run", ""))
    ]
    assert len(scripts) == 1, (
        f"{job_id} runs pytest in {len(scripts)} steps; this gate reads one command "
        "and would silently judge only part of the job if there were two"
    )
    tokens = shlex.split(scripts[0])
    after = tokens[tokens.index("pytest") + 1 :]
    paths = list(takewhile(lambda token: not token.startswith("-"), after))
    assert paths, f"{job_id}'s pytest command collects no path at all"
    for path in paths:
        assert (ROOT / path).exists(), (
            f"{job_id} collects {path!r}, which is not in the tree — the token split "
            "read a flag or a quoted marker as a path"
        )
    return paths


def _collected_by(rel: str, paths: list[str]) -> bool:
    return any(rel == path or rel.startswith(path.rstrip("/") + "/") for path in paths)


def census() -> list[str]:
    """The #120 scan: every test file that constructs a store or a config."""
    return sorted(_contract.mysql_backed_test_files())


def population() -> list[str]:
    """The census restricted to what ``tests-no-infra`` actually collects."""
    paths = _pytest_path_args(NO_INFRA_JOB)
    return [name for name in census() if _collected_by(name, paths)]


# ---------------------------------------------------------------------------
# one child session, read by several legs
# ---------------------------------------------------------------------------


class _Report:
    """A child run's report, cut into the two shapes this gate reads.

    Node ids are normalised to forward slashes: a Windows runner prints
    ``tests\\unit\\...`` and a Linux one prints ``tests/unit/...``, while the
    population this gate derives is spelled with forward slashes on both.
    """

    def __init__(self, proc: subprocess.CompletedProcess[str]) -> None:
        self.rc = proc.returncode
        self.out = proc.stdout
        self.flat = " ".join(proc.stdout.split())
        self.attempts = 1
        self.outcomes: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            found = _OUTCOME.match(line.strip())
            if found:
                self.outcomes[found.group(1).replace("\\", "/")] = found.group(2)

    @property
    def failures(self) -> list[str]:
        return sorted(
            node for node, outcome in self.outcomes.items()
            if outcome in ("FAILED", "ERROR")
        )

    def skip_reasons(self) -> dict[str, list[str]]:
        """Each file the child skipped something in, with what it said why."""
        out: dict[str, list[str]] = {}
        for found in _SKIP_REPORT.finditer(self.flat):
            out.setdefault(found.group(1).replace("\\", "/"), []).append(
                " ".join(found.group(2).split())
            )
        return out


def _spawn(files: list[str]) -> _Report:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *files,
            "-o",
            "addopts=",
            "-v",
            "-rs",
            "--tb=line",
            "-p",
            "no:cacheprovider",
        ],
        cwd=ROOT,
        env=dead_database_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=CHILD_TIMEOUT_SECONDS,
        check=False,
    )
    return _Report(proc)


def _child_ran(report: _Report) -> bool:
    """Did the child hold a session at all?

    Exit code 2 is "interrupted during collection", 3 an internal error, 4 a
    usage error, 5 nothing collected — none of which is a verdict about the
    product, and all of which print no per-test outcomes.
    """
    return report.rc in (0, 1) and bool(report.outcomes)


def _child_run(files: list[str]) -> _Report:
    """One child session over ``files``, with no database for it to reach.

    A session that dies before collecting anything is retried once. Measured on
    the development machine: a Chrome installer's swept ``%TEMP%`` directory
    made the planted child exit 2 with zero outcomes, while the same case failed
    with ``OperationalError`` on every quiet re-run — #126's rule, a red about
    the runner is not a red about the product. A death that repeats is returned
    as it came, and the legs' own messages name it as a death.
    """
    report = _spawn(files)
    for attempt in range(2, CHILD_ATTEMPTS + 1):
        if _child_ran(report):
            break
        report = _spawn(files)
        report.attempts = attempt
    return report


@pytest.fixture(scope="module")
def no_database_report() -> _Report:
    """The population, once, in a session with no database to reach.

    Module-scoped because every leg that reads it wants the same child, and the
    census is the expensive half of this file.
    """
    return _child_run(population())


# ---------------------------------------------------------------------------
# P1  the population is derived
# ---------------------------------------------------------------------------


def test_the_population_is_the_census_cut_by_the_job_s_own_path_list() -> None:
    """Both halves have to be seen cutting, or the intersection is a fiction.

    A census that found nothing, a path list that collected nothing, and a
    population that was the whole census all look the same in a green run.
    """
    found = census()
    inside = population()
    here = Path(__file__).resolve().relative_to(ROOT).as_posix()
    assert found, (
        "the #120 census returned no MySQL-backed test file — the scan is blind, "
        "and a gate whose population is empty passes without judging anything"
    )
    assert inside, "no census file is collected by tests-no-infra: nothing to police"
    assert set(inside) <= set(found), "the population is not a subset of the census"
    outside = [name for name in found if name not in set(inside)]
    assert outside, (
        "every census file is collected by the no-database job — the path filter "
        f"stopped cutting: {found}"
    )
    assert AGGREGATE_TESTS in inside, (
        f"{AGGREGATE_TESTS} is outside the population, so the leg that made this "
        "job red is not the leg this gate is judging"
    )
    assert here not in found, (
        f"{here} joined the census it polices: the population would move whenever "
        "this file is edited, and a census that counts its own counter is not a census"
    )


def test_the_job_being_modelled_really_runs_without_infrastructure() -> None:
    """The children here refuse a port, which models ``tests-no-infra`` only
    while that job brings no infrastructure of its own.

    A ``docker compose up`` added to this job would make every verdict below
    describe a session the merge gate never runs, and the gate would still be
    green. The workflow is read, not remembered: the same parse that builds the
    population is what says this job has no service step.
    """
    steps = _workflow()["jobs"][NO_INFRA_JOB]["steps"]
    armed = [
        str(step.get("run", "") or step.get("uses", ""))
        for step in steps
        if "docker" in str(step.get("run", "")) + str(step.get("uses", ""))
        or "compose" in str(step.get("run", "")) + str(step.get("uses", ""))
    ]
    assert not armed, (
        f"{NO_INFRA_JOB} now brings infrastructure ({armed}): a child run with a "
        "refused port no longer models the job this gate polices"
    )
    infra = _pytest_path_args(WITH_INFRA_JOB)
    assert any(path.startswith("tests/integration") for path in infra), (
        f"{WITH_INFRA_JOB} no longer collects the integration paths ({infra}): "
        "P6 reads it as the job that has a database, and that claim needs checking"
    )


# ---------------------------------------------------------------------------
# P2  the environment really is a no-database environment
# ---------------------------------------------------------------------------


def test_a_live_database_leg_is_red_when_no_database_answers() -> None:
    """A planted live leg fails in exactly the environment P3 judges with.

    Without this, P3's green would be indistinguishable from a child that never
    reached the database at all — a ruler that cannot fail is not a ruler, and
    #499's G2 has the same shape for the same reason.

    THE PLANTED CASE LIVES IN THE REPO'S OWN ``.scratch/``, not in the
    machine's shared ``%TEMP%``. Measured on the development machine (#1636):
    a case planted under ``%TEMP%`` made the child die BEFORE it judged
    anything — the collection walked the shared temp root and tripped over a
    file that was swept away while it walked (``FileNotFoundError`` on
    ``%TEMP%\\marketplace-mutation-source-….lock``), so the session ended
    with exit code 2 and no outcome. The child was told "the runner died"
    twice and the gate blamed the runner — correctly, and for the wrong
    reason: the case had been planted in the busiest directory on the
    machine. A quiet directory the sweep does not touch is the honest place
    for a case whose whole job is to be collected.
    """
    planted_dir = ROOT / ".scratch" / f"no-infra-planted-{os.getpid()}"
    planted_dir.mkdir(parents=True, exist_ok=True)
    try:
        planted = planted_dir / f"{PLANTED_LEG}.py"
        planted.write_text(PLANTED_CASE.format(root=str(ROOT)), encoding="utf-8")
        report = _child_run([str(planted)])
    finally:
        shutil.rmtree(planted_dir, ignore_errors=True)
    assert report.rc != 0, (
        "the planted live-database leg PASSED with no database configured, so the "
        "environment this gate hands its children is not a no-database environment "
        f"and P3's verdict means nothing\n{report.out[-1500:]}"
    )
    assert report.failures, (
        f"the child exited {report.rc} without reporting a failed leg — it died "
        f"before running the planted case ({report.attempts} attempt"
        f"{'s' if report.attempts > 1 else ''} of {CHILD_ATTEMPTS})\n{report.out[-1500:]}"
    )
    assert all(node.endswith(PLANTED_LEG) for node in report.failures), (
        f"the child's failed legs were {report.failures}, which is not the planted "
        "case — the run judged something else, so its red says nothing about this "
        f"gate's environment\n{report.out[-1500:]}"
    )
    # The child collects one item, so more outcomes than this means the parse is
    # reading the report's prose rather than its per-test lines.
    assert len(report.outcomes) == 1, (
        f"the planted run reported {report.outcomes} but collects one case: the "
        "outcome parser is matching lines that are not verdicts, which is how the "
        f"legs below would read a child that never ran\n{report.out[-1500:]}"
    )
    assert "OperationalError" in report.flat, (
        "the planted leg failed for something other than a refused connection, so "
        f"the failure is not about the database\n{report.out[-1500:]}"
    )


def test_the_outcome_parser_reads_both_node_id_spellings() -> None:
    """Both shapes this gate parses are checked offline, on the object the legs use.

    P2's child is the only in-room witness that a file outside the repository is
    read at all, and a twelve-second witness is not one a later edit re-runs by
    reflex. A summary line is fed in too: it carries the same node id after the
    word ``FAILED`` instead of before it, and counting it would double the child's
    verdict.
    """
    report = _Report(
        subprocess.CompletedProcess(
            args=[sys.executable],
            returncode=1,
            stdout=(
                "tests\\unit\\test_x.py::test_real PASSED                        [ 50%]\n"
                f"::{PLANTED_LEG} FAILED                                  [100%]\n"
                f"FAILED tests\\unit\\test_x.py::{PLANTED_LEG} - pymysql.err.OperationalError\n"
                "============================== 1 failed in 11.88s ==============\n"
            ),
            stderr="",
        )
    )
    assert report.outcomes == {
        "tests/unit/test_x.py::test_real": "PASSED",
        f"::{PLANTED_LEG}": "FAILED",
    }, report.outcomes
    assert report.failures == [f"::{PLANTED_LEG}"], report.failures


# ---------------------------------------------------------------------------
# P3  nothing in the population fails
# ---------------------------------------------------------------------------


def test_no_mysql_backed_case_fails_when_the_job_has_no_database(
    no_database_report: _Report,
) -> None:
    """The promise itself: a session with no reachable database is not a red.

    Every file the census names inside this job runs, and none of them may fail.
    Before #600 the #542 leg raised ``OperationalError`` here, and the job's own
    exit code said "the product is broken" when the truth was "there is no
    database on this runner".
    """
    report = no_database_report
    assert not report.failures, (
        f"these legs failed with no database: {report.failures}\n"
        f"{report.out[-3000:]}"
    )
    assert report.rc == 0, (
        f"the population run exited {report.rc} without a named failure — a session "
        f"that aborts is not a session that passed ({report.attempts} attempt(s) of "
        f"{CHILD_ATTEMPTS}; the legs below read whatever the last one printed)\n"
        f"{report.out[-3000:]}"
    )
    seen = {node.split("::")[0] for node in report.outcomes}
    missing = [name for name in population() if name not in seen]
    assert not missing, (
        f"{missing} reported no outcome at all: the child did not run the file this "
        "gate claims to have judged"
    )


# ---------------------------------------------------------------------------
# P4  the guarded leg skips, and says why
# ---------------------------------------------------------------------------


def test_the_leg_that_needs_the_database_skips_and_names_the_verdict(
    no_database_report: _Report,
) -> None:
    """Skip, do not fail — and say the thing that makes the skip checkable.

    The reason has to name the isolation verdict, or a case skipped for any other
    reason would pass for "there is no database here". That is #499's G2 rule, and
    the phrase is now produced by one owner rather than typed per file.
    """
    report = no_database_report
    assert SEEDED_LEG in report.outcomes, (
        f"{SEEDED_LEG} reported no outcome — either it moved out of the file this "
        "gate names, or the population run never collected it"
    )
    assert report.outcomes[SEEDED_LEG] == "SKIPPED", (
        f"the seeded-row leg reported {report.outcomes[SEEDED_LEG]!r} where no "
        "database answers; it needs a live schema and must skip with the verdict"
    )
    reasons = report.skip_reasons().get(AGGREGATE_TESTS, [])
    assert reasons, (
        "the child printed no skip report for the aggregate file, so the reason "
        "above cannot be read: check what -rs reports for a module-level mark"
    )
    for reason in reasons:
        assert "isolation verdict" in reason, (
            f"the skip says {reason!r}: it must name the isolation verdict, or a "
            "different skip passes for the missing database"
        )


# ---------------------------------------------------------------------------
# P5  one owner for the verdict-to-skip decision
# ---------------------------------------------------------------------------


#: The two names a file must hold to be deciding "no database here" for itself.
#: Each is assembled from halves on purpose: written whole, this file would match
#: its own scan and P5 would report two owners because of a comment.
_VERDICT = "MYSQL" + "_ISOLATION"
_SKIP_MARK = ".mark." + "skip"


def _verdict_skip_owners() -> list[str]:
    """Every tests file that reads the isolation verdict and builds a skip mark."""
    return sorted(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.glob("tests/**/*.py")
        if _VERDICT in (text := path.read_text(encoding="utf-8-sig"))
        and _SKIP_MARK in text
    )


def test_the_isolation_verdict_is_turned_into_a_skip_in_one_place() -> None:
    """The mark is written once, so a third file says the same reason.

    #499's two cases and #542's one leg now share ``tests/_mysql_gate.py``. The
    scan keys on the two names a file has to hold to be deciding this — the
    verdict it reads and the mark it builds — so a copy written somewhere else is
    caught by shape, not by a remembered list of files.
    """
    owners = _verdict_skip_owners()
    assert owners == ["tests/_mysql_gate.py"], (
        f"{owners} read the isolation verdict into a skip mark; the owner is "
        "tests/_mysql_gate.py and a second copy of the predicate is how a rename "
        "leaves one file's skips lying about the other's"
    )


def test_the_owner_scan_does_not_count_the_file_running_it() -> None:
    """The needles are split, and only that keeps this scan from finding itself.

    A file whose text contains both names whole is an owner by P5's rule — which
    would make this gate an owner of the very thing it polices, and red the run
    for editing a comment here. The split is the same protection P1 asks of the
    census; this leg is the version of that promise that can fail.
    """
    here = Path(__file__).resolve().read_text(encoding="utf-8-sig")
    for needle in (_VERDICT, _SKIP_MARK):
        assert needle not in here, (
            f"{needle!r} now appears whole in this file, so the owner scan counts "
            "the file running it — the report would name two owners where there is "
            "one, and the second would be this gate's own prose"
        )
    assert _verdict_skip_owners() == ["tests/_mysql_gate.py"], (
        "the halves are split but the scan still finds something other than the "
        "owner: the needle no longer describes what it claims to match"
    )


# ---------------------------------------------------------------------------
# P6  a skip without a run is a coverage hole
# ---------------------------------------------------------------------------


def test_every_case_that_skips_for_a_missing_database_runs_where_one_answers(
    no_database_report: _Report,
) -> None:
    """Nothing may convert this red into a permanent skip.

    The guard P4 adds is only honest because ci.yml runs the leg in the job that
    has a database. The same test applied to the whole population found four
    files whose database legs run in no job at all; they were given one in
    tests-with-infra on 2026-11-08, and the roster it polices is empty until a
    file rejoins it.
    """
    reasons = no_database_report.skip_reasons()
    database_skips = sorted(
        name for name, texts in reasons.items() if any("MySQL" in text for text in texts)
    )
    assert database_skips, (
        "no case skipped because of a missing database: this ruler has nothing to "
        "read, and a run in which nobody skipped is not the same as a run that "
        "proved skipping works"
    )
    assert AGGREGATE_TESTS in database_skips, (
        "the guarded file produced no database-absence skip, so the guard is not "
        "what P3's green is resting on"
    )
    homeless = sorted(
        name for name in database_skips
        if not _collected_by(name, _pytest_path_args(WITH_INFRA_JOB))
    )
    assert homeless == sorted(SKIPS_WITHOUT_A_HOME), (
        f"skips-without-a-database and runs-nowhere = {homeless}; the roster names "
        f"{sorted(SKIPS_WITHOUT_A_HOME)}. A file joining the list is new coverage "
        "lost without anyone deciding it; a file leaving it has to say which way"
    )
    for name in homeless:
        assert name in LEGACY_RUN_TIME_SKIPS, (
            f"{name} runs nowhere and also does not use the verdict — fix the order "
            "of the two debts before adding a third"
        )
        leg = SKIPS_WITHOUT_A_HOME[name].split(" — ", 1)[0]
        outcome = no_database_report.outcomes.get(f"{name}::{leg}")
        assert outcome == "SKIPPED", (
            f"{name} is rostered as coverage nobody ever runs, and the leg that "
            f"proves it is {leg!r} — but this session reported it {outcome!r}. The "
            "roster's sentence is stale: either the leg moved or it stopped "
            "skipping, and the hole it describes needs re-measuring"
        )
    assert AGGREGATE_TESTS not in SKIPS_WITHOUT_A_HOME, (
        "the leg this unit guarded must not be listed as coverage nobody ever runs"
    )


def test_the_files_that_decide_for_themselves_instead_of_the_verdict_are_counted(
    no_database_report: _Report,
) -> None:
    """The run-time skips this roster held were all folded onto the shared owner.

    Bidirectional on purpose: any new file deciding "no database" in its own
    words reds here, which is the only way the list cannot quietly become the
    way things are done.
    """
    reasons = no_database_report.skip_reasons()
    verdict_named = {
        name for name, texts in reasons.items()
        if any("isolation verdict" in text for text in texts)
    }
    legacy = {
        name for name in reasons
        if any("MySQL" in text for text in reasons[name])
    } - verdict_named
    assert legacy == LEGACY_RUN_TIME_SKIPS, (
        f"files skipping on their own run-time check: {sorted(legacy)}; rostered: "
        f"{sorted(LEGACY_RUN_TIME_SKIPS)}"
    )


# ---------------------------------------------------------------------------
# P7  what the census cannot see
# ---------------------------------------------------------------------------


def test_the_census_is_how_this_gate_chooses_its_population_and_says_what_it_misses() -> None:
    """``ContractRegistry()`` reaches MySQL without naming it in a construct call.

    The #120 scan finds files that build a store or a config, so the contract
    CLI cases — the reason #499 exists — are invisible to it. That is only safe
    while a different gate reads them; this leg fails if either half changes, so
    the blind spot is stated rather than relied on.
    """
    contract_tests = "tests/unit/test_contract_compiler.py"
    assert contract_tests not in census(), (
        f"{contract_tests} is now in the census, so the #120 scan learned to see "
        "indirect reach — this gate's population grew and P7's split is stale"
    )
    assert _collected_by(contract_tests, _pytest_path_args(WITH_INFRA_JOB)), (
        f"{contract_tests} left the job that has a database; its two cases then "
        "skip everywhere and #499's G4 rule is broken by a file this gate cannot see"
    )
