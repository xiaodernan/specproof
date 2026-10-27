"""#499 — a CI job must be able to RUN the repository's own gates.

WHY THIS EXISTS.  The repository's gates are its audit trail: the ledger
fence (``test_recorded_ledger_sections_do_not_vanish.py``), the evidence gate
(``test_ledger_evidence_claims_are_true.py``), the MySQL isolation contract
(``tests/conftest.py``).  On 2026-10-27, CI run 40574430562 showed 21 reds
in ``tests-no-infra`` and two jobs that died before running a single test —
and not one of the 21 was a defect in the product.  Every one of them was a
JOB failing to carry what a gate reads:

  * the ledger fence compares HEAD against every reachable revision of the
    ledger and REFUSES to judge when fewer than ``MIN_REVS`` are reachable.
    ``actions/checkout`` defaults to depth 1 — one revision — so all seven of
    its legs went red with ``UnreadableLedgerError: only 1 revisions ...
    are reachable``.  The job has to check out the history the gate reads;
  * the evidence gate read "does this file exist" off the DISK of whoever
    ran it, so a git-ignored eval artifact was true on the developer and
    false on CI.  That gate now judges the repository (see
    ``test_ledger_evidence_claims_are_true.py``);
  * two ``contract propose`` cases reach MySQL through ``ContractRegistry()``
    and FAILED in the no-infra job, where there is no database to reach.  A
    case that cannot run must SKIP, and the job that HAS the database must
    run it for real;
  * two whole jobs died before their tests: a ``#`` comment placed INSIDE a
    backslash continuation swallowed the rest of the logical command —
    including the docker image — so ``docker run`` was called with no image
    ("docker: 'docker run' requires at least 1 argument").

A gate that cannot run is not a gate.  These legs are about the JOBS, and
each of them is paired with the measurement that explains WHY the job has to
carry what it carries.

THE RULERS, each one sentence:

  G1  the job that runs the unit suite checks out the full history, because
      the ledger fence needs ``MIN_REVS`` revisions of ONE file and no
      finite depth promises that;
  G2  the contract CLI cases SKIP — with a reason naming the isolation
      verdict — when this session has no reachable database;
  G3  the job that has the database creates the isolated schema the
      isolation contract demands, and does it BEFORE it runs anything;
  G4  the job that has the database runs the cases the no-infra job skips;
  G5  no ``run:`` block may put a comment inside a backslash continuation.

WHAT IS DELIBERATELY OUT OF SCOPE.  This file does not judge what the jobs
RUN — that is the suite's business, and 11 of the 21 reds belong to other
lanes' work.  It judges whether the job could run the repository's gates at
all.  It also does not re-decide the ledger's content: the fence owns that,
and this file reads the fence's own floor rather than typing its own.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import tests.conftest as _isolation

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_REL = ".github/workflows/ci.yml"

#: The job that runs the unit suite — the one the ledger fence rides in.
UNIT_JOB = "tests-no-infra"
#: The job that has the databases.
WITH_INFRA_JOB = "tests-with-infra"

#: The file whose cases need a live database.
CONTRACT_TESTS = "tests/unit/test_contract_compiler.py"
#: The two cases in it that reach MySQL through ``ContractRegistry()``.
MYSQL_CASES = (
    "test_the_gap_branch_names_the_two_different_fixes",
    "test_full_coverage_exits_zero",
)


# ---------------------------------------------------------------------------
# the workflow
# ---------------------------------------------------------------------------


def workflow() -> dict:
    """The parsed workflow. Read from disk, never retyped."""
    return yaml.safe_load((ROOT / WORKFLOW_REL).read_text(encoding="utf-8"))


def steps_of(job_id: str) -> list[dict]:
    jobs = workflow()["jobs"]
    assert job_id in jobs, f"the workflow has no job {job_id!r}: {sorted(jobs)}"
    return list(jobs[job_id].get("steps", []))


def run_scripts(job_id: str) -> list[str]:
    return [str(step["run"]) for step in steps_of(job_id) if "run" in step]


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ("git", "-C", str(cwd), *args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, (
        f"git {' '.join(args)} in {cwd} -> rc={proc.returncode} {proc.stderr[:300]!r}"
    )
    return proc.stdout


def _fence_min_revs() -> int:
    """The ledger fence's own floor — read from the fence, never retyped here.

    A copy of the number would drift from the gate that needs it, and the
    drift would read as "the job satisfies the fence" when it does not.
    """
    from tests.unit.test_recorded_ledger_sections_do_not_vanish import MIN_REVS

    return MIN_REVS


# ---------------------------------------------------------------------------
# G1  the unit-suite job must carry the history the ledger fence reads
# ---------------------------------------------------------------------------


def test_the_unit_suite_job_checks_out_the_history_the_ledger_fence_reads() -> None:
    """``fetch-depth: 0`` — the whole history, because no finite depth does.

    The fence needs ``MIN_REVS`` revisions of ONE file.  A depth-N checkout
    carries N revisions of the REPOSITORY, not N revisions of that file, so
    every finite depth is a promise the checkout cannot keep; only the whole
    history keeps it.

    Measured: CI run 40574430562, seven legs red in
    ``test_recorded_ledger_sections_do_not_vanish.py``, every one of them
    ``UnreadableLedgerError: only 1 revisions of
    docs/operations/DEEP_OPTIMIZATION_PLAN.md are reachable``.
    """
    checkouts = [
        step
        for step in steps_of(UNIT_JOB)
        if str(step.get("uses", "")).startswith("actions/checkout")
    ]
    assert checkouts, f"{UNIT_JOB} has no checkout step"
    for step in checkouts:
        depth = step.get("with", {}).get("fetch-depth")
        assert depth == 0, (
            f"{UNIT_JOB} checks out with fetch-depth={depth!r}; the ledger fence "
            f"needs {_fence_min_revs()} revisions of one file, and a depth-N "
            "checkout carries N revisions of the repository, not of that file"
        )


def test_the_ledger_history_at_head_satisfies_the_fence() -> None:
    """The demand the job now meets is satisfiable — it is not a demand for
    the impossible.

    If the ledger had fewer revisions than the fence's floor, then no
    checkout depth would satisfy it and this gate would be asking for
    something that cannot exist.
    """
    floor = _fence_min_revs()
    revs = _git(
        ROOT, "log", "--format=%H", "--", "docs/operations/DEEP_OPTIMIZATION_PLAN.md"
    ).split()
    assert len(revs) >= floor, (
        f"the ledger has only {len(revs)} reachable revisions; the fence needs "
        f"{floor}, so no checkout could satisfy it"
    )


def test_a_depth_one_checkout_carries_exactly_one_revision(tmp_path: Path) -> None:
    """The mechanism behind G1, measured instead of assumed.

    ``actions/checkout`` without ``fetch-depth`` is a depth-1 clone, and a
    depth-1 clone carries one revision.  The fence needs more than one, so
    the default checkout cannot satisfy it — whatever the repository's own
    history looks like.
    """
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    # The machine's global hooks are not this witness's business, and a hook
    # that failed would fail the witness for the wrong reason.
    hooks = tmp_path / "no-hooks"
    hooks.mkdir()
    for index in range(3):
        (source / f"f{index}.txt").write_text(str(index), encoding="utf-8")
        _git(source, "-c", f"core.hooksPath={hooks}", "add", "-A")
        _git(
            source,
            "-c",
            f"core.hooksPath={hooks}",
            "-c",
            "user.name=witness",
            "-c",
            "user.email=witness@example.invalid",
            "commit",
            "-qm",
            f"c{index}",
        )
    assert len(_git(source, "log", "--format=%H").split()) == 3

    clone = tmp_path / "clone"
    # --no-local: the local transport ignores --depth, so a plain
    # `git clone --depth 1 <path>` would silently clone everything and this
    # witness would prove nothing.
    _git(tmp_path, "clone", "-q", "--depth", "1", "--no-local", str(source), str(clone))
    assert len(_git(clone, "log", "--format=%H").split()) == 1
    assert _fence_min_revs() > 1


# ---------------------------------------------------------------------------
# G2  a case that cannot run must skip
# ---------------------------------------------------------------------------


def _no_database_env() -> dict[str, str]:
    """An environment in which no MySQL answers.

    Port 1 is refused instantly on every platform, so the child session
    learns "no database" without waiting for a timeout.
    """
    env = dict(os.environ)
    env["MYSQL_HOST"] = "127.0.0.1"
    env["MYSQL_PORT"] = "1"
    env.pop("MYSQL_DATABASE", None)
    env.pop("SPECPROOF_TEST_MYSQL_DATABASE", None)
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


#: This leg spawns a child pytest, so it is tagged ``slow`` like every other
#: spawn-child module in this repo (#135's lesson: the fast inner loop must not
#: pay for a child process).  CI does NOT deselect ``slow``, so the merge gate
#: still runs it.  Measured on the development machine: 16-24s of child wall
#: clock, of which pytest itself reports 2s — the rest is interpreter start-up
#: and plugin autoload, which a Linux CI runner does not pay.
@pytest.mark.slow
def test_the_contract_cli_cases_skip_rather_than_fail_without_a_database() -> None:
    """A case that cannot run must not report a broken product.

    Measured: CI run 40574430562, ``tests-no-infra`` — exactly two reds from
    this file, both ``pymysql.err.OperationalError: (2003, "Can't connect to
    MySQL server on 'localhost' ([Errno 111] Connection refused)")``.  The
    product was fine; the job had no database.

    The skip has to NAME why, or a case skipped for another reason would
    pass for this one.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", CONTRACT_TESTS, "-v", "-p", "no:cacheprovider"],
        cwd=ROOT,
        env=_no_database_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    out = proc.stdout
    assert proc.returncode == 0, (
        f"the contract cases must not fail without a database "
        f"(rc={proc.returncode})\n{out[-4000:]}\n{proc.stderr[-2000:]}"
    )
    # pytest wraps a long skip reason across several physical lines, so the
    # case's own segment is flattened before it is read: a verdict that
    # happened to be split over a line break must not read as a missing one.
    flat = " ".join(out.split())
    for case in MYSQL_CASES:
        start = flat.find(case)
        assert start != -1, f"{case} did not report at all:\n{out}"
        rest = flat[start + len(case) :]
        end = rest.find("tests/unit/test_contract_compiler.py::")
        segment = rest[:end] if end != -1 else rest
        assert "SKIPPED" in segment, f"{case} did not skip:\n{segment}"
        assert "isolation verdict" in segment, (
            "the skip must name the isolation verdict, or a case skipped for "
            f"another reason passes for this one:\n{segment}"
        )


# ---------------------------------------------------------------------------
# G3/G4  the job that has the database must be able to use it
# ---------------------------------------------------------------------------


def test_the_job_with_the_database_creates_the_isolated_schema_before_it_runs() -> None:
    """The isolation contract (#75) refuses to let a session write the product
    schema, and it only redirects when the ISOLATED schema answers.

    ``compose.phase0.yml`` creates one schema — the product one — so on CI's
    runner the session would exit 4 ("blocked") before a single test ran, and
    the message pointed at a Windows-only ``.ps1``.

    The schema name is the conftest's OWN default, imported here: a literal
    in the workflow beside a literal in the conftest would drift, and the
    drift would only ever show up as a CI job that exits 4.
    """
    steps = steps_of(WITH_INFRA_JOB)
    create = next(
        (
            index
            for index, step in enumerate(steps)
            if "CREATE DATABASE" in str(step.get("run", ""))
        ),
        None,
    )
    assert create is not None, (
        f"{WITH_INFRA_JOB} never creates a schema; the isolation contract will "
        "exit 4 before a single test runs"
    )
    script = str(steps[create]["run"])
    assert _isolation.DEFAULT_TEST_MYSQL_DATABASE in script, (
        f"{WITH_INFRA_JOB} creates a schema that is not the conftest's own "
        f"default ({_isolation.DEFAULT_TEST_MYSQL_DATABASE!r})"
    )
    pytest_step = next(
        (
            index
            for index, step in enumerate(steps)
            if "pytest" in str(step.get("run", ""))
        ),
        None,
    )
    assert pytest_step is not None, f"{WITH_INFRA_JOB} never runs pytest"
    assert create < pytest_step, (
        "the schema must exist before the session starts: the isolation "
        "contract decides in pytest_configure, before the first test runs"
    )


def test_the_job_with_the_database_runs_the_cases_the_other_job_skips() -> None:
    """The skip must not be the only place those two paths are ever exercised.

    A skip that is never accompanied by a run is a coverage hole wearing a
    green checkmark.
    """
    scripts = "\n".join(run_scripts(WITH_INFRA_JOB))
    assert CONTRACT_TESTS in scripts, (
        f"{WITH_INFRA_JOB} does not run {CONTRACT_TESTS}; the two cases that "
        "skip without a database would then never run anywhere"
    )


# ---------------------------------------------------------------------------
# G5  a comment inside a backslash continuation eats the command
# ---------------------------------------------------------------------------


def _comment_starts_a_comment(line: str) -> bool:
    """Whether the line carries a ``#`` the shell reads as a comment.

    ``#`` starts a comment only at the start of a word and only outside
    quotes; ``foo#bar`` and ``echo "a # b"`` are not comments.
    """
    quote = ""
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "'\"":
            quote = char
            continue
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            return True
    return False


def swallowed_lines(script: str) -> list[tuple[int, str]]:
    """The lines whose content a comment swallows.

    A backslash continuation is removed BEFORE the line is parsed, so a
    comment on a continued line runs to the end of the whole logical
    command — and everything the later physical lines contribute is lost.
    The shape that loses it is a comment followed by more command.
    """
    out: list[tuple[int, str]] = []
    group: list[tuple[int, str]] = []
    for lineno, line in enumerate(script.splitlines(), start=1):
        group.append((lineno, line))
        if not line.rstrip().endswith("\\"):
            _swallowed_by(group, out)
            group = []
    if group:
        _swallowed_by(group, out)
    return out


def _swallowed_by(group: list[tuple[int, str]], out: list[tuple[int, str]]) -> None:
    if len(group) < 2:
        return
    first_comment = next(
        (lineno for lineno, line in group if _comment_starts_a_comment(line)), None
    )
    if first_comment is None:
        return
    for lineno, line in group:
        if lineno <= first_comment:
            continue
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append((lineno, stripped))


def test_no_run_block_puts_a_comment_inside_a_backslash_continuation() -> None:
    """No job may carry the shape that killed two of them.

    Measured: CI run 40574430562 logged ``docker: 'docker run' requires at
    least 1 argument`` in ``tests-with-infra`` and in ``eval-golden-cases``,
    and neither job ran a single test.
    """
    bad: list[str] = []
    for job_id in workflow()["jobs"]:
        for script in run_scripts(job_id):
            for lineno, text in swallowed_lines(script):
                bad.append(f"{job_id} line {lineno}: {text}")
    assert not bad, (
        "these lines are swallowed by a comment inside a backslash "
        "continuation:\n  " + "\n  ".join(bad)
    )


def test_a_comment_inside_a_continuation_swallows_the_rest_of_the_command() -> None:
    """The mechanism behind G5, measured by the shell itself.

    A backslash continuation is removed before the line is parsed, so the
    ``#`` on a continued line starts a comment that runs to the end of the
    logical command: the image that followed it was never passed to ``docker
    run``, and the shell then tried to execute the image line as a command of
    its own.  That is the whole of CI's ``docker: 'docker run' requires at
    least 1 argument``.
    """
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on this machine; the shell is what has to be asked")
    prelude = 'docker() { printf "%s\\n" "$@"; }\n'
    broken = (
        prelude
        + "docker run --rm --user 1000:1000 \\\n"
        + "  -e A=1 \\\n"
        + "  # a note inside the continuation \\\n"
        + "  alpine echo hi\n"
    )
    fixed = (
        prelude
        + "docker run --rm --user 1000:1000 \\\n"
        + "  -e A=1 \\\n"
        + "  alpine echo hi\n"
    )

    def run(script: str) -> tuple[int, list[str]]:
        proc = subprocess.run(
            [bash, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc.returncode, proc.stdout.split()

    lost_code, lost = run(broken)
    assert "alpine" not in lost, (
        f"the comment did not swallow the image after all: {lost}"
    )
    assert lost_code != 0, (
        "the broken shape must fail: the image line became a command of its own"
    )
    kept_code, kept = run(fixed)
    assert "alpine" in kept, f"the comment-free shape lost the image too: {kept}"
    assert kept_code == 0, f"the comment-free shape failed: {kept}"
