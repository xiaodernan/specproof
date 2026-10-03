"""#153 — the CLI exit code answers the verdict, and MCP keeps the summary.

Before this batch `specproof verify` exited 0 for VERIFIED and FAILED alike
(the only non-zero exits were three setup failures, indistinguishable from a
BLOCKED verdict's channel), and `mcp/tools.py` raised ToolError on ANY
non-zero exit — discarding the parsed BLOCKED summary with its BLOCKER
findings, the very thing the caller asked for. The exit code is the last
outlet of the verdict (#151 gave it to the certificate, #150 to the report,
#154 to the job row): 0 = VERIFIED, 1 = BLOCKED, 2 = no verdict was reached
(FAILED / preflight not ready / bad paths / an unknown word — fail-closed).

The three setup exits move from 1 to 2, because "1" must always mean a real
verdict refused the change, never "the tool could not run".

Witness plan (arms in .scratch/g153/mutate_153.py, predictions written here
BEFORE the first run; test numbers are the order below):

* E1 `exit_code_for` maps BLOCKED/FAILED to 0 (the constant forgets refusal)
  ⇒ {1,5,6} red — the mapping test plus the two non-zero command legs;
  4 stays green (VERIFIED→0 is untouched by this arm), 2/3 are setup-legs
  that never call the mapping, 7/8/9 are MCP-side.
* E2 the final `raise SystemExit(exit_code_for(verdict))` is deleted ⇒
  {5,6} red (the command then exits 0 regardless of the verdict) — 4 is the
  all-legs-green对照 that cannot see it, 1/2/3 never reach the tail, 7/8/9
  never run the command.
* E3 the MCP "verdict keeps the summary" branch is deleted (non-zero ⇒
  ToolError again) ⇒ {7} red; 8 stays green (it pins the no-verdict
  ToolError) and 9 stays green (exit 0 never entered the branch).
* E4 the missing-repo setup exit flips back to 1 ⇒ {2} red; the spec leg
  (3) has its own site and stays green — each site gets its own arm.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import mcp.tools as mcp_tools
from cli.specproof.commands.verify import exit_code_for, verify
from mcp.tools import ToolError, call_tool

# ── pure mapping ────────────────────────────────────────────────────────────


def test_exit_code_mapping_is_fail_closed():
    assert exit_code_for("VERIFIED") == 0
    assert exit_code_for("BLOCKED") == 1
    assert exit_code_for("FAILED") == 2
    # A word this module never writes is "no verdict", not a guess.
    assert exit_code_for("NEEDS REVIEW") == 2
    assert exit_code_for("") == 2


# ── setup legs: the run never happened, so the exit is 2 ───────────────────


def test_missing_repo_exits_two_without_a_verdict(tmp_path: Path):
    result = CliRunner().invoke(verify, [
        "--repo", str(tmp_path / "no-such-repo"),
        "--base", "b", "--head", "h",
        "--spec", str(tmp_path / "spec.txt"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert result.exit_code == 2
    assert "Repository path does not exist" in result.output


def test_missing_spec_exits_two_without_a_verdict(tmp_path: Path):
    result = CliRunner().invoke(verify, [
        "--repo", str(tmp_path),
        "--base", "b", "--head", "h",
        "--spec", str(tmp_path / "no-such-spec.txt"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert result.exit_code == 2
    assert "Spec file does not exist" in result.output


# ── full-command legs: a fake graph, the real tail ──────────────────────────


def _passing_matrix() -> dict[str, Any]:
    return {
        "rows": [{
            "contract_id": "C-1", "result": "PASS",
            "evidence_refs": ["ev-1"], "experiment_ids": ["DIFF-01"],
        }],
        "total_contracts": 1, "passed": 1, "failed": 0, "unverified": 0,
        "total_rows": 1,
    }


def _fake_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "matrix": _passing_matrix(),
        "contracts": [{"id": "C-1"}],
        "contract_results": [],
        "confirmed_findings": [],
        "errors": [],
        "capsules": [],
        "release_results": {},
    }
    state.update(overrides)
    return state


@pytest.fixture()
def fast_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A graph that returns the canned state; preflight that always passes."""
    holder: dict[str, dict[str, Any]] = {}

    class _FakeGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return holder["state"]

    monkeypatch.setattr(
        "agent.graph.build_phase0_graph", lambda: _FakeGraph()
    )
    monkeypatch.setattr("agent.preflight.detect_language", lambda *_a, **_k: "python")
    monkeypatch.setattr(
        "agent.preflight.run_preflight",
        lambda *_a, **_k: type("P", (), {"passed": True})(),
    )
    monkeypatch.setattr(
        "agent.preflight.format_preflight_report", lambda *_a, **_k: "preflight ok"
    )

    def _run(state: dict[str, Any]) -> Any:
        holder["state"] = state
        spec = tmp_path / "spec.txt"
        spec.write_text("要求: 邮箱变更需要认证\n", encoding="utf-8")
        return CliRunner().invoke(verify, [
            "--repo", str(tmp_path),
            "--base", "base", "--head", "head",
            "--spec", str(spec),
            "--output-dir", str(tmp_path / "out"),
            "--no-llm",
        ])

    return _run


def test_verified_run_exits_zero(tmp_path: Path, fast_pipeline):
    result = fast_pipeline(_fake_state())
    assert "VERDICT: VERIFIED" in result.output
    assert result.exit_code == 0


def test_blocked_run_exits_one(tmp_path: Path, fast_pipeline):
    blocked = _fake_state(
        confirmed_findings=[{
            "id": "F-1", "severity": "BLOCKER", "contract_id": "C-1",
            "confidence": 0.9, "evidence_type": "base_pass_head_fail",
            "description": "email change without authentication succeeds",
        }],
    )
    result = fast_pipeline(blocked)
    assert "VERDICT: BLOCKED" in result.output
    assert result.exit_code == 1


def test_failed_run_exits_two(tmp_path: Path, fast_pipeline):
    result = fast_pipeline(_fake_state(errors=["maven compile failed"]))
    assert "VERDICT: FAILED" in result.output
    assert result.exit_code == 2


# ── MCP legs: a non-zero exit with a verdict is the answer, not an error ────


_BLOCKED_STDOUT = """Job ID: abc123
Findings: 1 total (1 BLOCKER, 0 MAJOR, 0 MINOR)
  [BLOCKER] AUTH-01 (confidence: 90%, evidence: base_pass_head_fail)
       email change without authentication succeeds
VERDICT: BLOCKED
"""


def _run_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    proc: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    monkeypatch.setattr(mcp_tools, "_run_cli", lambda cmd, timeout: proc)
    return call_tool("specproof_verify", {
        "repo": str(tmp_path), "base_ref": "base", "head_ref": "head",
        "spec_text": "要求: 邮箱变更需要认证",
    })


def test_mcp_verify_returns_blocked_summary_with_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    payload = _run_tool(monkeypatch, tmp_path, subprocess.CompletedProcess(
        args=[], returncode=1, stdout=_BLOCKED_STDOUT, stderr="",
    ))
    assert payload["verdict"] == "BLOCKED"
    assert payload["cli_exit_code"] == 1
    assert payload["findings_summary"]["blocker"] == 1


def test_mcp_verify_still_errors_when_no_verdict_parsed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    with pytest.raises(ToolError, match="exited with code 1"):
        _run_tool(monkeypatch, tmp_path, subprocess.CompletedProcess(
            args=[], returncode=1, stdout="crash: traceback tail", stderr="",
        ))


def test_mcp_verify_zero_exit_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    payload = _run_tool(monkeypatch, tmp_path, subprocess.CompletedProcess(
        args=[], returncode=0, stdout="VERDICT: VERIFIED\n", stderr="",
    ))
    assert payload["verdict"] == "VERIFIED"
    assert "cli_exit_code" not in payload
