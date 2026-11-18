"""stress_digest_graph — offline witness for the fifteenth lamp."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.graphs.stress_digest_graph import (
    _EXPECTED_PIN_SHA256,
    build_stress_digest_graph,
    intake_node,
    verify_node,
)
import api.stress_digest as digest_mod

_SAMPLE = {
    "started_utc": "2026-11-19T00:00:00+00:00",
    "note": "static lane, 3 entry assets, fresh server on 127.0.0.1",
    "concurrency": 48,
    "per_thread": 2,
    "warmup_rounds": 2,
    "rounds": [
        {"total": 96, "ok": 96, "err_rate": 0.0, "p50_ms": 21.0, "p90_ms": 1476.0, "p95_ms": 1854.0, "p99_ms": 1888.0, "max_ms": 1891.0, "avg_ms": 526.0, "bytes_read": 40_000_000, "sample_errors": []},
        {"total": 96, "ok": 96, "err_rate": 0.0, "p50_ms": 22.0, "p90_ms": 1272.0, "p95_ms": 1479.0, "p99_ms": 1878.0, "max_ms": 1882.0, "avg_ms": 467.0, "bytes_read": 40_000_000, "sample_errors": []},
    ],
    "verdict": "OK",
    "honesty": "This is a static-asset delivery probe on this host; it is not a FastAPI/MySQL/Redis rating.",
}


@pytest.fixture()
def evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "weekly-2026-11-19.json"
    p.write_text(json.dumps(_SAMPLE), encoding="utf-8")
    monkeypatch.setenv("SPECPROOF_STRESS_EVIDENCE", str(p))
    return p


@pytest.fixture()
def witness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "witness"
    monkeypatch.setenv("SPECPROOF_STRESS_DIGEST_DIR", str(d))
    monkeypatch.delenv("SPECPROOF_STRESS_DIGEST_LIVE", raising=False)
    return d


def test_graph_is_a_real_stategraph() -> None:
    build_stress_digest_graph()


def test_offline_invoke_reports_held_when_pin_holds(evidence: Path, witness: Path) -> None:
    result = build_stress_digest_graph().invoke({}) or {}
    assert result["verdict"] == "HELD"
    assert result["pinned"] is True
    assert Path(str(result["report_path"])).is_file()
    payload = json.loads(Path(str(result["report_path"])).read_text(encoding="utf-8"))
    assert payload["pinned_sha256"] == _EXPECTED_PIN_SHA256
    assert payload["lane"] == "stress_digest"
    assert payload["evidence_file"] == "weekly-2026-11-19.json"
    assert payload["floor_comparison"] == "under"
    assert payload["worst_p99_ms"] == pytest.approx(1888.0)
    assert payload["err_rate_any"] is False


def test_offline_digest_md_carries_the_packet_numbers_verbatim(evidence: Path, witness: Path) -> None:
    result = build_stress_digest_graph().invoke({}) or {}
    md = Path(str(result["report_path"])).with_suffix(".md")
    text = md.read_text(encoding="utf-8")
    assert "1888" in text            # worst p99 verbatim
    assert "5000" in text            # the machine floor, stated as a fact
    assert "not a FastAPI/MySQL/Redis rating" in text  # honesty line verbatim
    assert "通过" not in text and "approved" not in text.lower()
    # every round appears in the table
    assert "| 1 |" in text and "| 2 |" in text


def test_prompt_edit_flips_verdict_to_drifted(evidence: Path, witness: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(digest_mod, "_PROMPT_ZH", digest_mod._PROMPT_ZH + "改动")
    result = build_stress_digest_graph().invoke({}) or {}
    assert result["verdict"] == "DRIFTED"
    assert result["pinned"] is False


def test_intake_packet_is_deterministic(evidence: Path, witness: Path) -> None:
    out = intake_node({})
    assert out["packet_identical"] is True
    assert out["messages_shape_ok"] is True
    assert out["live_requested"] is False


def test_missing_evidence_marks_packet_unreadable_not_fabricated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, witness: Path) -> None:
    monkeypatch.setenv("SPECPROOF_STRESS_EVIDENCE", str(tmp_path / "nope.json"))
    packet = digest_mod.build_stress_packet()
    assert packet["error"]
    assert "weekly-*.json" in packet["error"]
    out = intake_node({})
    assert out["packet_identical"] is False


def test_verify_refuses_held_without_pin() -> None:
    assert verify_node({"pinned": False, "packet_identical": True, "messages_shape_ok": True})["verdict"] == "DRIFTED"
    assert verify_node({"pinned": True, "packet_identical": True, "messages_shape_ok": True})["verdict"] == "HELD"


def test_live_strike_skipped_without_flag(evidence: Path, witness: Path) -> None:
    result = build_stress_digest_graph().invoke({}) or {}
    assert "live strike skipped" in result["notes"]
    assert result.get("sealed_zh") is None
