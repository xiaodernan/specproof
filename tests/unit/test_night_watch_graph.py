"""night_watch_graph unit tests — hermetic: no scripts, no network, no LLM.

The night-watch composes three StateGraphs (evidence → purity → audit) and a
verdict node. The tests stub the three lane builders; everything else is real:
the compiled graph, the verdict logic, the report files written under tmp_path.
"""
import sys
import types
from pathlib import Path

import pytest

from agent.graphs import night_watch_graph as nw


class FakeApp:
    def __init__(self, payload):
        self.payload = payload

    def invoke(self, _state):
        return self.payload


def stub_lane(monkeypatch, lane: str, payload, raising: bool = False):
    """Point the composition at one lane's fake; every other lane gets a green stub."""

    def fake_build():
        if raising:
            raise RuntimeError(f"simulated {lane} failure")
        return FakeApp(payload)

    if lane == "evidence":
        module = types.SimpleNamespace(build_evidence_review_graph=fake_build)
        monkeypatch.setitem(sys.modules, "agent.graphs.evidence_graph", module)
        monkeypatch.setitem(sys.modules, "agent.graphs._evidence_graph_ok", module)
    elif lane == "purity":
        module = types.SimpleNamespace(build_purity_graph=fake_build)
        monkeypatch.setitem(sys.modules, "agent.graphs.purity_graph", module)
    elif lane == "audit":
        module = types.SimpleNamespace(build_audit_chain_graph=fake_build)
        monkeypatch.setitem(sys.modules, "agent.graphs.auditor_graph", module)


def stub_ok(monkeypatch, evidence_dir: Path):
    stub_lane(monkeypatch, "evidence", {"verdict": "OK", "summary": "verdict=OK entries=3"})
    stub_lane(monkeypatch, "purity", {"summary": "verdict=CLEAR hits=0"})
    stub_lane(monkeypatch, "audit", {"summary": "verdict=CLEAR lanes=5"})


def test_all_green_marks_CLEAR_and_writes_both_files(tmp_path, monkeypatch):
    stub_ok(monkeypatch, tmp_path)
    result = nw.build_night_watch_graph().invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "CLEAR"
    report = tmp_path / "night-watch.md"
    sidecar = tmp_path / "night-watch.json"
    assert report.exists() and sidecar.exists()
    text = report.read_text(encoding="utf-8")
    assert "verdict: CLEAR" in text
    doc = __import__("json").loads(sidecar.read_text(encoding="utf-8"))
    assert doc["verdict"] == "CLEAR"
    assert doc["lanes"] == {"evidence": "OK", "purity": "CLEAR", "audit": "CLEAR"}
    assert result["summary"].startswith("verdict=CLEAR")


@pytest.mark.parametrize("lane,payload", [
    ("purity", {"summary": "verdict=CRACKED hits=3"}),
    ("audit", {"summary": "verdict=CRACKED lanes=5"}),
    ("evidence", {"verdict": "REGRESSION", "summary": "verdict=REGRESSION"}),
])
def test_one_cracked_lane_fails_the_watch(tmp_path, monkeypatch, lane, payload):
    stub_ok(monkeypatch, tmp_path)
    stub_lane(monkeypatch, lane, payload)
    result = nw.build_night_watch_graph().invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "CRACKED"
    assert any(name in f for f in result["findings"] for name in [lane])


def test_exception_in_a_lane_is_a_crack_not_a_crash(tmp_path, monkeypatch):
    stub_ok(monkeypatch, tmp_path)
    stub_lane(monkeypatch, "evidence", None, raising=True)
    result = nw.build_night_watch_graph().invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "CRACKED"
    assert (tmp_path / "night-watch.md").exists()


def test_missing_report_dir_is_created_by_the_emitter(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "deeper"
    stub_ok(monkeypatch, nested)
    result = nw.build_night_watch_graph().invoke({"evidence_dir": str(nested)})
    assert result["verdict"] == "CLEAR"
    assert nested.joinpath("night-watch.json").exists()
