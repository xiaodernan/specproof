"""#536 — a reused Head run must carry the error it failed with.

Measured on CI (run 41067550985, `eval-golden-cases`, case-12-add-javadoc):
the case read ``Generated test executed no tests (base tests: 1, head tests:
0; exit codes base 0, head -1)`` while ``head_output`` was empty. A fresh
``_run_generated_test`` cannot produce that shape — every sandbox failure
path sets ``error`` (``sandbox/runner.py`` exit -1 -> "Sandbox execution
failed: ..."), and an error would route to the "Maven execution error"
branch. The run that produced ``exit -1`` was the one recorded during
generation, and ``record.head_run`` kept only exit code, counts, compile
flag, stdout and stderr: the error was dropped at the producer, and the
consumer hard-coded ``"error": ""`` when reusing it. The zero-tests guard
then explained a sandbox failure with the one message that was not true.

Both ends are pinned here, plus the two reverse controls that keep the fix
from rewriting every reused run:

  1. the producer records the sandbox error on ``head_run`` (and records an
     empty error for a healthy run — the key's shape does not depend on
     the outcome);
  2. the consumer surfaces a recorded error through the execution-error
     branch, so the entry names the sandbox failure instead of the
     zero-tests message;
  3. a reused run with no recorded error still reads as "executed no
     tests" — the pre-#536 message stays for the situation it describes;
  4. a recorded compile error keeps its explicit precedence.

The consumer witnesses reuse itself: the stubbed run table has no
``maven_head`` key, so an attempt to invoke Maven on Head raises KeyError.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

import agent.nodes.generate_counterexamples as gen_module
from agent.nodes.generate_counterexamples import generate_counterexamples_node
from observability.metrics import snapshot

_SANDBOX_ERROR = (
    "Sandbox execution failed: docker run exited -1: "
    "failed to create shim task: no space left on device"
)


def _counter(name: str) -> float:
    return snapshot()["counters"].get(name, 0.0)


def _result(
    exit_code: int,
    tests: int,
    *,
    failures: int = 0,
    stdout: str = "",
) -> dict[str, Any]:
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": "",
        "test_counts": {
            "tests": tests, "failures": failures, "errors": 0, "skipped": 0,
        },
        "error": "",
    }


def _stub_execution(
    monkeypatch: pytest.MonkeyPatch, results: dict[str, Any]
) -> None:
    def fake(job_id: object, stage: str, fn: object, *args: object, **kwargs: object) -> Any:  # noqa: ARG001
        return results[stage]

    monkeypatch.setattr(
        "agent.nodes.run_differential.run_with_cancel_checks", fake
    )


def _state_with_recorded_head(
    tmp_path: Path,
    *,
    recorded_error: str,
    exit_code: int = -1,
    tests: int = 0,
    compile_error: bool = False,
) -> dict[str, Any]:
    base_ws = tmp_path / "base"
    head_ws = tmp_path / "head"
    base_ws.mkdir()
    head_ws.mkdir()
    gen = tmp_path / "SpecProofGeneratedTest.java"
    gen.write_text("class SpecProofGeneratedTest {}\n", encoding="utf-8")
    record_sha = hashlib.sha256(gen.read_bytes()).hexdigest()
    return {
        "repo_path": "",
        "app_dir": "",
        "base_workspace": str(base_ws),
        "head_workspace": str(head_ws),
        "generated_tests_path": str(gen),
        "contracts": [{"id": "UNIQUE-01"}],
        "generation_record": {
            "test_file_sha256": record_sha,
            "head_run": {
                "exit_code": exit_code,
                "test_counts": {"tests": tests},
                "compile_error": compile_error,
                "error": recorded_error,
                "stdout": "",
                "stderr": "",
            },
        },
    }


# ── 1. the producer ─────────────────────────────────────────────────────────


def _producer_state(workspace: str) -> dict[str, Any]:
    return {
        "head_workspace": workspace,
        "app_dir": "",
        "static_findings": [],
        "confirmed_findings": [],
        "contracts": [],
        "requirement_text": "unauthenticated email change must be rejected",
        "use_llm": False,
    }


def test_the_producer_records_the_head_runs_sandbox_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><groupId>com.specproof</groupId></project>", encoding="utf-8"
    )

    def failed_head_run(workspace: str, class_name: str) -> dict[str, Any]:
        return {
            "exit_code": -1,
            "test_counts": {},
            "error": _SANDBOX_ERROR,
            "stdout": "",
            "stderr": "",
        }

    monkeypatch.setattr(
        "agent.nodes.run_differential._run_generated_test", failed_head_run
    )
    monkeypatch.setattr(gen_module, "_get_provider", lambda: None)

    out = generate_counterexamples_node(_producer_state(str(tmp_path)))  # type: ignore[arg-type]

    head_run = out["generation_record"]["head_run"]
    assert head_run["error"] == _SANDBOX_ERROR, (
        "the producer must keep the sandbox error; dropping it leaves the "
        "reused run with exit -1 and no witness for why"
    )
    assert head_run["exit_code"] == -1
    assert head_run["compile_error"] is False


def test_the_producer_records_an_empty_error_for_a_healthy_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    (tmp_path / "pom.xml").write_text(
        "<project><groupId>com.specproof</groupId></project>", encoding="utf-8"
    )

    def healthy_head_run(workspace: str, class_name: str) -> dict[str, Any]:
        return {
            "exit_code": 0,
            "test_counts": {"tests": 1},
            "error": "",
            "stdout": "BUILD SUCCESS",
            "stderr": "",
        }

    monkeypatch.setattr(
        "agent.nodes.run_differential._run_generated_test", healthy_head_run
    )
    monkeypatch.setattr(gen_module, "_get_provider", lambda: None)

    out = generate_counterexamples_node(_producer_state(str(tmp_path)))  # type: ignore[arg-type]

    head_run = out["generation_record"]["head_run"]
    assert head_run["error"] == ""
    assert head_run["exit_code"] == 0


# ── 2. the consumer ─────────────────────────────────────────────────────────


def test_a_reused_head_run_surfaces_its_recorded_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from agent.nodes.run_differential import run_differential_node

    before_errors = _counter("differential_errors_total")
    _stub_execution(monkeypatch, {
        "maven_base": _result(0, 1),
        "maven_probe": [],
    })
    state = _state_with_recorded_head(
        tmp_path, recorded_error=_SANDBOX_ERROR
    )

    out = run_differential_node(state)  # type: ignore[arg-type]

    entry = out["diff_results"][0]
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "Maven execution error" in entry["detail"]
    assert _SANDBOX_ERROR in entry["detail"], (
        "the entry must name the sandbox failure recorded with the run"
    )
    assert "executed no tests" not in entry["detail"], (
        "a sandbox failure is not a zero-test comparison; the old message "
        "blamed the toolchain for not running a test it never got to try"
    )
    assert entry["head_exit_code"] == -1
    assert _counter("differential_errors_total") == before_errors + 1
    assert [r["result"] for r in out["contract_results"]] == ["UNVERIFIED"]
    assert _SANDBOX_ERROR in out["contract_results"][0]["details"]


def test_a_reused_silent_run_still_reads_as_executed_no_tests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Reverse control: the zero-tests message stays for the situation it
    describes — a run that exited without an error and without executing."""
    from agent.nodes.run_differential import run_differential_node

    _stub_execution(monkeypatch, {
        "maven_base": _result(0, 1),
        "maven_probe": [],
    })
    state = _state_with_recorded_head(
        tmp_path, recorded_error="", exit_code=0, tests=0
    )

    out = run_differential_node(state)  # type: ignore[arg-type]

    entry = out["diff_results"][0]
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "executed no tests" in entry["detail"]
    assert "head tests: 0" in entry["detail"]
    assert "Maven execution error" not in entry["detail"]


def test_a_recorded_compile_error_keeps_its_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from agent.nodes.run_differential import run_differential_node

    _stub_execution(monkeypatch, {
        "maven_base": _result(0, 1),
        "maven_probe": [],
    })
    state = _state_with_recorded_head(
        tmp_path, recorded_error="", exit_code=1, compile_error=True
    )

    out = run_differential_node(state)  # type: ignore[arg-type]

    entry = out["diff_results"][0]
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "failed to compile on Head" in entry["detail"]
