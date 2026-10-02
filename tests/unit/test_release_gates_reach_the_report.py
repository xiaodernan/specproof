"""#150: a RELEASE campaign's own gates have to be readable in the archived report.

`--depth RELEASE` is a shipped CLI choice (`cli/specproof/commands/verify.py:293`) and
`run_release_checks` runs on every graph execution (`agent/graph.py:122-123`): it re-runs the
generated test on HEAD and recomputes every capsule's manifest digest. Measured before writing
this: `release-report.json` had **zero** readers in the tree and `release_results` /
`release_note` were read only by `tests/unit/test_release_checks.py`, while
`publish_report.py` forwarded `deep`/`deep_note` and dropped the release pair. So the strongest
tier the product offers archived a report that said nothing about its gates — a run that failed
to reproduce its own evidence looked exactly like one that passed. Same disease #140 closed for
the DEEP cache statement, one tier up.

Two ends are pinned, because a disclosure that never reaches the call is a feature of the test
file rather than of the product:
  * the renderer (what a reviewer reads, including every kind of absence), and
  * `publish_report_node`, the only shipped caller.

Honesty rules this section is built on, each pinned by a case:
  - a tier that never ran produces no per-gate verdict, and the words 通过 must not appear;
  - a caller with no release state at all gets no section (silence, not reassurance);
  - a gate that checked an empty set is 未判定, not "all digests match";
  - a gate entry carrying no `passed` flag is 未判定 — the flag is the only source of verdicts.

Mutation arms, with red sets predicted from which branch each case walks (written before the
witness ran, not after):

  R1 the node stops forwarding the release pair      -> 9, 10 (2)
  R2 the not-requested branch says the gates passed  -> 3 (1)
  R3 the empty-capsule branch is dropped             -> 5 (1)
  R4 a gate with no `passed` flag reads as passed    -> 8 (1)
  R5 the section is never inserted into the document -> 1,2,3,5,6,7,8 (7); 4,9,10 stay green
  R6 a capsule path is rendered unescaped            -> 7 (1)
  R7 the overall verdict ignores `passed`            -> 2 (1)

Case 4 (legacy caller) stays green under R1/R5 by design: it asserts an absence, and an absent
section cannot make an absence assertion fail. That is why it is paired with 9/10, which assert
the carrier is actually wired.
"""

from __future__ import annotations

from typing import Any

from agent.nodes.publish_report import publish_report_node
from evidence.report import render_verification_report

MATRIX: dict[str, Any] = {"rows": []}
PASSED_RELEASE: dict[str, Any] = {
    "passed": True,
    "gates": {
        "reproducibility": {
            "passed": True,
            "first_head_pass": False,
            "rerun_head_pass": False,
            "rerun_mode": "docker_sandbox",
            "error": "",
        },
        "capsule_integrity": [{"capsule": "reports/capsule-1.zip", "digest_ok": True}],
    },
}
NOT_REQUESTED_NOTE = "RELEASE tier not requested"


def _render(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "repo": "demo/repo",
        "base_ref": "base-sha",
        "head_ref": "head-sha",
        "matrix": MATRIX,
        "findings": [],
        "generated_at": "2026-10-02 00:00:00 UTC",
    }
    kwargs.update(overrides)
    return render_verification_report(**kwargs)


def test_1_a_passed_release_campaign_names_both_gates() -> None:
    html = _render(release=PASSED_RELEASE, release_note="RELEASE gates: PASSED")
    assert "Release Gates 发布门" in html
    assert "发布门总判定: 通过" in html
    assert "reproducibility: 通过" in html
    assert "capsule_integrity: 通过" in html
    assert "reports/capsule-1.zip 摘要相符" in html
    assert "RELEASE gates: PASSED" in html


def test_2_a_failed_gate_cannot_look_like_a_pass() -> None:
    """The polarity flip is the whole point of the reproducibility gate."""
    payload: dict[str, Any] = {
        "passed": False,
        "gates": {
            "reproducibility": {
                "passed": False,
                "first_head_pass": True,
                "rerun_head_pass": False,
                "rerun_mode": "local",
                "error": "exit 1",
            },
            "capsule_integrity": [],
        },
    }
    html = _render(release=payload, release_note="RELEASE gates: FAILED")
    assert "发布门总判定: 未通过" in html
    assert "reproducibility: 未通过" in html
    assert "first_head_pass=True" in html
    assert "rerun_head_pass=False" in html
    assert "error=exit 1" in html


def test_3_a_tier_that_never_ran_produces_no_verdict() -> None:
    html = _render(release={}, release_note=NOT_REQUESTED_NOTE)
    assert NOT_REQUESTED_NOTE in html
    assert "本次没有执行任何发布门" in html
    assert "reproducibility" not in html
    assert "发布门总判定" not in html


def test_4_a_caller_that_knows_nothing_gets_no_section() -> None:
    assert "Release Gates" not in _render()


def test_5_an_empty_capsule_set_is_not_a_pass() -> None:
    payload: dict[str, Any] = {"passed": True, "gates": {"capsule_integrity": []}}
    html = _render(release=payload, release_note="RELEASE gates: PASSED")
    assert "capsule_integrity: 未判定" in html
    assert "没有条目可校验" in html
    assert "全部相符" not in html


def test_6_an_unopenable_capsule_is_named() -> None:
    payload: dict[str, Any] = {
        "passed": False,
        "gates": {
            "capsule_integrity": [
                {"capsule": "reports/bad.zip", "error": "File is not a zip file"}
            ]
        },
    }
    html = _render(release=payload, release_note="RELEASE gates: FAILED")
    assert "reports/bad.zip 无法打开: File is not a zip file" in html
    assert "capsule_integrity: 未通过" in html


def test_7_a_hostile_capsule_path_stays_text() -> None:
    payload: dict[str, Any] = {
        "passed": True,
        "gates": {
            "capsule_integrity": [
                {
                    "capsule": 'x<script>alert("digest")</script>.zip',
                    "digest_ok": True,
                }
            ]
        },
    }
    html = _render(release=payload, release_note="ran")
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html


def test_8_a_gate_without_a_flag_is_undecided_not_passed() -> None:
    payload: dict[str, Any] = {
        "passed": True,
        "gates": {"signing": {"note": "certificate path handled by the caller"}},
    }
    html = _render(release=payload, release_note="ran")
    assert "signing: 未判定" in html
    assert "signing: 通过" not in html


def _drive_node(
    monkeypatch, tmp_path, state: dict[str, Any]
) -> dict[str, Any]:
    """Run the shipped node and return the kwargs it passed to the renderer."""
    import evidence.lineage as lineage
    import evidence.report as report
    import storage.object_metadata as metadata

    captured: dict[str, Any] = {}

    def fake_render(**kwargs: Any) -> str:
        captured.update(kwargs)
        return "<html>report</html>"

    monkeypatch.setattr(report, "render_verification_report", fake_render)
    monkeypatch.setattr(
        lineage, "build_lineage", lambda _s, **_k: ({"nodes": [], "edges": []}, "root")
    )
    monkeypatch.setattr(lineage, "lineage_to_json", lambda _d, _r: "{}")
    monkeypatch.setattr(
        metadata, "record_file_object_best_effort", lambda *_a, **_k: None
    )
    node_state: dict[str, Any] = {
        "repo_path": "demo/repo",
        "base_ref": "base-sha",
        "head_ref": "head-sha",
        "matrix": MATRIX,
        "confirmed_findings": [],
        "errors": [],
        "preflight": {},
        "job_id": "",
        "output_dir": str(tmp_path / "reports"),
    }
    node_state.update(state)
    publish_report_node(node_state)  # type: ignore[arg-type]
    return captured


def test_9_the_node_forwards_the_gates_it_was_given(monkeypatch, tmp_path) -> None:
    captured = _drive_node(
        monkeypatch,
        tmp_path,
        {"release_results": PASSED_RELEASE, "release_note": "RELEASE gates: PASSED"},
    )
    assert captured["release"] == PASSED_RELEASE
    assert captured["release_note"] == "RELEASE gates: PASSED"


def test_10_a_job_without_release_state_forwards_nothing(monkeypatch, tmp_path) -> None:
    """Empty, not fabricated: the renderer must receive nothing to invent with."""
    captured = _drive_node(monkeypatch, tmp_path, {})
    assert captured["release"] == {}
    assert captured["release_note"] == ""
