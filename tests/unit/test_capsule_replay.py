"""Capsule replay execution tests (#183) — sandbox-only, honest counters.

No Docker, no network: run_sandboxed and _clone_repo are monkeypatched at
the evidence.capsule_replay seam. Covers:

- the counter family: runs / exec_errors / timeouts / verdict_<word>
  (delta assertions — the registry is process-global);
- the honest absence rules: unparsable stdout and a non-zero exit count no
  verdict bucket; a clone failure never reaches the sandbox (counts no run);
- the replay profile and mode="docker" ride along so the sandbox stays the
  only execution plane for untrusted capsule code;
- the verdict vocabulary tracks the create_capsule template (drift gate);
- CLI wiring: --run executes and reports honestly; no --run keeps the
  legacy "extracted" behavior byte-for-byte.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from evidence.capsule_replay import VERDICTS, run_capsule_replay
from observability.metrics import snapshot


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


@dataclass
class FakeResult:
    """SandboxResult's replay-relevant surface (no Docker imports needed)."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    mode: str = "docker"
    cache_note: str = ""


class SandboxStub:
    def __init__(self) -> None:
        self.result = FakeResult()
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, command: list[str], workspace: str, timeout: int,
        mode: str, profile: Any,
    ) -> FakeResult:
        self.calls.append({
            "command": list(command),
            "workspace": workspace,
            "timeout": timeout,
            "mode": mode,
            "profile": profile,
        })
        return self.result


@pytest.fixture()
def sandbox(monkeypatch: pytest.MonkeyPatch) -> SandboxStub:
    """Stub the sandbox seam AND the host clone; record the call shape."""
    stub = SandboxStub()

    def fake_clone(repo: Path, work_dir: Path) -> tuple[bool, str]:
        repo_dir = work_dir / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git").mkdir(exist_ok=True)
        return True, ""

    monkeypatch.setattr("evidence.capsule_replay._clone_repo", fake_clone)
    monkeypatch.setattr("evidence.capsule_replay.run_sandboxed", stub)
    return stub


# ── the counter family ─────────────────────────────────────────────────────


def test_successful_replay_counts_run_and_parsed_verdict(
    sandbox: SandboxStub, tmp_path: Path,
) -> None:
    sandbox.result = FakeResult(stdout="... >> REGRESSION CONFIRMED <<\n", exit_code=0)
    before = (
        _counter("capsule_replay_runs_total"),
        _counter("capsule_replay_verdict_regression_confirmed_total"),
        _counter("capsule_replay_exec_errors_total"),
        _counter("capsule_replay_timeouts_total"),
    )

    result = run_capsule_replay(tmp_path, Path("some/repo"))

    after = (
        _counter("capsule_replay_runs_total"),
        _counter("capsule_replay_verdict_regression_confirmed_total"),
        _counter("capsule_replay_exec_errors_total"),
        _counter("capsule_replay_timeouts_total"),
    )
    assert after == (before[0] + 1, before[1] + 1, before[2], before[3])
    assert result["status"] == "replayed"
    assert result["verdict"] == "regression_confirmed"
    assert result["error"] == ""
    assert result["exit_code"] == 0
    assert "replayed_at" in result
    # The sandbox is the only execution plane, and the replay profile —
    # not the default — rides along.
    call = sandbox.calls[0]
    assert call["command"] == ["bash", "run.sh", "repo"]
    assert call["mode"] == "docker"
    assert call["profile"].name == "replay"
    assert call["workspace"] == str(tmp_path)


def test_compliant_stdout_counts_compliant_family(
    sandbox: SandboxStub, tmp_path: Path,
) -> None:
    sandbox.result = FakeResult(stdout=">> COMPLIANT <<")
    before = _counter("capsule_replay_verdict_compliant_total")

    result = run_capsule_replay(tmp_path, Path("r"))

    assert result["verdict"] == "compliant"
    assert _counter("capsule_replay_verdict_compliant_total") == before + 1


def test_timeout_counts_run_failure_and_timeout(
    sandbox: SandboxStub, tmp_path: Path,
) -> None:
    sandbox.result = FakeResult(
        error="sandbox execution timed out after 900s", exit_code=124,
    )
    before = (
        _counter("capsule_replay_runs_total"),
        _counter("capsule_replay_exec_errors_total"),
        _counter("capsule_replay_timeouts_total"),
        _counter("capsule_replay_verdict_regression_confirmed_total"),
    )

    result = run_capsule_replay(tmp_path, Path("r"))

    assert (
        _counter("capsule_replay_runs_total"),
        _counter("capsule_replay_exec_errors_total"),
        _counter("capsule_replay_timeouts_total"),
    ) == (before[0] + 1, before[1] + 1, before[2] + 1)
    # A timed-out run completed nothing — no verdict is parsed or counted.
    assert _counter("capsule_replay_verdict_regression_confirmed_total") == before[3]
    assert result["verdict"] is None


def test_spawn_error_counts_failure_but_not_timeout(
    sandbox: SandboxStub, tmp_path: Path,
) -> None:
    sandbox.result = FakeResult(error="docker daemon unreachable", exit_code=255)
    before = (
        _counter("capsule_replay_exec_errors_total"),
        _counter("capsule_replay_timeouts_total"),
    )

    run_capsule_replay(tmp_path, Path("r"))

    assert (
        _counter("capsule_replay_exec_errors_total"),
        _counter("capsule_replay_timeouts_total"),
    ) == (before[0] + 1, before[1])


def test_unparsable_stdout_counts_no_verdict_bucket(
    sandbox: SandboxStub, tmp_path: Path,
) -> None:
    """Honest absence: exit 0 with marker-less output counts no verdict."""
    sandbox.result = FakeResult(stdout="all good, trust me", exit_code=0)
    words = sorted(set(VERDICTS.values()))
    before = tuple(_counter(f"capsule_replay_verdict_{word}_total") for word in words)

    result = run_capsule_replay(tmp_path, Path("r"))

    after = tuple(_counter(f"capsule_replay_verdict_{word}_total") for word in words)
    assert after == before
    assert result["verdict"] is None


def test_nonzero_exit_counts_no_verdict_bucket(
    sandbox: SandboxStub, tmp_path: Path,
) -> None:
    """A marker on stdout means nothing when the run did not complete."""
    sandbox.result = FakeResult(stdout=">> REGRESSION CONFIRMED <<", exit_code=1)
    before = _counter("capsule_replay_verdict_regression_confirmed_total")

    result = run_capsule_replay(tmp_path, Path("r"))

    assert _counter("capsule_replay_verdict_regression_confirmed_total") == before
    assert result["verdict"] is None


# ── host/sandbox boundary ──────────────────────────────────────────────────


def test_clone_failure_never_reaches_the_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_clone(repo: Path, work_dir: Path) -> tuple[bool, str]:
        return False, "git clone failed: not a repository"

    monkeypatch.setattr("evidence.capsule_replay._clone_repo", failing_clone)
    before = (
        _counter("capsule_replay_runs_total"),
        _counter("capsule_replay_exec_errors_total"),
    )

    result = run_capsule_replay(tmp_path, Path("nowhere"))

    assert result["status"] == "clone_failed"
    assert "not a repository" in result["error"]
    assert (
        _counter("capsule_replay_runs_total"),
        _counter("capsule_replay_exec_errors_total"),
    ) == before


def test_verdict_vocabulary_tracks_the_replay_template() -> None:
    """The table and the create_capsule template must move together."""
    from agent.nodes.create_capsule import _build_sh_script

    script = _build_sh_script(
        "F-1", "MAJOR", "C-1", "drift probe", "http", "capsule-F-1",
    )
    for marker in VERDICTS:
        assert marker in script, f"template lost the {marker!r} marker"


# ── CLI wiring ─────────────────────────────────────────────────────────────


def _capsule_zip(path: Path) -> Path:
    manifest = {"finding_id": "F-9", "severity": "MAJOR", "contract_id": "C-1"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("run.sh", "#!/bin/bash\necho '>> REGRESSION CONFIRMED <<'\n")
    return path


def test_replay_command_run_flag_executes_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cli.specproof.commands.replay import replay

    captured: dict[str, Any] = {}

    def fake_run(work_dir: Path, repo: Path, timeout: int = 900) -> dict[str, Any]:
        captured.update({"work_dir": work_dir, "repo": repo, "timeout": timeout})
        return {
            "status": "replayed",
            "exit_code": 0,
            "stdout_tail": ">> REGRESSION CONFIRMED <<",
            "stderr_tail": "",
            "mode": "docker",
            "error": "",
            "verdict": "regression_confirmed",
            "repo": str(repo),
            "replayed_at": "2026-10-06T00:00:00+00:00",
        }

    monkeypatch.setattr("evidence.capsule_replay.run_capsule_replay", fake_run)

    repo_dir = tmp_path / "target-repo"
    repo_dir.mkdir()
    out_dir = tmp_path / "out"
    result = CliRunner().invoke(
        replay,
        [
            str(_capsule_zip(tmp_path / "capsule.zip")),
            "--run", str(repo_dir),
            "--output-dir", str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["repo"] == repo_dir
    assert captured["timeout"] == 900
    report = json.loads((out_dir / "replay-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "replayed"
    assert report["verdict"] == "regression_confirmed"
    assert report["exit_code"] == 0
    assert "Status: replayed" in result.output
    assert "Verdict: regression_confirmed" in result.output


def test_replay_command_without_run_flag_keeps_extracted_status(tmp_path: Path) -> None:
    """Regression lock: the legacy extract-only behavior is unchanged."""
    from cli.specproof.commands.replay import replay

    out_dir = tmp_path / "out"
    result = CliRunner().invoke(
        replay,
        [str(_capsule_zip(tmp_path / "capsule.zip")), "--output-dir", str(out_dir)],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((out_dir / "replay-report.json").read_text(encoding="utf-8"))
    assert report["status"] == "extracted"
    assert "verdict" not in report
    assert "To execute replay" in result.output
