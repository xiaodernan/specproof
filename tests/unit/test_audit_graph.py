import json
import sys
import subprocess
from pathlib import Path

import pytest

from agent.graphs import auditor_graph

ROOT = Path(__file__).resolve().parents[2]


def test_audit_chain_runs_all_five_lanes_and_writes_report(tmp_path) -> None:
    app = auditor_graph.build_audit_chain_graph()
    result = app.invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] in {"CLEAR", "CRACKED"}
    assert len(result["results"]) == 5
    report = Path(result["report_path"])
    assert report.exists()
    assert report.parent == Path(result["report_path"]).parent == tmp_path
    md = report.read_text(encoding="utf-8")
    for lane in ("unsigned", "court_lock", "evidence", "scratch_residue", "portfolio"):
        assert f"| {lane} |" in md
    assert result["summary"].startswith("verdict=")
    # tmp report stays outside the repo tree
    assert ROOT not in report.resolve().parents


def test_audit_chain_verdict_flips_red_when_any_lane_exits_nonzero(monkeypatch, tmp_path) -> None:
    real_run = auditor_graph._run

    def fake_run(script, *args):
        if script == "audit_court_lock.py":
            return (2, "verdict: BROKEN\n")
        return real_run(script, *args)

    monkeypatch.setattr(auditor_graph, "_run", fake_run)
    app = auditor_graph.build_audit_chain_graph()
    result = app.invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "CRACKED"
    court = next(r for r in result["results"] if r["lane"] == "court_lock")
    assert court["exit"] == 2
    md = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "CRACKED" in md
