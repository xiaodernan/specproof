import json
import sys
import subprocess
from pathlib import Path

import pytest

from agent.graphs import auditor_graph

ROOT = Path(__file__).resolve().parents[2]


def test_audit_chain_runs_all_five_lanes_and_writes_report() -> None:
    app = auditor_graph.build_audit_chain_graph()
    result = app.invoke({})
    assert result["verdict"] in {"CLEAR", "CRACKED"}
    assert len(result["results"]) == 5
    assert Path(result["report_path"]).exists()
    md = Path(result["report_path"]).read_text(encoding="utf-8")
    for lane in ("unsigned", "court_lock", "evidence", "scratch_residue", "portfolio"):
        assert f"| {lane} |" in md
    assert result["summary"].startswith("verdict=")


def test_audit_chain_verdict_flips_red_when_any_lane_exits_nonzero(monkeypatch) -> None:
    real_run = auditor_graph._run

    def fake_run(script, *args):
        if script == "audit_court_lock.py":
            return (2, "verdict: BROKEN\n")
        return real_run(script, *args)

    monkeypatch.setattr(auditor_graph, "_run", fake_run)
    app = auditor_graph.build_audit_chain_graph()
    result = app.invoke({})
    assert result["verdict"] == "CRACKED"
    court = next(r for r in result["results"] if r["lane"] == "court_lock")
    assert court["exit"] == 2
