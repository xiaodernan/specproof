"""WHAT IS CLAIMED -- provider-smoke's manual CI leg, and the four names it must
not be typed from memory.

Three of the orphan branches' five jobs in ``a756f5338:.github/workflows/quality.yml``
had no master counterpart by name; ``provider-smoke`` was the only one of them that
ran something rather than renamed something, and it is the only leg in this
repository that talks to a real model gateway. #1548 registered it as a gap
(``REGISTERED_GAPS["provider-smoke"]``) and #1549 carries the job over.

Measured while building this gate, in a disposable worktree at ``3f493ea``:

* The 16 test modules that mention ``ci.yml`` (168 items) are **green with a 9th
  job added, with the trigger added, and with both** -- 0 red in every shape. So
  "what polices the job roster" is: #1548's P8 leg and nothing else. Everything
  else reads the content of job ids it already knows. The trigger arm did print
  one red, and it is not a measurement of anything here: a sibling gate's child
  process died during collection because another lane's maven cleaned the shared
  ``Temp`` directory holding its ``surefire`` scratch, and the same module run
  alone reads 11 passed. That collision is registered as its own defect class,
  not smoothed into this table as a green arm.
* The landing was written from memory first, and the memory was wrong: the job
  body carried ``SPECPROOF_LLM_API_KEY`` and friends. ``providers/config.py``'s
  ``_ENV_FIELDS`` declares ``LLM_BASE_URL / LLM_API_KEY / LLM_MODEL /
  LLM_REASONING_EFFORT / LLM_PROTOCOL``, and at ``3f493ea`` the token
  ``SPECPROOF_LLM`` appeared **0 times** in the whole tree (it now appears in this
  file and in ci.yml's comment, which is the same self-witness shape #1548 had to
  exclude -- harmless here only because no ruler greps for that token) -- so that
  job would have run, read nothing, reported
  ``source="unconfigured"`` with 0 capabilities, exited 1, and every existing gate
  stayed green. The branch's own job had the three names right. This is what
  convergence buys, and it is a measurement rather than an argument.

The ten legs, each one a shape that would otherwise be silent:

  C1 the leg exists and runs the script (a job named provider-smoke that runs
     something else is the gap wearing a successor's name). Two halves: the
     argument after the interpreter must be exactly the script -- no flag, no
     pipeline -- and the thing *before* the interpreter must be a prefix some
     other ci.yml job also uses, because that prefix is how the job finds a
     Python that exists on this runner.
  C2 dispatch self-consistency - ``if: github.event_name == 'workflow_dispatch'``
     and ``workflow_dispatch`` in ``on:`` have to move together, and push /
     pull_request have to survive. A dispatch-gated job in a workflow that cannot
     be dispatched is coverage that never runs; a dispatch trigger with a job that
     ignores it runs on every push against an environment it will not be given.
  C3 every ``env:`` key the leg sets is a name the reader declares - read from
     ``providers/config.py``, never typed here. This is the leg that would have
     reddened the landing I nearly shipped.
  C4 every ``${{ secrets.X }}`` the leg consumes names a declared knob too - an
     environment secret called something the code never reads can never be
     honoured, and the failure looks like an unconfigured stack.
  C5 the leg declares an ``environment:``. Repository-level secrets are not what
     this job reads; without the declaration the three keys arrive empty.
  C6 the register earns its number: the quality.yml reason's leading integer is
     re-derived (branch job ids - master job ids - ``RENAMED_JOBS``), and
     ``provider-smoke`` is gone from ``REGISTERED_GAPS``.
  C7 no ``run:`` command in any workflow interpolates a secret - secret material
     belongs in ``env:`` where the child process, not the command line, holds it.
     Measured baseline: 0 occurrences, in 0 files, before and after the landing.
  C8 the leg is the branch's job, not a re-implementation of it: the step kinds
     are compared as a multiset against ``a756f5338``'s own job, after the two
     runner swaps this file declares and can observe (``setup-python`` ->
     ``uv venv``). A declared swap whose master side is absent is a dropped
     guarantee, so C8 checks the substitution is present before it excuses it.
  C9 the ruler proves it read something - ci.yml parses, the job roster has a
     floor, the declared-name map has a floor. An empty denominator makes every
     claim above vacuously true, which is the failure mode #1548 wrote down twice.
  C10 the job creates the interpreter before it installs into it. This leg did not
     exist when the job landed, and the job's first real run (``44912703445``,
     2026-11-21) died exactly there: ``uv pip install --python
     .venv/Scripts/python.exe`` with no ``.venv``. C1-C9 were green the whole time.
     The branch never showed it because ubuntu + setup-python made the path real.

WHAT THIS GATE DOES NOT SAY. It does not run the leg: that needs a real gateway
credential held by a GitHub environment, and nothing here has or prints one. It
does not prove the leg would PASS - only that the job says what it runs, reads
names that exist, and can actually be triggered. It also did not catch the job
being BROKEN: #2029 moved every ci.yml python call behind ``uv run`` and dropped
``setup-python`` for a venv this job never created, and this file sat red on
C1/C8 for a day because no lane ran it -- the same defect class #2071 recorded
for a lease test that stayed red across 763 commits (a leg nobody runs does not
speak). C6 measures master's roster from
the working tree while #1548's P8 measures it from ``origin/master``, so between
committing and pushing this file is green and P8 is red; the push is what makes
them agree, and that is the same boundary #1548 registered for every other
pointer to master.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
WORKFLOW_DIR = ROOT / ".github" / "workflows"
REGISTER_PATH = ROOT / "evidence" / "branch_reconciliation.py"

#: The orphan branch whose job this leg is carried over from. Absent in a clone
#: that never fetched it -- the branch shares no history with master, so C6 and
#: C8 skip with the count that resolved instead of certifying a guess.
BRANCH_REF = "refs/remotes/origin/feature/p1-reliability-kernel"
BRANCH_QUALITY = ".github/workflows/quality.yml"
JOB_ID = "provider-smoke"
SCRIPT = "scripts/provider_smoke.py"
MIN_MASTER_JOBS = 9
MIN_ENV_FIELDS = 3

_SECRET_IN_TEXT = re.compile(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}\}")
_LEADING_INT = re.compile(r"(\d+)")
_PIP_INSTALL = re.compile(r"(?:^|\s)(?:uv pip|pip) install\b")
_CREATE_VENV = re.compile(r"(?:^|\s)uv venv\b")
#: A step that writes into the venv by path, so it only works once the venv exists.
_VENV_WRITE = re.compile(r"\.venv[/\\]")

#: The branch's job ran on ubuntu with a managed Python; master's job runs on the
#: self-hosted Windows runner, where ``actions/setup-python`` cannot run as a
#: non-administrator (it clears an HKLM Uninstall slot) and #2029 replaced it
#: with ``uv venv``. C8 accepts exactly these swaps -- and C10 requires the
#: master side to be really present, so a swap can never stand in for a dropped
#: guarantee.
_RUNNER_SUBSTITUTIONS: dict[str, str] = {"setup-python": "venv"}


# ══════════════════════════════════════════════════════════════════════════
# rulers
# ══════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _ci_text() -> str:
    return CI_PATH.read_text(encoding="utf-8")


def _doc(text: str) -> dict[str, Any]:
    data = yaml.safe_load(text)
    assert isinstance(data, dict), "workflow did not parse to a mapping"
    return data


@lru_cache(maxsize=1)
def _ci() -> dict[str, Any]:
    return _doc(_ci_text())


def _triggers(doc: dict[str, Any]) -> dict[str, Any]:
    """``on:`` arrives as the boolean True under YAML 1.1, so both spellings."""
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on: None}
    assert isinstance(on, dict), f"triggers parsed to {type(on).__name__}: {on!r}"
    return on


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job.get("steps") or []
    assert isinstance(steps, list), f"{JOB_ID} has a non-list steps block: {steps!r}"
    return [s for s in steps if isinstance(s, dict)]


@lru_cache(maxsize=1)
def _provider_job() -> dict[str, Any]:
    jobs = _ci().get("jobs") or {}
    assert isinstance(jobs, dict) and jobs, f"ci.yml declares no jobs at all: {jobs!r}"
    return jobs.get(JOB_ID) or {}


@lru_cache(maxsize=1)
def _smoke_step() -> dict[str, Any]:
    for step in _steps(_provider_job()):
        if SCRIPT in str(step.get("run", "")):
            return step
    return {}


@lru_cache(maxsize=1)
def _env_fields() -> dict[str, str]:
    """field -> env name, straight from ``providers/config.py``.

    Typed here it would be a second declaration -- and the defect this file
    exists for is a landing typed from memory.
    """
    from providers.config import _ENV_FIELDS  # noqa: PLC0415

    assert isinstance(_ENV_FIELDS, dict) and _ENV_FIELDS, f"owner declared {_ENV_FIELDS!r}"
    return dict(_ENV_FIELDS)


def _declared_env_names() -> frozenset[str]:
    return frozenset(_env_fields().values())


def _master_job_ids() -> set[str]:
    """Every job id master's own workflows declare, from the working tree."""
    out: set[str] = set()
    files = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    assert files, f"no workflow files under {WORKFLOW_DIR}"
    for path in files:
        jobs = _doc(path.read_text(encoding="utf-8")).get("jobs") or {}
        out |= set(jobs)
    return out


def _git_show(ref: str, path: str) -> str | None:
    proc = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="surrogateescape")
    return proc.stdout if proc.returncode == 0 else None


@lru_cache(maxsize=1)
def _branch_job_ids() -> set[str]:
    text = _git_show(BRANCH_REF, BRANCH_QUALITY)
    if text is None:
        pytest.skip(f"{BRANCH_REF} does not resolve in this clone -- the branch "
                    "shares no history with master, so its job roster is only "
                    "readable where it was fetched")
    jobs = _doc(text).get("jobs") or {}
    assert jobs, f"{BRANCH_QUALITY} at {BRANCH_REF} declared no jobs"
    return set(jobs)


@lru_cache(maxsize=1)
def _register() -> Any:
    spec = importlib.util.spec_from_file_location("branch_reconciliation_1549",
                                                  REGISTER_PATH)
    assert spec and spec.loader, f"cannot load {REGISTER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for attr in ("FILE_DISPOSITIONS", "REGISTERED_GAPS", "RENAMED_JOBS"):
        assert hasattr(module, attr), f"register carries no {attr}"
    return module


def _step_kind(step: dict[str, Any]) -> str:
    """A step reduced to what it does, so a rename cannot dodge the parity check.

    ``uv pip install`` is the same guarantee as ``pip install`` (the branch ran
    on ubuntu with a system pip; master's runner gets its packages from uv), and
    ``uv venv`` is what replaced ``actions/setup-python`` here. A classifier that
    only knows the ubuntu spellings reads both as an unknown ``run:`` step, and
    C8 then reports a parity failure for steps that are literally the same job.
    """
    uses = str(step.get("uses", ""))
    if uses.startswith("actions/checkout"):
        return "checkout"
    if uses.startswith("actions/setup-python"):
        return "setup-python"
    if uses:
        return f"uses:{uses.split('@')[0]}"
    run = " ".join(str(step.get("run", "")).split())
    if SCRIPT in run:
        return "smoke-script"
    if _PIP_INSTALL.search(run):
        return "pip-install"
    if _CREATE_VENV.search(run):
        return "venv"
    return f"run:{run[:40]}"


def _python_invocations(doc: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(job id, step name, prefix, rest) for every ci.yml line that runs python.

    ``prefix`` is everything the file puts before the ``python`` token, so the
    question "how does this repo start an interpreter" is answered by the file
    rather than by this gate's memory of one answer.
    """
    out: list[tuple[str, str, str, str]] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in _steps(job):
            name = str(step.get("name", "?"))
            for line in str(step.get("run", "")).splitlines():
                tokens = line.split()
                if "python" not in tokens:
                    continue
                i = tokens.index("python")
                out.append((job_id, name, " ".join(tokens[:i]), " ".join(tokens[i + 1:])))
    return out


# ══════════════════════════════════════════════════════════════════════════
# C1 -- the leg exists and runs the script
# ══════════════════════════════════════════════════════════════════════════

def test_C1_the_leg_exists_and_runs_the_script_it_is_named_for() -> None:
    job = _provider_job()
    assert job, (f"ci.yml has no job {JOB_ID!r}; its roster is {sorted(_master_job_ids())} "
                 "-- the register claims this gap is closed")
    step = _smoke_step()
    assert step, f"no step of {JOB_ID} runs {SCRIPT}; runs were " \
                 f"{[str(s.get('run', ''))[:60] for s in _steps(job)]}"
    run = str(step["run"])
    bare = [ln.strip() for ln in run.splitlines() if ln.strip()]
    line = bare[-1]
    assert "|" not in line and "&&" not in line and ";" not in line, (
        f"the smoke step is a compound command: {line!r}. A pipeline reports the exit "
        "code of its last stage, so a smoke that died halfway can still exit 0")
    invocations = _python_invocations(_ci())
    mine = [t for t in invocations if t[0] == JOB_ID and t[3].startswith(SCRIPT)]
    assert len(mine) == 1, (
        f"{len(mine)} ci.yml lines run python with {SCRIPT} as their first argument in "
        f"{JOB_ID}; C1 can only certify the invocation while there is exactly one")
    prefix, rest = mine[0][2], mine[0][3]
    assert rest == SCRIPT, (
        f"the smoke step runs {rest!r} after the interpreter, not {SCRIPT!r}. A flag "
        "changes what is certified (or prints help and exits 0), and a pipeline that "
        "does not run the smoke is not coverage of the gateway")
    # The interpreter prefix is not free either: the leg has to start python the way
    # the rest of the file does. #2029 moved every ci.yml python call behind `uv run`
    # (the host interpreter is 3.11 and the project needs >=3.12) and the smoke step
    # came along; a prefix used by no other job would mean this leg runs in an
    # environment nothing else in CI has proved it can build.
    others = {t[2] for t in invocations if t[0] != JOB_ID}
    assert prefix in others, (
        f"{JOB_ID} starts python as {prefix!r}, which no other ci.yml job uses "
        f"(theirs: {sorted(others)}). The venv it points at is created by the job that "
        "uses it; an invention here is a job that cannot run")


# ══════════════════════════════════════════════════════════════════════════
# C2 -- the dispatch gate and the trigger have to move together
# ══════════════════════════════════════════════════════════════════════════

def test_C2_the_dispatch_gate_matches_the_declared_triggers() -> None:
    triggers = _triggers(_ci())
    gate = str(_provider_job().get("if", ""))
    assert "workflow_dispatch" in gate, (
        f"{JOB_ID} is gated on {gate!r}. It reads a GitHub environment that only exists "
        "for a manual run: on a push it would get three empty strings and FAIL for the "
        "wrong reason -- and a red CI job that means 'nobody configured it' teaches "
        "people to ignore red CI jobs")
    assert "workflow_dispatch" in triggers, (
        f"the leg waits for an event {JOB_ID} cannot receive: ci.yml triggers are "
        f"{sorted(triggers)}. A job that can never run is coverage on paper")
    assert {"push", "pull_request"} <= set(triggers), (
        f"adding a manual leg removed a trigger the other 8 jobs depend on: {sorted(triggers)}")


# ══════════════════════════════════════════════════════════════════════════
# C3/C4 -- the names are the reader's, not the author's
# ══════════════════════════════════════════════════════════════════════════

def test_C3_every_env_key_the_leg_sets_is_a_name_the_reader_declares() -> None:
    env = _smoke_step().get("env") or {}
    assert env, f"the smoke step sets no env at all: {sorted(_smoke_step())}"
    declared = _declared_env_names()
    unreadable = sorted(set(env) - declared)
    assert not unreadable, (
        f"{JOB_ID} delivers {unreadable} and providers/config.py reads "
        f"{sorted(declared)} -- nothing in this repository reads those names, so the run "
        "reports source='unconfigured' with 0 capabilities beside a green-looking job. "
        "This is the defect this leg was written for")
    needed = {}
    for field in ("base_url", "api_key", "model"):
        assert field in _env_fields(), (
            f"providers/config.py no longer maps the {field!r} field, so this leg's "
            f"population has to be re-read rather than assumed ({sorted(_env_fields())})")
        needed[field] = _env_fields()[field]
    missing = sorted(name for name in needed.values() if name not in env)
    assert not missing, (
        f"the leg omits {missing} -- the names the owner gives for "
        f"{sorted(needed.items())} (it sets {sorted(env)})")


def test_C4_every_secret_the_leg_consumes_names_a_declared_knob() -> None:
    declared = _declared_env_names()
    env = _smoke_step().get("env") or {}
    offenders = {}
    for key, value in env.items():
        for secret in _SECRET_IN_TEXT.findall(str(value)):
            if secret not in declared:
                offenders[key] = secret
    assert not offenders, (
        f"{offenders} maps an env key to secrets.X, and no code reads X: the environment "
        "would have to be configured with a name that is not a knob, and the run would "
        "still report unconfigured")
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        assert _SECRET_IN_TEXT.findall(str(env.get(key, ""))) == [key], (
            f"{key} is not carried by secrets.{key}: the identity is what makes the "
            f"environment setting discoverable (got {env.get(key)!r})")


# ══════════════════════════════════════════════════════════════════════════
# C5 -- the credential lives on an environment, so name it
# ══════════════════════════════════════════════════════════════════════════

def test_C5_the_leg_declares_the_environment_that_holds_the_credentials() -> None:
    environment = _provider_job().get("environment")
    assert environment, (
        f"{JOB_ID} sets secrets but declares no `environment:` -- repository-level "
        "secrets are a different namespace, and an undeclared environment delivers "
        "three empty strings")
    name = environment.get("name") if isinstance(environment, dict) else environment
    assert str(name).strip() == JOB_ID, (
        f"the environment is {name!r}, not {JOB_ID!r}: the name is how an operator finds "
        "which settings a manual leg needs")


# ══════════════════════════════════════════════════════════════════════════
# C6 -- the register's prose number is now a measurement
# ══════════════════════════════════════════════════════════════════════════

def test_C6_the_register_earns_the_count_in_its_own_reason() -> None:
    register = _register()
    key = f"a756f5338:{BRANCH_QUALITY}"
    # #1623 adjudicated every orphan-branch disposition as MERGED (the
    # three root branches landed in master) and archived the whole table,
    # so the live table is empty by construction; the entry lives in the
    # historical home. The arithmetic and the reason are unchanged either
    # way — this is where the row moved, not what it says.
    entry = register.FILE_DISPOSITIONS.get(key) or register.MERGED_FILE_DISPOSITIONS.get(key)
    assert entry, f"the register dropped its {key} disposition"
    reason = " ".join(str(x) for x in (entry["reason"],))
    # #1623 archived the whole adjudication as MERGED_* (the refs are
    # ancestors of master now; the live tables are empty by construction).
    # The merged rename only ever had one row, and the ruler gets it from
    # the archive like the FILE disposition two lines up does.
    renamed = set(register.RENAMED_JOBS) | set(register.MERGED_RENAMED_JOBS)
    absent = _branch_job_ids() - _master_job_ids() - renamed
    measured = _LEADING_INT.search(reason)
    assert measured, f"reason carries no number at all: {reason!r}"
    assert int(measured.group(1)) == len(absent), (
        f"the reason opens with {measured.group(1)} but the rulers measure "
        f"{len(absent)} name-level absences ({sorted(absent)}); branch has "
        f"{len(_branch_job_ids())} jobs, master's workflows declare "
        f"{len(_master_job_ids())} job ids, {len(register.RENAMED_JOBS)} renamed")
    # provider-smoke must be absent from BOTH sides of the register now.
    assert JOB_ID not in register.REGISTERED_GAPS, (
        f"REGISTERED_GAPS still lists {JOB_ID}: #1548's P8 re-derives gaps from the "
        "refs, so a stale row here is a gap that reads as still open")
    assert JOB_ID not in register.MERGED_REGISTERED_GAPS, (
        f"MERGED_REGISTERED_GAPS still lists {JOB_ID}: the #1549 landing carried "
        "the branch's job into master's ci.yml step-for-step, so the archive row "
        "reading as open is the same ghost the live table would have been")
    assert JOB_ID not in register.RENAMED_JOBS, (
        f"{JOB_ID} is registered as a rename, not as landed -- ci.yml carries the "
        "branch's own job id, so there is nothing to rename")
    assert JOB_ID not in register.MERGED_RENAMED_JOBS, (
        f"{JOB_ID} is registered as a rename in the MERGED archive either; the "
        "branch's job carried the id verbatim, so no row can say rename")


# ══════════════════════════════════════════════════════════════════════════
# C7 -- secrets reach the child through env, never through a command line
# ══════════════════════════════════════════════════════════════════════════

def test_C7_no_run_command_interpolates_a_secret() -> None:
    offenders: list[str] = []
    scanned = 0
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        scanned += 1
        for job_id, job in (_doc(path.read_text(encoding="utf-8")).get("jobs") or {}).items():
            for step in _steps(job) if isinstance(job, dict) else []:
                if _SECRET_IN_TEXT.search(str(step.get("run", ""))):
                    offenders.append(f"{path.name}::{job_id}::{step.get('name', '?')}")
    assert scanned >= 2, f"only {scanned} workflow files scanned -- the census read nothing"
    assert not offenders, (
        f"{offenders} put ${{{{ secrets.* }}}} inside a run: command. The command line is "
        "visible in the runner's job log and in any process listing the step shells out "
        "to; env: is the channel that keeps the value off the log")


# ══════════════════════════════════════════════════════════════════════════
# C8 -- the leg is the branch's job, not a job with its name
# ══════════════════════════════════════════════════════════════════════════

def test_C8_the_leg_carries_the_branch_steps_not_a_reimplementation() -> None:
    branch_text = _git_show(BRANCH_REF, BRANCH_QUALITY)
    if branch_text is None:
        pytest.skip(f"{BRANCH_REF} does not resolve here; master's "
                    f"{len(_master_job_ids())} job ids are still checked by C1-C6")
    branch_job = (_doc(branch_text).get("jobs") or {}).get(JOB_ID)
    assert branch_job, f"{BRANCH_REF}:{BRANCH_QUALITY} has no {JOB_ID} any more"
    want = Counter(_step_kind(s) for s in _steps(branch_job))
    got = Counter(_step_kind(s) for s in _steps(_provider_job()))
    # The two runners are not the same machine, and the file says so; the swaps are
    # declared above rather than absorbed by a looser comparison.
    for branch_kind, master_kind in _RUNNER_SUBSTITUTIONS.items():
        if want.get(branch_kind):
            want[branch_kind] -= 1
            want[master_kind] += 1
    got_kinds = set(got)
    unobserved = [f"{b}->{m}" for b, m in _RUNNER_SUBSTITUTIONS.items()
                  if m not in got_kinds]
    assert not unobserved, (
        f"this gate allows {sorted(_RUNNER_SUBSTITUTIONS.items())} because the branch ran "
        f"on ubuntu and master's runner is Windows, but the master side is missing "
        f"{unobserved}: a declared swap that is not present is a guarantee that was "
        "dropped, not moved")
    assert want == got, (
        f"the carried-over job differs from the branch's own (after the declared runner "
        f"swaps): branch {sorted(want.elements())} "
        f"vs master {sorted(got.elements())} -- a missing step is a claim of convergence "
        "with one of the branch's guarantees dropped")
    assert want.get("smoke-script") == 1, (
        f"the branch's job runs the smoke {want.get('smoke-script')} times; this gate's "
        "parity claim only means something while it is exactly 1")


# ══════════════════════════════════════════════════════════════════════════
# C10 -- the job builds the environment its own steps write into
# ══════════════════════════════════════════════════════════════════════════

def test_C10_the_job_provisions_the_environment_its_steps_install_into() -> None:
    """The leg has to create the interpreter before it can install into it.

    WHY THIS LEG EXISTS (run 44912703445, 2026-11-21, the job's first real run):
    ``uv pip install --python .venv/Scripts/python.exe -e ".[dev]"`` died with
    "No virtual environment or system Python installation found for path
    .venv/Scripts/python.exe; run `uv venv` to create an environment". The branch's
    job never hit this because ubuntu + setup-python created the interpreter for it;
    copying the job across kept the writes to ``.venv`` and lost the thing that
    makes ``.venv`` exist. C1-C9 were all green on that file.
    """
    steps = _steps(_provider_job())
    assert steps, f"{JOB_ID} declares no steps"
    consumers = [(i, s) for i, s in enumerate(steps) if _VENV_WRITE.search(str(s.get("run", "")))]
    assert consumers, (
        f"no step of {JOB_ID} names a venv path at all -- this leg checks that whoever "
        f"writes into .venv first creates it, and with none it proves nothing")
    providers = [i for i, s in enumerate(steps)
                 if str(s.get("uses", "")).startswith("actions/setup-python")
                 or _CREATE_VENV.search(str(s.get("run", "")))]
    assert providers, (
        f"{JOB_ID} installs into a venv at {[i for i, _ in consumers]} but nothing creates "
        "one: no actions/setup-python and no `uv venv`. On the self-hosted Windows runner "
        "that is exit 1 at the install step, and the dispatch button reads as a broken "
        "gateway when nothing was ever called")
    first_write = min(i for i, _ in consumers)
    assert min(providers) < first_write, (
        f"{JOB_ID} creates the environment at step {min(providers)} but writes into it at "
        f"step {first_write} -- an install that runs before the venv exists fails the "
        "same way whether or not the file mentions both")


# ══════════════════════════════════════════════════════════════════════════
# C9 -- the ruler proves it read something
# ══════════════════════════════════════════════════════════════════════════

def test_C9_the_ruler_reads_a_population_it_can_be_wrong_about() -> None:
    jobs = _ci().get("jobs") or {}
    assert len(jobs) >= MIN_MASTER_JOBS, (
        f"ci.yml declares {len(jobs)} jobs, floor {MIN_MASTER_JOBS} -- a roster that "
        "collapsed reads exactly like a leg that was removed for a reason")
    assert JOB_ID in jobs, f"{sorted(jobs)}"
    assert len(_declared_env_names()) >= MIN_ENV_FIELDS, (
        f"providers/config.py declared {len(_declared_env_names())} names, floor "
        f"{MIN_ENV_FIELDS}: an empty name set makes C3/C4 true for every typo")
    # The ruler must disagree with a hand-typed roster somewhere, or it is prose.
    typed = {"lint-type", "web", "java-services", "openapi-schema-diff", "security",
             "tests-no-infra", "tests-with-infra", "eval-golden-cases", "e2e",
             JOB_ID}
    assert typed == set(jobs), (
        f"the roster this gate's own docstring quotes ({len(typed)} ids) no longer "
        f"matches ci.yml ({sorted(jobs)}) -- update the quoted list by reading it, "
        "in the same change that moved the roster")
    assert _SECRET_IN_TEXT.search(_ci_text().split("jobs:")[1] or ""), (
        "ci.yml declares a job roster but carries no secrets interpolation at all: "
        "C3/C4/C7 would pass about nothing")
