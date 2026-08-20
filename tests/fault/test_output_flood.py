"""Backlog #7 攻击测试 2: 输出洪水 (数百 MB 级, 可配置模拟大小).

Threat: a malicious build/test floods stdout/stderr with hundreds of MB,
aiming to OOM the worker or bury real evidence. The sandbox runner must
bound retained output to head + explicit truncation marker + tail, drop
the middle, and report truncated/truncated_chars honestly, so downstream
consumers (executor, tool layer, evidence writers) never hold the flood.

Memory control (as required): the flood size is configurable via
SPECPROOF_FAULT_FLOOD_BYTES (default 2 MiB for the gate). Raising it to
hundreds of MB exercises the identical code path with identical
assertions — the retained size is fixed by SPECPROOF_SANDBOX_OUTPUT_HEAD/
TAIL and stays constant regardless of flood size. The child writes the
flood in 4 KiB chunks (constant child memory); no test materializes the
full flood itself.

Annotated gap (capture): the runner still buffers the whole stream via
subprocess.run(capture_output=True) BEFORE retention truncation, so peak
process memory scales with the flood size. Bounded RETENTION is enforced
and proven here; bounded peak CAPTURE (streaming read) is the documented
follow-up — see docs/operations/THREAT_TESTING.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

import sandbox.runner as runner
from craft.executor import Executor
from sandbox.runner import run_sandboxed

FLOOD_BYTES_DEFAULT = 2 * 1024 * 1024
HEAD = 1000  # test-time retention budget (via SPECPROOF_SANDBOX_OUTPUT_HEAD)
TAIL = 2000  # test-time retention budget (via SPECPROOF_SANDBOX_OUTPUT_TAIL)

# The flood child: writes 'HEAD' + n*'F' + 'TAIL' to stdout and
# 'ERRHEAD' + m*'E' + 'ERRTAIL' to stderr, in constant-memory chunks.
_FLOOD_SCRIPT = (
    "import sys\n"
    "n = int(sys.argv[1]); m = int(sys.argv[2])\n"
    "sys.stdout.write('HEAD')\n"
    "rem = n\n"
    "while rem > 0:\n"
    "    k = min(rem, 4096)\n"
    "    sys.stdout.write('F' * k)\n"
    "    rem -= k\n"
    "sys.stdout.write('TAIL')\n"
    "sys.stdout.flush()\n"
    "sys.stderr.write('ERRHEAD')\n"
    "rem = m\n"
    "while rem > 0:\n"
    "    k = min(rem, 4096)\n"
    "    sys.stderr.write('E' * k)\n"
    "    rem -= k\n"
    "sys.stderr.write('ERRTAIL')\n"
    "sys.stderr.flush()\n"
)


def _flood_bytes() -> int:
    raw = os.getenv("SPECPROOF_FAULT_FLOOD_BYTES", "").strip()
    if raw:
        try:
            return max(int(raw), 64)
        except ValueError:
            return FLOOD_BYTES_DEFAULT
    return FLOOD_BYTES_DEFAULT


def _flood_command(n: int, m: int) -> list[str]:
    return ["python", "-u", "-c", _FLOOD_SCRIPT, str(n), str(m)]


def _set_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_SANDBOX_OUTPUT_HEAD", str(HEAD))
    monkeypatch.setenv("SPECPROOF_SANDBOX_OUTPUT_TAIL", str(TAIL))


def _expected_stdout(n: int) -> str:
    """head + marker + tail of the flood child's stdout, without building it."""
    dropped = n + 8 - HEAD - TAIL
    marker = runner.truncation_marker(dropped)
    return "HEAD" + "F" * (HEAD - 4) + marker + "F" * (TAIL - 4) + "TAIL"


def _expected_stderr(m: int) -> str:
    dropped = m + 14 - HEAD - TAIL
    marker = runner.truncation_marker(dropped)
    return "ERRHEAD" + "E" * (HEAD - 7) + marker + "E" * (TAIL - 7) + "ERRTAIL"


# ══════════════════════════════════════════════════════════════════
# 单元边界: bound_output 的 head/marker/tail 语义
# ══════════════════════════════════════════════════════════════════

class TestBoundOutputSemantics:
    def test_under_limit_unchanged(self) -> None:
        text = "x" * 19
        assert runner.bound_output(text, head=10, tail=10) == (text, False, 0)

    def test_exactly_at_limit_unchanged(self) -> None:
        text = "x" * 20
        assert runner.bound_output(text, head=10, tail=10) == (text, False, 0)

    def test_one_over_limit_keeps_head_marker_tail(self) -> None:
        text = "a" * 10 + "M" * 2 + "b" * 10
        bounded, truncated, dropped = runner.bound_output(text, head=10, tail=10)
        assert truncated is True
        assert dropped == 2
        assert bounded == "a" * 10 + runner.truncation_marker(2) + "b" * 10
        assert "2 chars omitted" in bounded


# ══════════════════════════════════════════════════════════════════
# 真实本地洪水: 头部+标记+尾部保留, 中段丢弃, 保留量恒定
# ══════════════════════════════════════════════════════════════════

class TestOutputFloodBoundedRetention:
    def test_real_flood_keeps_head_marker_tail_bounded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_budgets(monkeypatch)
        n = _flood_bytes()
        m = max(n // 2, 4096)
        result = run_sandboxed(
            _flood_command(n, m), str(tmp_path), timeout=300, mode="local"
        )
        assert result.exit_code == 0
        assert result.error == ""
        assert result.mode == "local"
        assert result.truncated is True
        assert result.truncated_chars == (n + 8 - HEAD - TAIL) + (m + 14 - HEAD - TAIL)
        assert result.stdout == _expected_stdout(n)
        assert result.stderr == _expected_stderr(m)
        assert len(result.stdout) < 100_000, "retained size must not grow with the flood"
        assert str(n + 8 - HEAD - TAIL) + " chars omitted" in result.stdout
        assert result.stdout.count("F") == HEAD - 4 + TAIL - 4, "middle must be dropped"

    def test_small_output_under_budget_not_truncated_no_marker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_budgets(monkeypatch)
        n, m = 100, 50
        result = run_sandboxed(
            _flood_command(n, m), str(tmp_path), timeout=300, mode="local"
        )
        assert result.exit_code == 0
        assert result.truncated is False
        assert result.truncated_chars == 0
        assert result.stdout == "HEAD" + "F" * n + "TAIL"
        assert result.stderr == "ERRHEAD" + "E" * m + "ERRTAIL"
        assert "chars omitted" not in result.stdout

    def test_timeout_flood_preserves_bounded_partial_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_budgets(monkeypatch)
        n, m = 200_000, 100_000
        script = _FLOOD_SCRIPT + "import time\nsys.stdout.flush()\ntime.sleep(60)\n"
        result = run_sandboxed(
            ["python", "-u", "-c", script, str(n), str(m)],
            str(tmp_path),
            timeout=3,
            mode="local",
        )
        assert result.exit_code == -1
        assert "timed out" in result.error
        assert result.truncated is True
        assert result.stdout == _expected_stdout(n)
        assert result.stderr == _expected_stderr(m)

    def test_docker_path_bounds_flood_from_captured_proc(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The docker branch applies the same retention bound (fake proc —
        no docker needed)."""
        flood_stdout = "HEAD" + "F" * 500_000 + "TAIL"

        class _FloodProc:
            returncode = 0
            stdout = flood_stdout
            stderr = ""

        def fake_run(cmd: list[str], **kwargs: Any) -> _FloodProc:
            return _FloodProc()

        monkeypatch.setattr(runner.subprocess, "run", fake_run)
        monkeypatch.setattr(runner, "_image_ready", lambda _image: True)
        monkeypatch.setattr(runner, "_ensure_writable_target", lambda _ws: "")
        monkeypatch.setenv("SPECPROOF_SANDBOX_OUTPUT_HEAD", str(HEAD))
        monkeypatch.setenv("SPECPROOF_SANDBOX_OUTPUT_TAIL", str(TAIL))
        result = run_sandboxed(["mvn", "-o", "test"], str(tmp_path / "ws"), mode="docker")
        assert result.mode == "docker"
        assert result.truncated is True
        assert result.truncated_chars == 500_000 + 8 - HEAD - TAIL
        assert result.stdout == _expected_stdout(500_000)

    def test_executor_downstream_sees_bounded_marked_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _set_budgets(monkeypatch)
        n, m = _flood_bytes(), _flood_bytes() // 2
        exec_result = Executor(tmp_path, mode="local", timeout=300).run(
            _flood_command(n, m)
        )
        assert exec_result.exit_code == 0
        assert exec_result.mode == "local"
        assert exec_result.truncated is True
        assert len(exec_result.stdout) == len(_expected_stdout(n))
        assert exec_result.stdout.count("F") == HEAD - 4 + TAIL - 4
        assert exec_result.output_tail.endswith("ERRTAIL")
        assert "chars omitted" in exec_result.stdout

    def test_flood_size_configurable_for_manual_multi_hundred_mb_runs(self) -> None:
        """The knob exists and is honoured; the gate run keeps the default.

        A manual run can prove the identical assertions at hundreds of MB:
        SPECPROOF_FAULT_FLOOD_BYTES=268435456 python -m pytest
        tests/fault/test_output_flood.py -q
        (see docs/operations/THREAT_TESTING.md for the measured run)."""
        assert _flood_bytes() >= 64
