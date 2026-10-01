"""#142: the Craft loop's own step evidence has to carry the cache disclosure.

#7 made the sandbox say it (``SandboxResult.cache_note`` — a cache-mounting
profile always fills it in, including the un-armed case), #140 gave the DEEP
node's copy a reader in the archived HTML report, #141 gave the Craft *gate*
note a reader in the console. The loop itself was still the silent drop:
``_check_criteria`` builds the evidence dict that ends up on the step in
``report.json`` / the console, and it forwarded ``mode`` and ``output_tail``
while throwing the cache statement away. Same for ``_sandbox_unverifiable_evidence``
and for the ``#126 g`` terminal line, whose whole point is that a reader can see
what decided a STUCK verdict — a verdict reached inside a container that was
consuming an unverified dependency cache is exactly such a fact.

Honesty rule kept from #140/#141: an empty ``cache_note`` means "this profile
mounts no cache", never "the cache was verified", so the key rides only when the
sandbox actually said something — and every absence assertion here also binds its
carrier (``mode``), so "no key" cannot be the result of reading nothing.

Mutation arms, with the red set predicted BEFORE the witness ran (by which
branch the case walks, not by which words its name contains — #141's C2
MISMATCH was caused by exactly that shortcut):

  L1  drop ``**result.cache_disclosure`` from the compile dict
      -> ``test_compile_evidence_carries_the_cache_note`` (1)
  L2  drop it from the test_green dict
      -> ``test_test_green_evidence_carries_the_cache_note`` AND
         ``test_a_stuck_step_carries_the_cache_note_in_evidence_and_in_the_log``,
         because the check that ends that run IS the test_green check (2)
  L3  drop it from ``_sandbox_unverifiable_evidence``
      -> ``test_unverifiable_evidence_carries_the_cache_note`` (1)
  L4  ``ExecResult.cache_disclosure`` emits the key even when empty
      -> the two absence cases: the ``..._leaves_the_key_out_but_names_the_plane``
         one and the ``..._does_not_print_one`` one (2) —
         the first pins "no key means nothing was mounted", the second pins that
         a terminal must not print an empty cache claim
  L5  remove ``"cache_note"`` from the terminal facts tuple
      -> the log leg of ``test_a_stuck_step_carries_the_cache_note_in_evidence_and_in_the_log``
         only; the evidence key still rides (1)
  L6  ``cache_disclosure`` returns ``{}`` always (whole mechanism dead)
      -> the four disclosure cases (4); the two absence cases stay green, which is
         what makes them controls rather than dead weight
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

import craft.executor as executor_module
import sandbox.runner as runner
from craft.editor import Editor
from craft.executor import ExecResult
from craft.loop import CraftLoop, StepState
from craft.planner import Step, SuccessCriteria, compile_plan
from craft.spec import parse_spec_text
from sandbox.runner import SandboxResult

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

CALC = "def double(x):\n    return x / 2\n"
TEST_CALC = "def test_double():\n    assert double(3) == 6\n"

# The shipped un-armed wording (sandbox/runner.py): a cache volume exists, the
# caller passed no manifest. Asserted verbatim, so a paraphrase is a red.
CACHE_UNARMED = (
    "缓存完整性: 未校验 (NOT VERIFIED) —— profile PYTHON 挂了缓存卷 "
    "specproof-pip-cache, 调用方却没传 cache_dir+cache_manifest"
)

FAILING_WITH_CACHE = SandboxResult(
    exit_code=1,
    stdout=(
        "F                                                                 [100%]\n"
        "FAILED test_calc.py::test_double - assert 1 == 6\n1 failed in 0.03s"
    ),
    stderr="",
    mode="docker_sandbox",
    cache_note=CACHE_UNARMED,
)

FAILING_WITHOUT_CACHE = SandboxResult(
    exit_code=1,
    stdout=(
        "F                                                                 [100%]\n"
        "FAILED test_calc.py::test_double - assert 1 == 6\n1 failed in 0.03s"
    ),
    stderr="",
    mode="docker_sandbox",
    cache_note="",
)

PASSING_WITH_CACHE = SandboxResult(
    exit_code=0,
    stdout="1 passed in 0.03s",
    stderr="",
    mode="docker_sandbox",
    cache_note=CACHE_UNARMED,
)

PASSING_WITHOUT_CACHE = SandboxResult(
    exit_code=0,
    stdout="1 passed in 0.03s",
    stderr="",
    mode="docker_sandbox",
    cache_note="",
)

UNVERIFIABLE_RUN = ExecResult(
    command=["python", "-m", "pytest", "-q"],
    exit_code=-1,
    stdout="",
    stderr="",
    output_tail="[sandbox error] image pull failed",
    truncated=False,
    error="docker sandbox could not start: image pull failed",
    mode="local_fallback",
    cache_note=CACHE_UNARMED,
)


def noop_fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    # A no-op edit on purpose: the check keeps failing for a real reason, so the
    # loop collects three identical signatures and answers STUCK on this check.
    return ["calc.py"]


def make_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scripted: SandboxResult,
    *,
    job_id: str,
    script_fragment: str | None = "pytest",
) -> CraftLoop:
    for name, body in {"calc.py": CALC, "test_calc.py": TEST_CALC}.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    real = runner.run_sandboxed

    def fake(**kwargs: Any) -> SandboxResult:
        # Only the check this case is about is scripted; everything else really
        # runs, so the loop reaches its terminal for the reason being pinned.
        command = list(kwargs.get("command") or [])
        if script_fragment is None or any(script_fragment in part for part in command):
            return scripted
        return real(**kwargs)

    monkeypatch.setattr(executor_module, "run_sandboxed", fake, raising=True)
    spec = parse_spec_text(FIX_SPEC)
    return CraftLoop(
        spec,
        compile_plan(spec),
        tmp_path,
        job_id=job_id,
        exec_mode="local",
        fix_registry={"test": noop_fix},
    )


def compile_step() -> Step:
    return Step(
        id="s-cache-compile",
        kind="verify",
        target_files=["calc.py"],
        intent="compile the edited module",
        success_criteria=SuccessCriteria("compile"),
    )


def green_check_step() -> Step:
    return Step(
        id="s-cache-test",
        kind="test",
        target_files=["test_calc.py"],
        intent="run the acceptance test",
        success_criteria=SuccessCriteria("test_green"),
    )


def terminal_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "craft.loop" and "终态" in record.getMessage()
    ]


def stuck_state(loop: CraftLoop) -> StepState:
    candidates = [state for state in loop.states if state.status in ("failed", "stuck")]
    assert len(candidates) == 1, (
        f"exactly one step may end the run, got "
        f"{[(s.step.id, s.status) for s in loop.states]!r}"
    )
    return candidates[0]


def test_a_stuck_step_carries_the_cache_note_in_evidence_and_in_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The two readers of #126 g's terminal: the console report and the worker log."""
    with caplog.at_level(logging.WARNING, logger="craft.loop"):
        loop = make_loop(tmp_path, monkeypatch, FAILING_WITH_CACHE, job_id="job-cache-stuck")
        report = loop.run()
    assert report["result"] == "STUCK", f"this case describes a STUCK run, got {report['result']!r}"
    state = stuck_state(loop)
    assert state.evidence["cache_note"] == CACHE_UNARMED, (
        f"the stuck step's evidence dropped the sandbox's own cache statement: "
        f"{sorted(state.evidence)!r}"
    )
    lines = terminal_lines(caplog)
    assert len(lines) == 1, f"one terminal, one log line, got {lines!r}"
    assert CACHE_UNARMED in lines[0], f"log line does not quote the cache note: {lines[0]!r}"
    assert "cache_note=" in lines[0], f"log line does not name the field: {lines[0]!r}"


def test_compile_evidence_carries_the_cache_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop = make_loop(
        tmp_path,
        monkeypatch,
        PASSING_WITH_CACHE,
        job_id="job-cache-compile",
        script_fragment="compileall",
    )
    step = compile_step()
    ok, evidence, _result = loop._check_criteria(step, StepState(step=step))
    assert ok is True
    assert evidence["cache_note"] == CACHE_UNARMED, f"compile evidence: {sorted(evidence)!r}"


def test_test_green_evidence_carries_the_cache_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop = make_loop(tmp_path, monkeypatch, PASSING_WITH_CACHE, job_id="job-cache-green")
    step = green_check_step()
    ok, evidence, _result = loop._check_criteria(step, StepState(step=step))
    assert ok is True
    assert evidence["cache_note"] == CACHE_UNARMED, f"test_green evidence: {sorted(evidence)!r}"


def test_unverifiable_evidence_carries_the_cache_note(tmp_path: Path) -> None:
    """A run that never reached a verdict is the case that needs the plane most."""
    loop = CraftLoop(
        parse_spec_text(FIX_SPEC),
        compile_plan(parse_spec_text(FIX_SPEC)),
        tmp_path,
        job_id="job-cache-unverifiable",
        exec_mode="local",
    )
    evidence = loop._sandbox_unverifiable_evidence("test_green", UNVERIFIABLE_RUN)
    assert evidence["unverifiable"] is True
    assert evidence["cache_note"] == CACHE_UNARMED, (
        f"unverifiable evidence: {sorted(evidence)!r}"
    )


def test_a_run_that_mounted_no_cache_leaves_the_key_out_but_names_the_plane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absence must mean 'nothing was mounted', and must not be readable as 'the
    cache was fine' — so the same dicts still disclose the plane they came from."""
    loop = make_loop(
        tmp_path,
        monkeypatch,
        PASSING_WITHOUT_CACHE,
        job_id="job-cache-empty",
        script_fragment=None,
    )
    compile_ok, compile_evidence, _ = loop._check_criteria(
        compile_step(), StepState(step=compile_step())
    )
    green_ok, green_evidence, _ = loop._check_criteria(
        green_check_step(), StepState(step=green_check_step())
    )
    unverifiable = loop._sandbox_unverifiable_evidence(
        "test_green",
        ExecResult(
            command=["python", "-m", "pytest", "-q"],
            exit_code=-1,
            stdout="",
            stderr="",
            output_tail="[sandbox error] image pull failed",
            truncated=False,
            error="docker sandbox could not start: image pull failed",
            mode="local_fallback",
            cache_note="",
        ),
    )
    assert compile_ok is True and green_ok is True
    for name, evidence in (
        ("compile", compile_evidence),
        ("test_green", green_evidence),
        ("unverifiable", unverifiable),
    ):
        assert "cache_note" not in evidence, f"{name} invented a cache claim: {evidence!r}"
        assert evidence["mode"], f"{name} lost the plane that decides the claim: {sorted(evidence)}"


def test_a_terminal_without_a_disclosure_does_not_print_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="craft.loop"):
        loop = make_loop(
            tmp_path, monkeypatch, FAILING_WITHOUT_CACHE, job_id="job-cache-none"
        )
        report = loop.run()
    assert report["result"] == "STUCK"
    state = stuck_state(loop)
    assert "cache_note" not in state.evidence, f"{sorted(state.evidence)!r}"
    lines = terminal_lines(caplog)
    assert len(lines) == 1, f"one terminal, one log line, got {lines!r}"
    assert "cache_note" not in lines[0], f"log line invented a cache claim: {lines[0]!r}"
    assert "mode=" in lines[0], f"log line stopped naming the plane: {lines[0]!r}"
