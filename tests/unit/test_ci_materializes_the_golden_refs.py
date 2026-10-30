"""#521 — CI must be able to RESOLVE the golden refs its evaluations read.

WHY THIS EXISTS.  Every golden case's ``scenario.json`` names two git refs
(``base`` and ``<case>-head``, or ``head-v1`` for case-01) that the pipeline
checks out to diff.  Those refs are built by
``scripts/build_golden_scenarios.py`` and are LOCAL tags: every rebuild
produces new commits, so a CI checkout carries only whatever earlier rebuilds
happened to push — measured on origin 2026-10-29: ``base``, ``head-v1``,
``p0.5-verified-v1`` and seven ``case-*-head`` tags, none of them the pair a
fresh checkout would have built.  CI run 40714443058 (2026-10-28) is the
measurement:
``tests-with-infra`` and ``eval-golden-cases`` both aborted in the eval's ref
preflight, which named ``case-12/17/21/56-head`` as unresolved.  A setup
problem, wearing the clothes of an eval result.

THE FIX THIS FILE BINDS.  ``--refs-only`` treats the checkout itself as the
honest base: it tags ``base`` at HEAD, rebuilds ``head-v1`` and the selected
cases in temporary worktrees, and never moves HEAD or dirties the tree the
evaluation is about to read.  The push-triggered jobs build only the cases
they evaluate (a full rebuild on this machine measured 1356 s); the nightly
builds all of them, because its 100-case run needs all of them.

THE RULERS, each one sentence:

  R1  on a tagless checkout the case refs do not resolve, and after
      ``--refs-only`` they do — without moving HEAD or dirtying anything
      (measured by building two of the cases CI evaluates, one of each ref
      family: case-01 resolves ``head-v1``, case-56 its own tag); stale
      ``base``/``head-v1`` tags of the kind a fetch delivers are moved to
      this checkout, not fought;
  R2  both push-triggered jobs that evaluate cases materialize the refs
      BEFORE the step that evaluates, with the git identity the builder's
      commits need;
  R3  each job's ``--only`` list covers every case the job actually
      evaluates — derived from the eval job's own ``cp -r golden-cases/...``
      lines and the integration test's ``HTML_REPORT_SUBSET`` — and every id
      names a real case directory;
  R4  the nightly builds the FULL set (no ``--only``) before its 100-case
      run, and the push-triggered integration job deselects exactly the
      marker the 100-case test carries — otherwise one push re-runs the
      multi-hour nightly.

WHAT IS DELIBERATELY OUT OF SCOPE.  Pushing the tags: a rebuild creates new
commits every time, so a pushed copy could never match the checkout, and
force-updating ``base`` would rewrite what every earlier report compared
against.  This file also does not judge what an evaluation finds.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import yaml

from cli.specproof.commands.eval import _ref_problems

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
NIGHTLY = ROOT / ".github" / "workflows" / "nightly-eval.yml"
GOLDEN = ROOT / "golden-cases"
ACCEPTANCE = ROOT / "tests" / "integration" / "test_phase_acceptance.py"
BUILDER = "scripts/build_golden_scenarios.py"

#: The job with the databases — it runs tests/integration.
INFRA_JOB = "tests-with-infra"
#: The job that runs the representative deterministic evaluation.
EVAL_JOB = "eval-golden-cases"

#: The 100-case evaluation's marker, deselected in the push-triggered job.
SLOW_MARKER = "slow_eval"


# ---------------------------------------------------------------------------
# reading the workflows
# ---------------------------------------------------------------------------


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(parsed: dict, job_id: str) -> list[dict]:
    jobs = parsed.get("jobs") or {}
    assert job_id in jobs, f"{job_id!r} is not a job in this workflow: {sorted(jobs)}"
    return list(jobs[job_id].get("steps") or [])


def _run_scripts(steps: list[dict]) -> list[str]:
    return [str(step["run"]) for step in steps if isinstance(step.get("run"), str)]


def _joined(script: str) -> str:
    """The script with its backslash continuations resolved to one line."""
    return re.sub(r"\\[ \t]*\n", " ", script)


def _tokens(script: str) -> list[str]:
    return shlex.split(_joined(script))


def _flag_value(tokens: list[str], flag: str, start: int = 0) -> str | None:
    if flag not in tokens[start:]:
        return None
    index = tokens.index(flag, start)
    assert index + 1 < len(tokens), f"{flag} has no value in {tokens!r}"
    return tokens[index + 1]


def _builder_index(steps: list[dict]) -> int:
    found = [
        index
        for index, step in enumerate(steps)
        if BUILDER in str(step.get("run") or "")
    ]
    assert len(found) == 1, (
        f"expected exactly one step that runs {BUILDER}, found {found}"
    )
    return found[0]


def _eval_index(steps: list[dict], needle: str) -> int:
    found = [
        index
        for index, step in enumerate(steps)
        if needle in str(step.get("run") or "")
    ]
    assert found, f"no step runs {needle!r}"
    return found[0]


# ---------------------------------------------------------------------------
# deriving the cases the jobs evaluate
# ---------------------------------------------------------------------------


def _short_case_id(case_dir: str) -> str:
    """``case-12-add-javadoc`` -> ``case-12`` (the builder's ``--only`` id)."""
    match = re.match(r"^(case-\d+)-", case_dir)
    assert match, f"not a golden case directory name: {case_dir!r}"
    return match.group(1)


def _eval_job_case_dirs(ci: dict) -> list[str]:
    """The cases the eval job copies into its subset — derived, not retyped.

    A second assertion pins the count to the ``cp`` lines so a rewrite of the
    copy syntax cannot silently shrink the derived set to nothing.
    """
    dirs: list[str] = []
    cp_lines = 0
    for script in _run_scripts(_steps(ci, EVAL_JOB)):
        for line in script.splitlines():
            stripped = line.strip()
            if not stripped.startswith("cp "):
                continue
            if "golden-cases/" not in stripped:
                continue
            cp_lines += 1
            match = re.search(r"golden-cases/(case-\d+-[a-z0-9-]+)", stripped)
            assert match, f"cannot read a case directory out of: {stripped!r}"
            dirs.append(match.group(1))
    assert cp_lines, f"{EVAL_JOB} copies no golden cases; the derivation is blind"
    return sorted(set(dirs))


def _html_report_subset() -> tuple[str, ...]:
    """The integration test's own subset, read off its AST."""
    tree = ast.parse(ACCEPTANCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "HTML_REPORT_SUBSET"
            for target in node.targets
        ):
            continue
        value = ast.literal_eval(node.value)
        assert isinstance(value, tuple) and value, value
        return value
    raise AssertionError(f"{ACCEPTANCE.name} no longer defines HTML_REPORT_SUBSET")


def _required_case_dirs(ci: dict) -> list[str]:
    return sorted(set(_eval_job_case_dirs(ci)) | set(_html_report_subset()))


def _markers_of_test(name: str) -> set[str]:
    """The pytest markers a test function carries."""
    tree = ast.parse(ACCEPTANCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != name:
            continue
        marks: set[str] = set()
        for decorator in node.decorator_list:
            # pytest.mark.<name>
            inner = getattr(decorator, "value", None)
            if (
                isinstance(decorator, ast.Attribute)
                and isinstance(inner, ast.Attribute)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "pytest"
                and inner.attr == "mark"
            ):
                marks.add(decorator.attr)
        return marks
    raise AssertionError(f"{ACCEPTANCE.name} has no test named {name!r}")


# ---------------------------------------------------------------------------
# R1  the mechanism, measured on a tagless checkout
# ---------------------------------------------------------------------------


def _git_ok(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ("git", "-C", str(cwd), *args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, (
        f"git {' '.join(args)} in {cwd} -> rc={proc.returncode} "
        f"{proc.stderr[:400]!r}"
    )
    return proc.stdout


def _remove_plane(plane: Path) -> None:
    """Remove the plane even when git left read-only files behind (Windows)."""
    for root, dirs, files in os.walk(plane):
        for name in dirs + files:
            with contextlib.suppress(OSError):
                os.chmod(os.path.join(root, name), stat.S_IWRITE)
    shutil.rmtree(plane, ignore_errors=True)


def _plane_with(plane: Path, paths: list[str]) -> None:
    """Extract HEAD's bytes for ``paths`` into ``plane`` and commit them.

    The plane is the checkout shape CI has — a complete working tree, no
    golden refs — carrying the inputs the builder and the chosen scenarios
    read: the whole ``demo/`` subtree (every mutation the two chosen cases
    apply lives there), their ``golden-cases/`` directories, and the builder.
    A ``git clone`` would model the same thing with 2340 files and measure
    170 s here (clone + two worktree checkouts); the full tree changes what
    the builder does not read.
    """
    data = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD", *paths],
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(plane, filter="data")


def test_refs_only_materializes_the_case_refs_on_a_tagless_checkout() -> None:
    """R1: the fix, measured on the checkout shape CI actually has.

    The plane is a fresh repository with HEAD's bytes for the paths the
    builder reads, and no tags — CI's checkout, reduced to what this
    mechanism consumes.  The builder under test is the WORKING-TREE script
    (the archived copy carries HEAD's bytes, and a gate that measured the
    old script would certify the old behaviour).
    """
    plane = Path(
        tempfile.mkdtemp(prefix="specproof-refs-plane-", dir=str(ROOT.parent))
    )
    try:
        subprocess.run(
            ["git", "init", "--quiet", str(plane)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        _git_ok(plane, "config", "user.name", "specproof-gate")
        _git_ok(plane, "config", "user.email", "specproof-gate@example.invalid")
        hooks = plane / ".no-hooks"
        hooks.mkdir()
        _git_ok(plane, "config", "core.hooksPath", str(hooks))

        required = _required_case_dirs(_workflow(CI))
        # One case of each ref family: case-01's scenario resolves head-v1,
        # case-56's resolves its own <case>-head tag.  Two, not six, because
        # every case costs a full worktree checkout.
        chosen = [required[0], required[-1]]
        assert [_short_case_id(name) for name in chosen] == ["case-01", "case-56"]
        _plane_with(
            plane,
            ["demo", "scripts", *[f"golden-cases/{name}" for name in chosen]],
        )
        shutil.copyfile(ROOT / BUILDER, plane / BUILDER)
        _git_ok(plane, "add", "-A")
        _git_ok(plane, "commit", "--quiet", "-m", "plane: HEAD's bytes, no tags")
        assert _git_ok(plane, "tag", "-l").strip() == "", "the plane carries tags"
        status_before = _git_ok(plane, "status", "--porcelain")
        assert status_before == "", status_before
        # CI's fetch does not deliver a tagless checkout: origin carries stale
        # ``base``/``head-v1`` and seven case tags from earlier rebuilds
        # (measured 2026-10-29: origin's ``base`` is 3d34c4d, this repo's is
        # 90ba16a). A builder that refused to move an existing tag would abort
        # the job; one that left it stale would diff HEAD against an old
        # commit. Both are caught here.
        _git_ok(plane, "commit", "--quiet", "--allow-empty", "-m", "stale anchor")
        stale = _git_ok(plane, "rev-parse", "HEAD~1").strip()
        _git_ok(plane, "tag", "base", stale)
        _git_ok(plane, "tag", "head-v1", stale)
        head_before = _git_ok(plane, "rev-parse", "HEAD").strip()
        assert head_before != stale

        dirs = [plane / "golden-cases" / name for name in required]
        setup_red = _ref_problems(str(plane), dirs)
        assert setup_red, (
            "the tagless checkout resolved the case refs after all — this "
            "gate would then certify nothing: " + repr(setup_red)
        )
        assert [_short_case_id(name) for name in chosen] == ["case-01", "case-56"]
        proc = subprocess.run(
            [
                sys.executable,
                BUILDER,
                "--refs-only",
                "--only",
                ",".join(_short_case_id(name) for name in chosen),
            ],
            cwd=plane,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
        )
        output = proc.stdout[-3000:] + proc.stderr[-3000:]
        assert proc.returncode == 0, f"--refs-only failed:\n{output}"

        chosen_dirs = [plane / "golden-cases" / name for name in chosen]
        assert _ref_problems(str(plane), chosen_dirs) == [], output
        assert _git_ok(plane, "rev-parse", "HEAD").strip() == head_before, (
            "the builder moved HEAD; CI's evaluation would read a different base"
        )
        assert _git_ok(plane, "status", "--porcelain") == status_before, (
            "the builder dirtied the checkout the evaluation reads"
        )

        base_commit = _git_ok(plane, "rev-parse", "base^{commit}").strip()
        assert base_commit == head_before, (
            "`base` still names the commit the stale tag carried "
            f"({base_commit[:7]}), not this checkout ({head_before[:7]}); the "
            "evaluation would diff two commits that are not on this tree"
        )
        base_tree = _git_ok(plane, "rev-parse", "base^{tree}").strip()
        assert _git_ok(plane, "rev-parse", "head-v1^{commit}").strip() != stale, (
            "`head-v1` was not rebuilt: it still names the stale fetched commit"
        )
        heads = {
            name: json.loads(
                (plane / "golden-cases" / name / "scenario.json").read_text(
                    encoding="utf-8"
                )
            )["head_ref"]
            for name in chosen
        }
        assert heads[chosen[0]] == "head-v1", heads
        assert heads[chosen[1]] == _short_case_id(chosen[1]) + "-head", heads
        for ref in set(heads.values()):
            _git_ok(plane, "rev-parse", "--verify", f"{ref}^{{commit}}")
            assert _git_ok(plane, "rev-parse", f"{ref}^{{tree}}").strip() != base_tree, (
                f"{ref} did not change a single byte from base"
            )
            ahead = _git_ok(plane, "rev-list", "--count", f"base..{ref}").strip()
            assert ahead == "1", f"{ref} is {ahead} commits off base, expected 1"
    finally:
        _remove_plane(plane)


# ---------------------------------------------------------------------------
# R2  both evaluating jobs build the refs before they evaluate
# ---------------------------------------------------------------------------


def test_both_evaluating_jobs_materialize_the_refs_before_they_evaluate() -> None:
    ci = _workflow(CI)
    for job_id, needle in (
        (INFRA_JOB, "pytest tests/integration"),
        (EVAL_JOB, "cli.specproof.main eval"),
    ):
        steps = _steps(ci, job_id)
        index = _builder_index(steps)
        script = str(steps[index]["run"])
        assert "--refs-only" in _joined(script), (
            f"{job_id} builds the refs without --refs-only: it would commit on "
            "the checkout instead of a worktree"
        )
        assert "git config user.email" in script, (
            f"{job_id} builds refs before configuring a git identity; the "
            "builder's commits would fail in CI"
        )
        evaluate = _eval_index(steps, needle)
        assert index < evaluate, (
            f"{job_id} evaluates at step {evaluate} but materializes the refs "
            f"at step {index}; the eval would abort in its ref preflight"
        )


# ---------------------------------------------------------------------------
# R3  each job's --only list covers what the job evaluates
# ---------------------------------------------------------------------------


def test_each_jobs_only_list_covers_every_case_the_job_evaluates() -> None:
    ci = _workflow(CI)
    required_dirs = _required_case_dirs(ci)
    required = sorted({_short_case_id(name) for name in required_dirs})
    case_dirs = {path.name for path in GOLDEN.iterdir() if path.is_dir()}
    missing_dirs = sorted(set(required_dirs) - case_dirs)
    assert not missing_dirs, (
        f"the jobs evaluate case directories that do not exist: {missing_dirs}"
    )

    for job_id in (INFRA_JOB, EVAL_JOB):
        steps = _steps(ci, job_id)
        script = str(steps[_builder_index(steps)]["run"])
        raw = _flag_value(_tokens(script), "--only")
        assert raw, f"{job_id} builds every case ref on every push (no --only)"
        only = [part for part in raw.split(",") if part]
        missing = sorted(set(required) - set(only))
        assert not missing, (
            f"{job_id}'s --only list ({only}) misses the cases it evaluates "
            f"({missing}); the eval would abort in its ref preflight"
        )
        unknown = sorted(set(only) - {_short_case_id(name) for name in case_dirs})
        assert not unknown, (
            f"{job_id}'s --only list names ids that are not golden cases: {unknown}"
        )


# ---------------------------------------------------------------------------
# R4  the nightly builds everything; the push job does not run the nightly
# ---------------------------------------------------------------------------


def test_the_nightly_builds_the_full_ref_set_before_the_100_case_run() -> None:
    nightly = _workflow(NIGHTLY)
    jobs = list(nightly.get("jobs") or {})
    assert len(jobs) == 1, f"nightly has {len(jobs)} jobs: {jobs}"
    steps = _steps(nightly, jobs[0])
    index = _builder_index(steps)
    script = str(steps[index]["run"])
    tokens = _tokens(script)
    assert "--refs-only" in _joined(script)
    assert "--only" not in tokens, (
        "the nightly builds a subset; its 100-case run resolves every case ref"
    )
    assert "git config user.email" in script
    run_index = _eval_index(steps, "--cases golden-cases")
    assert index < run_index, "the nightly evaluates before it builds the refs"


def test_the_push_job_deselects_exactly_the_nightly_marker() -> None:
    ci = _workflow(CI)
    steps = _steps(ci, INFRA_JOB)
    index = _eval_index(steps, "pytest tests/integration")
    tokens = _tokens(str(steps[index]["run"]))
    # ``python -m pytest`` carries its own -m; the marker flag comes after it.
    expression = _flag_value(tokens, "-m", start=tokens.index("pytest") + 1)
    assert expression == f"not {SLOW_MARKER}", (
        f"{INFRA_JOB} runs pytest with -m {expression!r}; the multi-hour "
        "evaluation would then run on every push"
    )
    carried = _markers_of_test("test_specproof_eval_runs_all_cases")
    assert SLOW_MARKER in carried, (
        f"the push job deselects {SLOW_MARKER!r}, but "
        f"test_specproof_eval_runs_all_cases carries {sorted(carried)}; the "
        "deselection would be a no-op and the 100-case run would happen here"
    )
