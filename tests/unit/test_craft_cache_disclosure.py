"""#141: Craft's gate note is the console's copy of a cache disclosure.

`SandboxResult.cache_note` (#7) already travels to the DEEP node (#137) and into
the archived HTML report (#140). The other shipped caller of `run_sandboxed` is
`craft/executor.py`, and its `ExecResult` projection dropped the note: every
`mvn` the Craft loop runs consumes the seeded cache volume, yet the gate note
the console renders (`gate -> note -> api/agent_runtime.py -> SSE entry`) only
said `mode=...`. A reviewer could not tell a cache-poisoned build from a clean
one.

Ends pinned here: the sandbox -> ExecResult projection, the note text for BOTH
verdict branches (a pass and a fail have to carry it, or the disclosure only
appears when something already went wrong), and the per-gate dict the console
actually receives.

Witness arms (predicted before running, measured after):
  C1 executor stops forwarding the note      -> 1
  C2 passing-command note drops the suffix   -> 2, 5   (5 rides the same pass line)
  C3 failing-command note drops the suffix   -> 3
  C4 suffix invented when there is no note    -> 4
  C5 ExecResult loses the field entirely     -> 1, 2, 3, 4, 5

First run measured two MISMATCHes, both prediction-side, and one of them was a
hole in this file rather than in the product: C5 left case 4 green because
`_run_commands` catches executor exceptions and writes a 执行异常 note that
contains no 缓存 either — an absence-only assertion cannot tell "no cache to
disclose" from "the feature is gone". Case 4 now also requires `mode=` in the
note, which only a real ExecResult produces.
"""

from __future__ import annotations

from typing import Any

import craft.executor as craft_executor
from craft.executor import ExecResult, Executor
from craft.gates import _run_commands
from sandbox.runner import SandboxResult

NOT_VERIFIED = "缓存完整性 NOT VERIFIED: cache_dir 未提供"


class _StubRunner:
    """Minimal ExecRunner whose ExecResult shape comes from production."""

    def __init__(self, **overrides: Any) -> None:
        self.fields: dict[str, Any] = {
            "command": ["mvn", "-q", "package"],
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "output_tail": "BUILD SUCCESS",
            "truncated": False,
            "error": "",
            "mode": "docker_sandbox",
            "cache_note": NOT_VERIFIED,
        }
        self.fields.update(overrides)

    def run(self, command: list[str], *, timeout: int | None = None) -> ExecResult:
        return ExecResult(**self.fields)


class TestExecutorProjection:
    def test_1_sandbox_cache_note_survives_into_execresult(
        self, tmp_path, monkeypatch
    ) -> None:
        """The real Executor must carry the note out of run_sandboxed."""
        monkeypatch.setattr(
            craft_executor,
            "run_sandboxed",
            lambda **_kw: SandboxResult(
                exit_code=0,
                stdout="BUILD SUCCESS",
                stderr="",
                mode="docker_sandbox",
                cache_note=NOT_VERIFIED,
            ),
        )
        result = Executor(tmp_path, mode="local").run(["mvn", "-q", "package"])
        assert result.cache_note == NOT_VERIFIED


class TestGateNoteIsTheReader:
    def test_2_passing_command_discloses_the_cache(self) -> None:
        gate = _run_commands("build", [["mvn", "-q", "package"]], _StubRunner())
        assert NOT_VERIFIED in gate.note
        assert "缓存=" in gate.note
        assert gate.status == "passed"

    def test_3_failing_command_discloses_it_too(self) -> None:
        gate = _run_commands(
            "build",
            [["mvn", "-q", "package"]],
            _StubRunner(exit_code=1, output_tail="BUILD FAILURE"),
        )
        assert NOT_VERIFIED in gate.note
        assert "缓存=" in gate.note
        assert gate.status == "failed"

    def test_4_no_note_writes_no_claim(self) -> None:
        """Empty note = this profile mounts no cache; the note must say nothing
        about caching rather than implying the cache was checked.

        The run must be provably the run under test: `_run_commands` swallows
        any executor exception into a 执行异常 note, and such a note contains no
        缓存 either — so asserting only the absence would stay green when the
        whole feature is gone. `mode=` is the witness that a real ExecResult
        reached the note builder.
        """
        gate = _run_commands("build", [["mvn", "-q", "package"]], _StubRunner(cache_note=""))
        assert "mode=docker_sandbox" in gate.note
        assert "缓存" not in gate.note
        assert gate.status == "passed"

    def test_5_the_console_payload_carries_it(self) -> None:
        """api/agent_runtime forwards entry dicts; the disclosure must already
        be inside the payload, not only in the local GateResult object."""
        payload = _run_commands(
            "build", [["mvn", "-q", "package"]], _StubRunner()
        ).to_dict()
        assert NOT_VERIFIED in payload["note"]
        assert "缓存=" in payload["note"]
