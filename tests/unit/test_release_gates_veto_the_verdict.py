"""#151: the outward verdict has to listen to the RELEASE tier's own gates.

#150 made the release gates readable in the archived HTML report. Measured before
writing this, nothing *acted* on them:

  * `release_results` had exactly one shipped reader — `publish_report.py` (#150) — and
    no reader on any announcement path;
  * `cli/specproof/commands/verify.py` accepted `--depth RELEASE` (the `--depth` choice),
    ran the gate node, then built its verdict from contract rows alone, so a campaign whose
    evidence had just failed to reproduce still issued a Merge Certificate, still persisted a
    VERIFIED job summary and still published a success GitHub Check Run (`--publish-check`);
  * correction to the backlog text: this CLI has **no** exit-code handling for a
    verdict at all (the only `SystemExit` uses are a missing repo/spec path and a
    failed preflight), so "the veto should change the exit code" is not a one-line
    fix but a separate unit — `mcp/tools.py:275` turns any non-zero return code into
    a ToolError and discards the parsed BLOCKED summary, so arming the exit code
    without fixing that consumer would replace a stated refusal with a raw tail.

The three outlets above all read the single `verdict` variable, so the veto lives in
the shared policy (`evidence/verdict.py`) and is consumed at that one call site.

Honesty rules this section pins, each with its own case:
  - a gate refusal downgrades VERIFIED and says *which* gate refused;
  - a job that is already FAILED/BLOCKED is never rewritten into something else;
  - a tier that never ran (FAST/DEEP, `release_results={}`) is untouched — "no gate"
    is not "a gate that refused";
  - a gate that checked an empty roster, or recorded no flag, is 未判定 — it can
    refuse a certificate but never support one.

Mutation arms, with the red set predicted from which branch each case walks (written
into this docstring before the witness ran, not after):

  V1 the CLI call stops passing `release=`         -> 9, 12 (2)
  V2 the veto never fires                          -> 2,3,6,7,8,9,12 (7)
  V3 a gate set that names nothing still vetoes     -> 4 (1)
  V4 the notice stops quoting the gate's own reason -> 9 (1)
  V5 the veto also rewrites a FAILED job           -> 5 (1)
  V6 an empty capsule roster reads as 通过          -> 7 (1)
  V7 a gate with no `passed` flag reads as 通过     -> 6 (1)
  V8 the gate names stop being sorted               -> 8 (1)

Cases 1, 10 and 11 are the no-false-refusal controls: they must stay green under every
arm, which is what makes V2/V3/V5 evidence rather than decoration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli.specproof.commands.verify import verify as verify_cmd
from evidence.verdict import (
    RELEASE_GATE_REASON_PREFIX,
    evaluate_acceptance,
    evaluate_verification,
)

_CONTRACT: dict[str, Any] = {
    "id": "C1",
    "checker_type": "differential",
    "description": "head must still fail the generated test",
}
_ROW: dict[str, Any] = {
    "contract_id": "C1",
    "result": "PASS",
    "evidence_refs": ["ev-1"],
    "experiment_ids": ["x-1"],
}
_MATRIX: dict[str, Any] = {
    "rows": [_ROW],
    "total_rows": 1,
    "passed": 1,
    "failed": 0,
    "unverified": 0,
}

_REPRO_PASSED: dict[str, Any] = {
    "passed": True,
    "first_head_pass": False,
    "rerun_head_pass": False,
    "rerun_mode": "docker_sandbox",
    "error": "",
}
_REPRO_FAILED: dict[str, Any] = {
    "passed": False,
    "first_head_pass": False,
    "rerun_head_pass": True,
    "rerun_mode": "docker_sandbox",
    "error": "",
}
_REPRO_NO_FLAG: dict[str, Any] = {"note": "no generated test to re-run"}
_CAPSULE_OK: dict[str, Any] = {"capsule": "reports/capsule-1.zip", "digest_ok": True}
_CAPSULE_BAD: dict[str, Any] = {"capsule": "reports/capsule-1.zip", "digest_ok": False}

PASSED_RELEASE: dict[str, Any] = {
    "passed": True,
    "gates": {"reproducibility": _REPRO_PASSED, "capsule_integrity": [_CAPSULE_OK]},
}
FAILED_RELEASE: dict[str, Any] = {
    "passed": False,
    "gates": {"reproducibility": _REPRO_FAILED, "capsule_integrity": [_CAPSULE_OK]},
}
#: The shape the node writes when the caller asked for FAST or DEEP.
NOT_REQUESTED: dict[str, Any] = {}


def _accept(release: Any) -> Any:
    return evaluate_acceptance(
        _MATRIX, contracts=[_CONTRACT], findings=(), errors=(), release=release
    )


class _FakeGraph:
    def __init__(self, final_state: dict[str, Any]) -> None:
        self._final_state = final_state

    def invoke(self, _state: dict[str, Any]) -> dict[str, Any]:
        return self._final_state


def _drive_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    depth: str,
    release: dict[str, Any],
    release_note: str,
    publish_check: bool,
) -> dict[str, Any]:
    """Run the shipped ``verify`` command over a faked pipeline result.

    Only the pipeline, the environment probe and the two optional integrations are
    replaced; the verdict, the certificate decision, the persisted summary payload and
    the rejection notice are all produced by the shipped code paths.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "App.java").write_text("class App {}", encoding="utf-8")
    spec = tmp_path / "spec.txt"
    spec.write_text("head must still fail the generated test", encoding="utf-8")
    out_dir = tmp_path / "reports"

    final_state: dict[str, Any] = {
        "report_path": "",
        "contracts": [_CONTRACT],
        "contract_results": [_ROW],
        "matrix": _MATRIX,
        "capsules": ["reports/capsule-1.zip"],
        "errors": [],
        "confirmed_findings": [],
        "release_results": release,
        "release_note": release_note,
        "depth": depth,
    }

    import agent.graph as graph_module
    import agent.preflight as preflight_module
    import evidence.certificate as certificate_module
    import storage.mysql as mysql_module
    import storage.object_metadata as metadata_module
    from cli.specproof.commands import verify as verify_module

    monkeypatch.setattr(
        graph_module, "build_phase0_graph", lambda *_a, **_k: _FakeGraph(final_state)
    )
    monkeypatch.setattr(preflight_module, "detect_language", lambda *_a, **_k: "java")
    monkeypatch.setattr(
        preflight_module, "run_preflight", lambda *_a, **_k: type("P", (), {"passed": True})()
    )
    monkeypatch.setattr(preflight_module, "format_preflight_report", lambda *_a, **_k: "ok")
    # No object store in this plane: production documents that as the legacy path.
    def _no_store() -> Any:
        raise RuntimeError("no object metadata store configured")

    monkeypatch.setattr(metadata_module, "default_object_metadata_store", _no_store)

    summaries: list[dict[str, Any]] = []

    class _RecorderStore:
        def save_job_summary(self, _job_id: str, summary: dict[str, Any]) -> None:
            summaries.append(summary)

    monkeypatch.setattr(mysql_module, "MySQLStore", _RecorderStore)

    certificates: list[dict[str, Any]] = []

    def _fake_issue(**kwargs: Any) -> None:
        certificates.append(kwargs)
        return None

    monkeypatch.setattr(certificate_module, "issue_certificate", _fake_issue)

    checks: list[dict[str, Any]] = []

    monkeypatch.setattr(
        verify_module,
        "_maybe_publish_check_run",
        lambda **kwargs: checks.append(kwargs),
    )

    args = [
        "--repo", str(repo),
        "--base", "base-sha",
        "--head", "head-sha",
        "--spec", str(spec),
        "--depth", depth,
        "--output-dir", str(out_dir),
        "--no-llm",
    ]
    if publish_check:
        args.append("--publish-check")
    result = CliRunner().invoke(verify_cmd, args, catch_exceptions=False)
    notice_files = sorted(out_dir.glob("rejection-notice-*.json"))
    notices = [
        json.loads(path.read_text(encoding="utf-8")) for path in notice_files
    ]
    return {
        "output": result.output,
        "certificates": certificates,
        "summaries": summaries,
        "checks": checks,
        "notices": notices,
    }


def test_1_release_gates_passed_leaves_the_verdict_verified() -> None:
    decision = _accept(PASSED_RELEASE)
    assert decision.status == "VERIFIED"
    assert decision.reasons == ()


def test_2_a_refused_reproducibility_gate_downgrades_to_blocked() -> None:
    decision = _accept(FAILED_RELEASE)
    assert decision.status == "BLOCKED"
    text = decision.reason
    assert "reproducibility" in text
    assert "未通过" in text


def test_3_a_capsule_digest_mismatch_downgrades_to_blocked() -> None:
    release = {
        "passed": False,
        "gates": {"capsule_integrity": [_CAPSULE_BAD]},
    }
    decision = _accept(release)
    assert decision.status == "BLOCKED"
    assert "capsule_integrity" in decision.reason
    assert "未通过" in decision.reason


def test_4_a_job_with_no_release_state_is_unchanged() -> None:
    baseline = evaluate_verification(_MATRIX, contracts=[_CONTRACT])
    # The last row is a defensive shape: `run_release_checks` always records both
    # gates, but a payload with a gate set that names nothing must not be read as a
    # refusal either — there is no verdict in it to report.
    for release in (None, {}, NOT_REQUESTED, {"gates": {}, "passed": False}):
        decision = _accept(release)
        assert decision.status == baseline.status
        assert decision.reasons == baseline.reasons


def test_5_the_veto_never_rewrites_a_job_that_is_already_failing() -> None:
    errors = [{"node": "run_differential", "error": "build failed"}]
    decision = evaluate_acceptance(
        _MATRIX,
        contracts=[_CONTRACT],
        findings=(),
        errors=errors,
        release=FAILED_RELEASE,
    )
    assert decision.status == "FAILED"
    assert not any(
        reason.startswith(RELEASE_GATE_REASON_PREFIX) for reason in decision.reasons
    )


def test_6_a_gate_without_a_passed_flag_is_unjudged_not_passed() -> None:
    release = {"passed": False, "gates": {"reproducibility": _REPRO_NO_FLAG}}
    decision = _accept(release)
    assert decision.status == "BLOCKED"
    assert "未判定" in decision.reason
    assert "通过" not in decision.reason.replace("未通过", "").replace("未判定", "")


def test_7_an_empty_capsule_roster_is_not_a_pass() -> None:
    release = {"passed": False, "gates": {"capsule_integrity": []}}
    decision = _accept(release)
    assert decision.status == "BLOCKED"
    assert "没有条目可校验" in decision.reason


def test_8_every_refused_gate_reports_exactly_one_reason() -> None:
    release = {
        "passed": False,
        "gates": {
            "reproducibility": _REPRO_FAILED,
            "capsule_integrity": [_CAPSULE_BAD],
        },
    }
    reasons = _accept(release).reasons
    gate_reasons = [
        r for r in reasons if r.startswith(RELEASE_GATE_REASON_PREFIX)
    ]
    assert len(gate_reasons) == 2 == len(release["gates"])
    assert gate_reasons == sorted(gate_reasons), "reason order must not follow dict order"
    assert sorted(r.split(" ")[2].rstrip(":") for r in gate_reasons) == [
        "capsule_integrity",
        "reproducibility",
    ]


def test_9_a_refused_gate_blocks_the_certificate_and_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = _drive_cli(
        monkeypatch,
        tmp_path,
        depth="RELEASE",
        release=FAILED_RELEASE,
        release_note="RELEASE gates: FAILED",
        publish_check=False,
    )
    assert "VERDICT: BLOCKED" in run["output"]
    assert run["certificates"] == []
    assert run["summaries"][0]["verdict"] == "BLOCKED"
    assert run["notices"], "no rejection notice was written"
    reasons = run["notices"][0]["reasons"]
    assert all(r.startswith(RELEASE_GATE_REASON_PREFIX) for r in reasons)
    assert any("reproducibility: 未通过" in r for r in reasons)
    assert "contracts unverified" not in reasons


def test_10_passing_gates_still_issue_the_certificate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = _drive_cli(
        monkeypatch,
        tmp_path,
        depth="RELEASE",
        release=PASSED_RELEASE,
        release_note="RELEASE gates: PASSED",
        publish_check=False,
    )
    assert "VERDICT: VERIFIED" in run["output"]
    assert len(run["certificates"]) == 1
    assert run["summaries"][0]["verdict"] == "VERIFIED"
    assert run["notices"] == []


def test_11_a_fast_job_is_not_vetoed_by_a_tier_it_never_ran(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = _drive_cli(
        monkeypatch,
        tmp_path,
        depth="FAST",
        release={},
        release_note="RELEASE tier not requested",
        publish_check=False,
    )
    assert "VERDICT: VERIFIED" in run["output"]
    assert len(run["certificates"]) == 1
    assert run["notices"] == []


def test_12_the_published_check_carries_the_vetoed_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run = _drive_cli(
        monkeypatch,
        tmp_path,
        depth="RELEASE",
        release=FAILED_RELEASE,
        release_note="RELEASE gates: FAILED",
        publish_check=True,
    )
    assert len(run["checks"]) == 1
    assert run["checks"][0]["verdict"] == "BLOCKED"
