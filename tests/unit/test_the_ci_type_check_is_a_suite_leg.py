"""#479 — the type check CI runs has to be a leg the suite runs too.

Measured cause: `.github/workflows/ci.yml` gates every push with `python -m mypy .`
(strict, per `[tool.mypy]` in `pyproject.toml`), and at `9c2c7e3` that step reported
3 errors in 2 files while the unit suite ran green over the same bytes. Both errors
had been sitting there since the commit that wrote them (#297 removed the `cast` in
`mcp/client.py`; #456 added a second, Optional-typed derivation in
`agent/self_test_diff.py`). That is the defect this file closes: nothing a developer
or an agent runs between "pytest is green" and "pushed" re-checks types, so a batch
can break the merge gate and see only green doing it.

This file does not retype CI's command line — it reads the workflow and runs what it
finds there, so the day the step changes shape the leg asks to be reconciled instead
of quietly grading something else. The four lens legs then prove the arm is loaded:
the same runner reports a wrong return type, stays green on a matching one, and
refuses an un-annotated def — the last only because the shipped config says strict,
which the empty-config twin of that same leg is what distinguishes.

Cost, measured with this file's own run shape (the module's whole set inside the
suite) rather than from a one-off cold command: see #479's ledger entry.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

#: The whole repository under a strict config is a real child doing real work.
#: Budgeted the way #157 budgeted the spawned children: a false timeout costs a
#: red run and an investigation, a genuinely hung child only costs the wait.
_TIMEOUT = 900.0

#: A def whose body cannot be faulted for anything but its annotations.
_BARE_DEF = "def double(value):\n    return value\n"
#: The same def, annotated, returning the wrong type.
_WRONG_RETURN = 'def double(value: int) -> int:\n    return "nope"\n'
#: The same def, annotated, returning what it promises.
_MATCHING_RETURN = "def double(value: int) -> int:\n    return value\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


def _judge(argv: list[str]) -> tuple[int, str]:
    """Run one type-check command from the repository root, as CI does.

    The codec is named because the report carries paths and this host's console
    codec is cp936: an unnamed `text=True` here would read the failure as `None`
    (#92) exactly when the leg has the most to say.
    """
    proc = subprocess.run(
        argv,
        cwd=REPO,
        capture_output=True,
        timeout=_TIMEOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _ci_type_check_commands() -> list[list[str]]:
    """Every `run:` line in the CI workflow that invokes mypy, tokenised.

    Read from the workflow rather than typed out again: a leg that hard-codes the
    command keeps passing after the step it claims to mirror is edited or deleted.
    """
    doc: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    commands: list[list[str]] = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run")
            if not isinstance(run, str):
                continue
            tokens = run.split()
            if "mypy" in tokens:
                commands.append(tokens)
    return commands


def _runner_argv(tokens: list[str]) -> list[str]:
    """CI's `python` is the venv interpreter running the step; here that is us."""
    assert tokens, "an empty `run:` line cannot invoke the type checker"
    assert tokens[0] == "python", (
        f"CI's type-check step no longer starts with `python`: {tokens!r}. "
        "Re-aim this translation, do not quietly drop the leg."
    )
    return [sys.executable, *tokens[1:]]


# ── the CI parity, both ends ───────────────────────────────────────────


def test_the_ci_workflow_declares_a_type_check_step() -> None:
    commands = _ci_type_check_commands()
    assert commands, (
        f"no `run:` line in {WORKFLOW.relative_to(REPO).as_posix()} invokes mypy. "
        "Either CI dropped the step — then this file is the only type coverage the "
        "repo has and must say so — or the workflow moved."
    )


def test_the_suite_judges_the_whole_repository_ci_judges() -> None:
    # The claim is "the same scope", not "the same tool": a leg that type-checked a
    # hand-picked file list would keep passing while CI graded a red repository.
    for tokens in _ci_type_check_commands():
        assert tokens[-1] == ".", (
            f"CI type-checks {tokens!r}, which is not the whole repository. This leg "
            "promised to judge what CI judges, so widen it or narrow the claim."
        )


def test_the_shipped_packages_pass_the_type_check_ci_runs() -> None:
    failures: list[str] = []
    for tokens in _ci_type_check_commands():
        code, report = _judge(_runner_argv(tokens))
        if code != 0:
            failures.append(f"{' '.join(tokens)} -> exit {code}\n{report}")
    assert not failures, (
        "the repository does not type-check under the command CI gates it with:\n"
        + "\n".join(failures)
    )


# ── the lens is loaded ─────────────────────────────────────────────────


def test_the_lens_reports_a_returned_value_of_the_wrong_type(tmp_path: Path) -> None:
    target = _write(tmp_path, "leak.py", _WRONG_RETURN)
    code, report = _judge([sys.executable, "-m", "mypy", str(target)])
    assert code != 0, (
        f"a function returning str where it promises int typed clean ({code}):\n{report}\n"
        "the runner is not grading the repository's own strict config"
    )
    assert "Incompatible return value type" in report, (
        f"the run failed, but not for the charged reason:\n{report}"
    )


def test_the_lens_passes_a_matching_return_type(tmp_path: Path) -> None:
    # The twin of the leg above: same file, same annotations, the value it promises.
    # Without it the red above could be the harness, the config or the interpreter.
    target = _write(tmp_path, "clean.py", _MATCHING_RETURN)
    code, report = _judge([sys.executable, "-m", "mypy", str(target)])
    assert code == 0, (
        f"a def that cannot fail to type-check was refused ({code}):\n{report}"
    )


def test_the_lens_refuses_an_un_annotated_def(tmp_path: Path) -> None:
    # `disallow_untyped_defs` is not mypy's default: this red is the shipped
    # `[tool.mypy]` speaking, which is what makes the leg above the repository the
    # strict merge gate CI advertises rather than a loose one.
    target = _write(tmp_path, "bare.py", _BARE_DEF)
    code, report = _judge([sys.executable, "-m", "mypy", str(target)])
    assert code != 0, (
        f"an un-annotated def typed clean ({code}):\n{report}\n"
        "the config the CI step relies on is not being loaded from here"
    )
    assert "missing a type annotation" in report, (
        f"the run failed, but not for the charged reason:\n{report}"
    )


def test_the_same_def_is_green_under_an_empty_config(tmp_path: Path) -> None:
    # Reverse control for the leg beside it: identical bytes, no strict config.
    # If this also went red the red says something about mypy, not about the repo.
    target = _write(tmp_path, "bare.py", _BARE_DEF)
    empty_config = _write(tmp_path, "no-strict.ini", "[mypy]\n")
    code, report = _judge(
        [sys.executable, "-m", "mypy", "--config-file", str(empty_config), str(target)]
    )
    assert code == 0, (
        f"the un-annotated def was refused without the shipped config too ({code}):\n"
        f"{report}\nso the other leg was never proving strictness"
    )
