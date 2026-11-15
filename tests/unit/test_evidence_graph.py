import json
from pathlib import Path

import pytest

from agent.graphs.evidence_graph import build_evidence_review_graph


def _write(p: Path, payload: dict) -> None:
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_graph_flags_regression_when_verdict_is_not_ok(tmp_path: Path) -> None:
    _write(tmp_path / "a.json", {"started_utc": "2026-11-15T17:20Z", "rounds": [{"total": 96, "ok": 96, "p99_ms": 1529.0}], "verdict": "OK"})
    _write(tmp_path / "b.json", {"started_utc": "2026-11-15T17:28Z", "rounds": [{"total": 96, "ok": 0, "p99_ms": 4999.0}], "verdict": "BUDGET-BLOWN"})
    app = build_evidence_review_graph()
    result = app.invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "REGRESSION"
    assert Path(result["report_path"]).exists()


def test_graph_ok_when_all_pass(tmp_path: Path) -> None:
    _write(tmp_path / "a.json", {"started_utc": "2026-11-15T17:20Z", "rounds": [{"total": 96, "ok": 96, "p99_ms": 1529.0}, {"total": 96, "ok": 96, "p99_ms": 1600.0}], "verdict": "OK"})
    _write(tmp_path / "b.json", {"started_utc": "2026-11-15T17:28Z", "rounds": [{"total": 96, "ok": 96, "p99_ms": 1010.0}, {"total": 96, "ok": 96, "p99_ms": 1010.1}], "verdict": "OK"})
    app = build_evidence_review_graph()
    result = app.invoke({"evidence_dir": str(tmp_path)})
    assert result["verdict"] == "OK"
    assert "entries=2" in result["summary"]


def test_graph_missing_directory_is_explicit(tmp_path: Path) -> None:
    app = build_evidence_review_graph()
    missing = tmp_path / "does-not-exist"
    result = app.invoke({"evidence_dir": str(missing)})
    assert result["verdict"] == "EVIDENCE-MISSING"
    assert Path(result["report_path"]).exists()
