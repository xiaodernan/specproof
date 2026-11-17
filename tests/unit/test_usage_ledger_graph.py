"""usage_ledger_graph — the ledger reports itself (offline witness).

Mirrors test_insight_advice.py's shape: env-var-ledger redirection, graph build
compilation, end-to-end invoke via the real StateGraph.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.graphs.usage_ledger_graph import (
    build_usage_ledger_graph,
    intake_node,
    strike_node,
    verdict_node,
)


def _seed(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _row(age_hours: float, **over):
    base = {
        "ts": (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat(timespec="seconds"),
        "model": "test-model",
        "kind": "diagnose",
        "lane": "direct",
        "streamed": True,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cached_tokens": 90,
        "duration_ms": 100,
        "error": False,
    }
    base.update(over)
    return base


@pytest.fixture()
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ledger = tmp_path / "ledger.jsonl"
    witness = tmp_path / "witness"
    _seed(ledger, [_row(1.0), _row(2.0, lane="policy", kind="draft", cached_tokens=0, prompt_tokens=50)])
    monkeypatch.setenv("SPECPROOF_LLM_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("SPECPROOF_LEDGER_WITNESS_DIR", str(witness))
    monkeypatch.setenv("SPECPROOF_LEDGER_WINDOW_HOURS", "24")
    return ledger


def test_graph_is_a_real_stategraph() -> None:
    g = build_usage_ledger_graph()
    assert g is not None


def test_intake_clamps_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_LEDGER_WINDOW_HOURS", "99999")
    out = intake_node({})
    assert out["window_hours"] == 24.0 * 30


def test_intake_defaults_to_24h(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECPROOF_LEDGER_WINDOW_HOURS", raising=False)
    out = intake_node({})
    assert out["window_hours"] == 24.0


def test_unseeded_ledger_is_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_LLM_USAGE_LEDGER", str(tmp_path / "nope.jsonl"))
    monkeypatch.setenv("SPECPROOF_LEDGER_WITNESS_DIR", str(tmp_path / "w"))
    result = build_usage_ledger_graph().invoke({})
    assert result["verdict"] == "UNAVAILABLE"
    assert result["rows_read"] == 0


def test_error_rows_count_as_errors_but_still_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _seed(ledger, [_row(1.0, error=True, cached_tokens=None, prompt_tokens=0)])
    monkeypatch.setenv("SPECPROOF_LLM_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("SPECPROOF_LEDGER_WITNESS_DIR", str(tmp_path / "w"))
    result = build_usage_ledger_graph().invoke({})
    assert result["verdict"] == "ANSWERED"
    assert result["summary"]["errors"] == 1
    assert result["summary"]["calls"] == 1


def test_by_lane_is_honest_under_the_graph(seeded: Path) -> None:
    result = build_usage_ledger_graph().invoke({})
    lanes = {b["lane"]: b for b in result["summary"]["by_lane"]}
    assert set(lanes) == {"direct", "policy"}
    assert lanes["direct"]["cached_tokens"] == 90
    assert lanes["policy"]["cached_tokens"] == 0


def test_report_files_are_written(seeded: Path, tmp_path: Path) -> None:
    result = build_usage_ledger_graph().invoke({})
    report = Path(tmp_path / "witness" / "usage-ledger-witness.md")
    data = Path(tmp_path / "witness" / "usage-ledger-witness.json")
    assert report.is_file()
    assert data.is_file()
    md = report.read_text(encoding="utf-8")
    assert "verdict: ANSWERED" in md
    assert "direct" in md and "policy" in md
    payload = json.loads(data.read_text(encoding="utf-8"))
    assert payload["verdict"] == "ANSWERED"
    assert payload["rows_read"] == 2


def test_window_excludes_old_rows_but_row_count_is_total(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "ledger.jsonl"
    _seed(ledger, [_row(24 * 30 + 1.0), _row(1.0)])
    monkeypatch.setenv("SPECPROOF_LLM_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("SPECPROOF_LEDGER_WITNESS_DIR", str(tmp_path / "w"))
    monkeypatch.setenv("SPECPROOF_LEDGER_WINDOW_HOURS", "1")
    out = strike_node(intake_node({}))
    assert out["rows_read"] == 2
    monkeypatch.setenv("SPECPROOF_LEDGER_WINDOW_HOURS", "1")
    result = verdict_node({"summary": {"calls": 1}})
    assert result["verdict"] == "ANSWERED"
