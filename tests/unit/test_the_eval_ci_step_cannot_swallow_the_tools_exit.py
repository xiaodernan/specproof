"""#537 — the eval CI step must not swallow the tool's own exit code.

WHY THIS EXISTS.  CI run 41067550985, HEAD ``1745654``: the eval job finished
GREEN while its own sidecar recorded ``Acceptance: INSUFFICIENT`` — the only
negative control (case-12) had NOT_RUN, so ``negative_cases`` was 0 and the
sample floor ``--min-negative-cases 1`` was unmet.  The tool did exit non-zero;
``cli/specproof/commands/eval.py`` ends with

    if gate and not acceptance.passed:
        raise SystemExit(1)

but both workflows ran it as

    python -m cli.specproof.main eval ... | tee eval-run.log

and a pipeline's status is its LAST command's.  ``tee`` succeeded, so the step
succeeded; the three grep gates below it then judged a log whose recall and
precision had been computed over only the cases that did run — and passed.
The subset's own floors made the run INSUFFICIENT, and nothing listened.

This is the #205/#224/#225 disease one layer out: those fixed the tool's
verdict and the greps that read it, but the shell between them was never
measured.  A gate that cannot fail is not a gate.

THE RULERS:

  R1  every workflow step that captures the eval log through ``tee`` arms
      ``pipefail`` before the pipeline, so the tool's verdict reaches the
      step;
  R2  the shipped script, run by a shell, FAILS when the tool fails — the
      producer is replaced by a command that exits 1 and the step script is
      executed under ``bash -e`` (the shell shape GitHub ran, as the green
      job above demonstrates);
  R3  reverse control — without the arming line the SAME pipeline exits 0:
      ``tee`` really does swallow the verdict, so R1 is load-bearing and not
      a decorative clause;
  R4  the census reaches every workflow that writes ``eval-run.log``, so a
      moved capture shape fails this file loudly instead of going quiet.

The evidence side of the same change (a failing step must still publish the
sidecar that says WHY) is pinned in
``test_ci_publishes_the_eval_evidence.py``; the CI subset's sample floors are
pinned against the copied population in ``test_ci_eval_subset_is_measurable.py``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

#: The capture shape the workflows use, measured in the two files.
PIPE = "| tee eval-run.log"
#: The producer whose exit status has to survive the pipeline.  Its failure
#: status is ``SystemExit(1)`` in eval.py when ``--gate`` is set and the
#: acceptance verdict is not PASS.
PRODUCER = "python -m cli.specproof.main eval"
#: Stands in for the producer in R2/R3.  A failing command must fail the
#: step; a successful one must succeed, and the pipeline's report is what
#: is under test — not the stub.
FAILING_PRODUCER = "false"


def _capture_scripts() -> dict[str, str]:
    """workflow name -> the one ``run`` script that captures the eval log."""
    out: dict[str, str] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(text)
        scripts: list[str] = []
        for job in (parsed.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                script = step.get("run")
                if isinstance(script, str) and PIPE in script:
                    scripts.append(script)
        if scripts:
            assert len(scripts) == 1, (
                f"{path.name}: {len(scripts)} run steps pipe the eval into "
                "eval-run.log; the capture shape must have one owner"
            )
            out[path.name] = scripts[0]
        elif "eval-run.log" in text:
            raise AssertionError(
                f"{path.name} mentions eval-run.log but no run step pipes into "
                f"it through {PIPE!r} — the census would not see this capture "
                "at all, so the gate would read as green over an unmeasured "
                "step"
            )
    assert len(out) >= 2, (
        f"expected the eval-log capture in every evaluating workflow, found "
        f"{sorted(out)} — the steps moved or were rewritten"
    )
    return out


def _is_pipefail_arming(line: str) -> bool:
    """A shell line that execs ``set`` with the ``pipefail`` option.

    Comments are excluded by requiring the line to START with ``set``: a
    note that happens to mention pipefail must not satisfy the gate — a
    commented-out arming is exactly the regression an arm measures.
    """
    stripped = line.strip()
    return stripped.startswith("set") and "pipefail" in stripped


def _pipe_line(lines: list[str]) -> int:
    hits = [index for index, line in enumerate(lines) if PIPE in line]
    assert len(hits) == 1, (
        f"expected exactly one capture pipeline in the step, found lines "
        f"{hits} — a second capture would take a different code path than "
        "the one this gate measures"
    )
    return hits[0]


def test_r1_every_capture_step_arms_pipefail_before_the_pipeline() -> None:
    """The step's status must be the tool's status, not ``tee``'s."""
    for name, script in _capture_scripts().items():
        lines = script.splitlines()
        pipe_at = _pipe_line(lines)
        armed = [line for line in lines[:pipe_at] if _is_pipefail_arming(line)]
        assert armed, (
            f"{name}: the eval is piped into tee without arming pipefail. "
            "A pipeline reports its last command's status, so SystemExit(1) "
            "from eval.py's --gate becomes tee's 0 and the step passes — "
            "measured: CI run 41067550985 finished this job green beside "
            "'Acceptance: INSUFFICIENT'"
        )


def _materialize_step(directory: Path, script: str) -> None:
    """Write the step as the shell would see it, with a failing producer.

    The prologue's own filesystem touches (``mkdir -p``, ``cp -r``) are
    pre-created so the script reaches the pipeline; a failure before it
    would make the step fail for a reason that is not under test.
    """
    assert script.count(PRODUCER) == 1, (
        f"the step no longer invokes {PRODUCER!r} exactly once "
        f"({script.count(PRODUCER)} found) — the witness has lost its subject"
    )
    failing = script.replace(PRODUCER, FAILING_PRODUCER, 1)
    for source in re.findall(r"cp -r (\S+)", failing):
        (directory / source).mkdir(parents=True, exist_ok=True)
    for target in re.findall(r"mkdir -p (\S+)", failing):
        (directory / target).mkdir(parents=True, exist_ok=True)
    # Bytes, not text: Path.write_text would translate to CRLF on Windows,
    # and ``tee eval-run.log\r`` writes a file with a carriage return in its
    # name — the log assertion would then read as "tee never ran".
    (directory / "step.sh").write_bytes(failing.encode("utf-8"))


def _run_step(directory: Path) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on this machine; the shell is what has to be asked")
    return subprocess.run(
        # ``bash -e`` mirrors the shell GitHub's Linux runner used: the
        # green job above is the measurement that it is NOT pipefail by
        # default.  The script name is relative so bash never has to parse
        # a Windows drive letter.
        [bash, "-e", "step.sh"],
        cwd=directory,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def test_r2_the_shipped_step_fails_when_the_evaluation_fails(
    tmp_path: Path,
) -> None:
    """Measured, not read: run the shipped script with a failing producer."""
    for name, script in _capture_scripts().items():
        case = tmp_path / name
        case.mkdir()
        _materialize_step(case, script)
        proc = _run_step(case)
        log = case / "eval-run.log"
        assert log.exists(), (
            f"{name}: the step aborted before its pipeline — tee never ran, "
            f"so this witness did not reach the subject (rc={proc.returncode})"
            f"\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
        assert proc.returncode != 0, (
            f"{name}: a failing evaluation reported success (rc=0). The "
            "pipeline carried tee's status, not the tool's — the shape that "
            "let CI run 41067550985 pass on 'Acceptance: INSUFFICIENT'. Start "
            f"the step with `set -o pipefail`.\n{proc.stdout[-2000:]}"
        )


def test_r3_without_the_guard_the_same_pipeline_reads_as_success(
    tmp_path: Path,
) -> None:
    """Reverse control: remove ONLY the arming line; the step must go green.

    If it stayed red, something else in the script (a prologue command, a
    missing file) would be failing the step and R2 could pass while the
    guard it names was absent — the arm has to be the load-bearing clause.
    """
    for name, script in _capture_scripts().items():
        stripped = (
            "\n".join(
                line
                for line in script.splitlines()
                if not _is_pipefail_arming(line)
            )
            + "\n"
        )
        if any(_is_pipefail_arming(line) for line in script.splitlines()):
            assert stripped != script, f"{name}: the control removed nothing"
        case = tmp_path / name
        case.mkdir()
        _materialize_step(case, stripped)
        proc = _run_step(case)
        assert (case / "eval-run.log").exists(), (
            f"{name}: the control aborted before its pipeline, so it is not "
            f"witnessing the swallow (rc={proc.returncode})"
            f"\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
        assert proc.returncode == 0, (
            f"{name}: without pipefail the pipeline still failed "
            f"(rc={proc.returncode}); the failure comes from somewhere other "
            "than the producer's status, so R2 would pass for the wrong "
            f"reason.\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )


def test_r4_the_census_reaches_every_workflow_that_writes_the_log() -> None:
    """The population comes from the files, not from a typed list."""
    writers = {
        path.name
        for path in WORKFLOWS.glob("*.yml")
        if "eval-run.log" in path.read_text(encoding="utf-8")
    }
    assert writers, "no workflow writes eval-run.log — the subject moved"
    captured = set(_capture_scripts())
    assert writers <= captured, (
        f"{sorted(writers - captured)} write eval-run.log but this gate does "
        "not reach their capture step"
    )
