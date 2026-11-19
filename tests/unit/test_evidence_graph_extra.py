import json
from pathlib import Path

from agent.graphs.evidence_graph import build_evidence_review_graph


def _write(p: Path, payload: dict) -> None:
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_malformed_exhibit_is_recorded_and_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path / "a.json", {"started_utc": "2026-11-15T17:20Z", "rounds": [{"total": 96, "ok": 96, "p99_ms": 1000.0}], "verdict": "OK"})
    (tmp_path / "b.json").write_text("{not-json", encoding="utf-8")
    result = build_evidence_review_graph().invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "EVIDENCE-MISSING"
    assert any("unreadable b.json" in e for e in result["errors"])
    assert Path(result["report_path"]).exists()


def test_audit_family_jsons_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path / "audit-links.json", {"version": 3})
    _write(tmp_path / "audit-evidence.json", {"verdict": "CONSISTENT"})
    _write(tmp_path / "weekly-summary.json", {"version": 1})
    _write(tmp_path / "evidence-tick.md", {}) if False else None
    _write(tmp_path / "c.json", {"started_utc": "2026-11-15T17:30Z", "rounds": [{"total": 10, "ok": 10, "p99_ms": 500.0}], "verdict": "OK"})
    result = build_evidence_review_graph().invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "NO-DELTA"  # only one exhibit, no drift pair
    assert len(result["rounds"]) == 1
    assert result["rounds"][0]["file"] == "c.json"
