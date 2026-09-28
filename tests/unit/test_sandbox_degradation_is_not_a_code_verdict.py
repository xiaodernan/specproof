"""W164: a check that never ran must not be reported as code that never works.

Real evidence (CI run 36465607221, job 109074800555, `tests-no-infra` on
Linux): 5 craft-loop unit tests asserted `report["result"] == "DONE"` and read
'STUCK', 2 more died inside their own canned-response queue with
`IndexError: pop from empty list`, and the SET of failing test names rotated
between runs (CI 36463431113 read 'STUCK' for a different four). A rotating red
over identical code is an environment coin-flip, not a regression.

The flip is `mode=auto`: `run_sandboxed` probes the docker daemon, and when
docker IS reachable but the sandbox image is not, it degrades to a host run of
the same command — whose paths are container-internal, so that run exits
non-zero while keeping `error="docker sandbox degraded to local_fallback:
..."`. `_check_criteria` judged only `exit_code`, so the loop treated the
degraded fallback as a failing check, collected the same error signature three
times and answered 'STUCK' — a verdict about the repository — for a problem
with the execution plane. When the `docker info` probe itself times out under
load, auto skips docker, the host run is clean, and the same test passes; that
is what made the red rotate instead of pinning.

The loop already has the right terminal for this: W114's `unverifiable`, which
fails the step immediately without entering the diagnose loop and without
counting repeated failures. These cases pin that a sandbox-level non-execution
reaches it — and, just as importantly, that a genuine test failure and a
degradation note on a run that DID produce a verdict do not.

Measured cost: the criterion under test is fed through the sandbox seam, so no
container and no nested pytest run; only the compile check executes for real.
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

import craft.executor as executor_module
import sandbox.runner as runner
from craft.editor import Editor
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from sandbox.runner import SandboxResult

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

CALC = "def double(x):\n    return x / 2\n"
TEST_CALC = "def test_double():\n    assert double(3) == 6\n"

DEGRADATION = (
    "docker sandbox degraded to local_fallback: sandbox image unavailable: pull failed"
)


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def scripted_pytest_result(result: SandboxResult) -> Any:
    """A sandbox layer that answers pytest-shaped commands with `result`.

    Only the command under scrutiny is scripted; everything else (the compile
    check that precedes it) delegates to the real local runner, so a case
    cannot reach its verdict by failing an unrelated earlier step. This is the
    seam where CI's plane actually differed, which keeps the simulation valid
    on any host.
    """
    real = runner.run_sandboxed

    def fake(**kwargs: Any) -> SandboxResult:
        command = list(kwargs.get("command") or [])
        if any("pytest" in part for part in command):
            return result
        return real(**kwargs)

    return fake


def make_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: SandboxResult) -> CraftLoop:
    write_repo = {"calc.py": CALC, "test_calc.py": TEST_CALC}
    for name, body in write_repo.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    monkeypatch.setattr(
        executor_module, "run_sandboxed", scripted_pytest_result(result), raising=True
    )
    spec = parse_spec_text(FIX_SPEC)
    return CraftLoop(
        spec,
        compile_plan(spec),
        tmp_path,
        job_id="job-degraded",
        exec_mode="local",
        fix_registry={"test": fix_double},
    )


def failed_state(loop: CraftLoop) -> Step:
    """The one step that ended the run — named, not assumed by index."""
    candidates = [state for state in loop.states if state.status in ("failed", "stuck")]
    assert len(candidates) == 1, (
        f"exactly one step may end the run, got "
        f"{[(s.step.id, s.status) for s in loop.states]!r}"
    )
    return candidates[0]


def test_a_degraded_run_that_never_ran_is_not_a_code_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI's shape: the fallback ran container paths, exited non-zero, kept the
    degradation note. The step must fail honestly, never become 'STUCK'."""
    loop = make_loop(
        tmp_path,
        monkeypatch,
        SandboxResult(
            exit_code=2,
            stdout="python: can't open file '/work/test_calc.py'",
            stderr="",
            error=DEGRADATION,
            mode="local_fallback",
        ),
    )
    report = loop.run()
    state = failed_state(loop)

    assert report["result"] == "FAILED", (
        "a check that never executed produced a verdict about the code; "
        f"result={report['result']!r} reason={state.evidence.get('reason')!r}"
    )
    assert state.evidence.get("unverifiable") is True, (
        f"the terminal must be the declared one, evidence={state.evidence!r}"
    )
    reason = str(state.evidence.get("reason", ""))
    assert "unverifiable" in reason, f"the reason must name its own claim: {reason!r}"
    assert DEGRADATION in reason, f"the reason must carry the plane's own error: {reason!r}"
    assert "同类错误连续" not in reason, (
        f"a degraded run must never count as a repeated identical failure: {reason!r}"
    )
    # The mechanism claimed: it stopped on the FIRST check of that step, so the
    # repair loop ran zero times rather than three.
    assert state.iterations == 0, (
        f"unverifiable must short-circuit before the repair loop, "
        f"iterations={state.iterations}"
    )


def test_a_real_test_failure_still_reaches_the_stuck_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control against over-widening: a verdict the plane genuinely produced
    (non-zero exit, no sandbox error) keeps the documented 3x rule."""
    loop = make_loop(
        tmp_path,
        monkeypatch,
        SandboxResult(
            exit_code=1,
            stdout="1 failed, 0 passed",
            stderr="",
            error="",
            mode="local",
        ),
    )
    report = loop.run()
    state = failed_state(loop)

    assert report["result"] == "STUCK", (
        f"the 3x same-signature rule must survive the new exemption, "
        f"result={report['result']!r} reason={state.evidence.get('reason')!r}"
    )
    assert "同类错误连续 3 次" in str(state.evidence.get("reason", "")), (
        f"the stuck verdict must state its own rule: {state.evidence!r}"
    )
    assert state.iterations == 3


def test_a_degraded_run_that_still_produced_a_verdict_is_believed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second control: the trigger is 'no verdict', not 'any degradation'.

    A local_fallback whose host command did run and passed (exit 0 with the
    degradation note recorded) is real evidence and must stay green — the
    exemption may not turn every documented degradation into a refusal.
    """
    loop = make_loop(
        tmp_path,
        monkeypatch,
        SandboxResult(
            exit_code=0,
            stdout="1 passed",
            stderr="",
            error=DEGRADATION,
            mode="local_fallback",
        ),
    )
    report = loop.run()

    assert report["result"] == "DONE", (
        f"a fallback run that produced a verdict is still evidence, "
        f"result={report['result']!r}"
    )


def test_the_auto_plane_really_hands_the_loop_that_result_shape() -> None:
    """Reach guard for the trigger, measured through the real `run_sandboxed`.

    Without this, 'error set + non-zero exit' could be a shape no deployment
    produces and the exemption would be a rule about nothing. Docker is faked at
    its two probes (daemon reachable, image missing) so the claim holds on any
    host: what rides back is the degradation AND the host run's own failure,
    because a container path cannot resolve locally.
    """
    seen: list[str] = []

    def fake_docker(
        command: list[str], workspace: str, timeout: int, profile: Any = None
    ) -> SandboxResult:
        seen.append("docker")
        return SandboxResult(
            exit_code=-1,
            stdout="",
            stderr="",
            error="sandbox image unavailable: pull failed",
            mode="docker",
        )

    original_available = runner._docker_available
    original_docker = runner._run_docker
    try:
        runner._docker_available = lambda: True
        runner._run_docker = fake_docker
        result = runner.run_sandboxed(
            command=["python", "/work/test_calc.py"],
            workspace=str(Path.cwd()),
            timeout=60,
            mode="auto",
            local_command=[sys.executable, "-c", "raise SystemExit(3)"],
        )
    finally:
        runner._docker_available = original_available
        runner._run_docker = original_docker

    assert seen == ["docker"], f"the auto branch must try the sandbox first: {seen!r}"
    assert result.mode == "local_fallback", f"mode={result.mode!r}"
    assert result.exit_code != 0, (
        f"the host cannot resolve a container path; the loop's trigger is only "
        f"reachable if the fallback keeps failing, exit={result.exit_code}"
    )
    assert "degraded to local_fallback" in result.error, (
        f"the degradation must ride on `error` for the loop to see it: "
        f"{result.error!r}"
    )


def test_the_exemption_is_fired_from_both_criteria_that_run_commands() -> None:
    """Wiring (not a substring): the two command-running criteria route to it.

    `compile` and `test_green` are the only places `_check_criteria` reads an
    ExecResult; a grep criterion executes nothing, so it must stay out of the
    rule.
    """
    import ast
    import inspect

    tree = ast.parse(textwrap.dedent(inspect.getsource(CraftLoop._check_criteria)))
    guarded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_sandbox_unverifiable_evidence"
    ]
    assert len(guarded) == 2, (
        f"compile + test_green must each route a non-executing check to the "
        f"unverifiable terminal, found {len(guarded)} call site(s)"
    )
    checks = {
        node.args[0].value
        for node in guarded
        if node.args and isinstance(node.args[0], ast.Constant)
    }
    assert checks == {"compile", "test_green"}, f"guarded criteria: {sorted(checks)}"
