"""W165: a terminal craft verdict has to name the check that produced it.

Why this exists (CI census, four runs read line by line):

  run 36459987681  test_craft_llm, test_craft_loop, test_craft_memory,
                   test_slow_marker_tagging x2
  run 36463431113  test_agent_runtime, test_craft_llm, test_craft_loop_metrics,
                   test_craft_verify, test_slow_marker_tagging x2
  run 36467013322  test_bench_mutation, test_swebench_llm_fixes,
                   test_swebench_v10_fixes, test_swebench_v11_fixes
  run 36473165360  test_craft_llm, test_craft_loop_jobs, test_craft_loop_metrics,
                   test_craft_verify, test_kind_threading

Same code, different names each run — and every red in the last three runs
reads `assert 'STUCK' == 'DONE'` (or an `IndexError: pop from empty list`, the
canned-response queue draining because the loop re-diagnosed). That is the
shape of a check that fails for a reason nobody can see: the loop's report said
only "同类错误连续 3 次 (签名: ...)", because `_check_criteria` builds a rich
evidence dict (check / exit_code / mode / output_tail) and the STUCK path throws
all of it away, keeping just the reason string. Nothing was logged either —
`craft/loop.py` had no logger at all — so a red unit test on CI showed four
"craft llm call" lines and no evidence, and the only way to learn which check
failed was to guess. (The 36463431113 `test_slow_marker_tagging` pair was a
different mechanism, already retired by the collect-only exemption; it is listed
here because reading those logs is what showed the two families apart.)

So this batch lands the diagnostic itself, and these cases pin that it is
attached to BOTH verdicts a non-green check can end a run with: STUCK (real
failure, 3 identical signatures) and unverifiable (the check never reached a
verdict). One helper feeds both, so the step's evidence in the report and the
log line cannot drift apart.

`observability/logging.py:format` renders only ts/level/logger/message, so the
facts have to be inside the message text — case
`test_the_json_formatter_drops_extra_so_the_message_must_carry_facts` pins that
premise, because if the formatter ever starts rendering `extra`, embedding the
facts twice becomes a thing to revisit rather than an accident.

No container and no nested pytest run: the pytest-shaped check is scripted at
the sandbox seam, so these cases behave the same on any host.
"""
from __future__ import annotations

import json
import logging
from ast import literal_eval
from pathlib import Path
from typing import Any

import pytest

import craft.executor as executor_module
import sandbox.runner as runner
from craft.editor import Editor
from craft.loop import CraftLoop
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from observability.logging import JsonFormatter
from sandbox.runner import SandboxResult

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

CALC = "def double(x):\n    return x / 2\n"
TEST_CALC = "def test_double():\n    assert double(3) == 6\n"

# A real failing run: non-zero, no sandbox-level error, and a pytest-shaped tail
# that should be readable in the terminal verdict.
REAL_FAILURE = SandboxResult(
    exit_code=1,
    stdout="F                                                                        [100%]\n"
    "FAILED test_calc.py::test_double - assert 1 == 6\n1 failed in 0.03s",
    stderr="",
    mode="local",
)

DEGRADED_RUN = SandboxResult(
    exit_code=2,
    stdout="python: can't open file '/work/test_calc.py': [Errno 2] No such file\n",
    stderr="",
    error="docker sandbox degraded to local_fallback: image pull failed",
    mode="local_fallback",
)


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    # Deliberately a no-op edit: the check keeps failing for a real reason, so
    # the loop collects three identical signatures and answers STUCK.
    return ["calc.py"]


def make_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: SandboxResult
) -> CraftLoop:
    for name, body in {"calc.py": CALC, "test_calc.py": TEST_CALC}.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    real = runner.run_sandboxed

    def fake(**kwargs: Any) -> SandboxResult:
        command = list(kwargs.get("command") or [])
        if any("pytest" in part for part in command):
            return result
        return real(**kwargs)

    monkeypatch.setattr(executor_module, "run_sandboxed", fake, raising=True)
    spec = parse_spec_text(FIX_SPEC)
    return CraftLoop(
        spec,
        compile_plan(spec),
        tmp_path,
        job_id="job-verdict-log",
        exec_mode="local",
        fix_registry={"test": fix_double},
    )


def failed_state(loop: CraftLoop) -> Any:
    """The one step that ended the run — named, not assumed by index."""
    candidates = [state for state in loop.states if state.status in ("failed", "stuck")]
    assert len(candidates) == 1, (
        f"exactly one step may end the run, got "
        f"{[(s.step.id, s.status) for s in loop.states]!r}"
    )
    return candidates[0]


def verdict_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "craft.loop" and "终态" in record.getMessage()
    ]


def test_a_stuck_verdict_logs_which_check_decided_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="craft.loop"):
        loop = make_loop(tmp_path, monkeypatch, REAL_FAILURE)
        report = loop.run()
    assert report["result"] == "STUCK", (
        f"this case exists to describe a STUCK run, got {report['result']!r} "
        f"with {[(s.step.id, s.status) for s in loop.states]!r}"
    )
    lines = verdict_lines(caplog)
    assert len(lines) == 1, f"one STUCK terminal, one log line, got {lines!r}"
    line = lines[0]
    state = failed_state(loop)
    # The line states its own claim: which step, which check, which plane,
    # which exit code, and what the check actually printed.
    for fact in (
        "STUCK",
        state.step.id,
        f"check={state.evidence['check']!r}",
        f"exit_code={state.evidence['exit_code']!r}",
        f"mode={state.evidence['mode']!r}",
        "assert 1 == 6",
    ):
        assert fact in line, f"{fact!r} missing from the verdict line: {line!r}"


def test_a_stuck_step_keeps_the_check_evidence_in_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other reader: whoever opens the job in the console reads the report,
    not the worker log, so the same facts must live on the stuck step."""
    loop = make_loop(tmp_path, monkeypatch, REAL_FAILURE)
    report = loop.run()
    assert report["result"] == "STUCK"
    state = failed_state(loop)
    for key in ("check", "exit_code", "mode", "output_tail", "reason"):
        assert key in state.evidence, (
            f"stuck step {state.step.id} evidence lost {key!r}: "
            f"{sorted(state.evidence)!r}"
        )
    assert state.evidence["terminal_verdict"] == "STUCK"
    assert "同类错误连续 3 次" in state.evidence["reason"]


def test_an_unverifiable_verdict_logs_its_check_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """W164's terminal gets the same treatment: it is also a non-green verdict
    a human has to be able to attribute without re-running anything."""
    with caplog.at_level(logging.WARNING, logger="craft.loop"):
        loop = make_loop(tmp_path, monkeypatch, DEGRADED_RUN)
        report = loop.run()
    assert report["result"] == "FAILED", (
        f"a degraded run must end unverifiable-FAILED, got {report['result']!r}"
    )
    lines = verdict_lines(caplog)
    assert len(lines) == 1, f"one terminal, one log line, got {lines!r}"
    line = lines[0]
    state = failed_state(loop)
    assert state.evidence.get("unverifiable") is True
    for fact in ("FAILED", f"check={state.evidence['check']!r}", DEGRADED_RUN.mode):
        assert fact in line, f"{fact!r} missing from the verdict line: {line!r}"
    assert "image pull failed" in line


def test_the_log_line_and_the_report_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One helper feeds both readers, so re-read the numbers out of the log line
    and require them to equal the step's evidence — a copy that drifts is the
    exact failure mode this file is about."""
    with caplog.at_level(logging.WARNING, logger="craft.loop"):
        loop = make_loop(tmp_path, monkeypatch, REAL_FAILURE)
        loop.run()
    [line] = verdict_lines(caplog)
    state = failed_state(loop)
    marker = "由这条检查决定: "
    assert marker in line, f"verdict line lost its own claim: {line!r}"
    facts = line.split(marker, 1)[1].split(" | output_tail=", 1)[0]
    quoted: dict[str, Any] = {}
    for part in facts.split():
        key = part.split("=", 1)[0]
        if key in {"check", "exit_code", "mode"}:
            # the line embeds Python reprs, not JSON
            quoted[key] = literal_eval(part.split("=", 1)[1])
    assert quoted == {
        key: state.evidence[key] for key in ("check", "exit_code", "mode")
    }, f"log line {quoted!r} vs evidence {state.evidence!r}"


def test_a_green_step_logs_no_terminal_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The line is about terminal verdicts, not about every check: a passing run
    must not print a '终态' claim it cannot support."""
    working = SandboxResult(exit_code=0, stdout="1 passed in 0.01s", stderr="", mode="local")
    with caplog.at_level(logging.WARNING, logger="craft.loop"):
        loop = make_loop(tmp_path, monkeypatch, working)
        report = loop.run()
    assert report["result"] == "DONE", (
        f"the scripted pass must let the loop finish, got {report['result']!r} "
        f"{[(s.step.id, s.status) for s in loop.states]!r}"
    )
    assert verdict_lines(caplog) == []


def test_both_terminals_are_wired_to_the_same_helper() -> None:
    """Reach guard: a future edit that drops one call site silently un-instruments
    one verdict, and no behavior case above would notice."""
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(CraftLoop)))
    callers: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and sub.func.attr == "_record_terminal_check"
            for sub in ast.walk(node)
        ):
            callers.add(node.name)
    assert callers == {"_run_step", "_fail_unverifiable"}, (
        f"_record_terminal_check must be called from both non-green terminals "
        f"(the 3x-STUCK branch inside _run_step, and _fail_unverifiable), got "
        f"{sorted(callers)!r}"
    )


def test_the_json_formatter_drops_extra_so_the_message_must_carry_facts() -> None:
    """Premise of the design: adding `extra=` would have rendered nothing."""
    record = logging.LogRecord(
        name="craft.loop",
        level=logging.WARNING,
        pathname="craft/loop.py",
        lineno=1,
        msg="craft 步骤 s4 的终态 STUCK",
        args=(),
        exc_info=None,
    )
    record.craft_check = {"check": "test_green", "exit_code": 1}
    rendered = json.loads(JsonFormatter().format(record))
    assert rendered["message"] == "craft 步骤 s4 的终态 STUCK"
    assert "craft_check" not in rendered, (
        "the formatter now renders `extra`; the facts embedded in the message "
        "text became a duplicate — pick one owner and update this case"
    )
