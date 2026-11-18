"""next_step_graph — offline witness for the fourteenth lamp."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.graphs.next_step_graph import (
    _EXPECTED_PIN_SHA256,
    build_next_step_graph,
    intake_node,
    verify_node,
)


@pytest.fixture()
def witness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "witness"
    monkeypatch.setenv("SPECPROOF_NEXT_STEP_WITNESS_DIR", str(d))
    monkeypatch.delenv("SPECPROOF_NEXT_STEP_LIVE", raising=False)
    return d


def test_graph_is_a_real_stategraph() -> None:
    build_next_step_graph()


def test_offline_invoke_reports_heled_when_pin_holds(witness: Path) -> None:
    result = build_next_step_graph().invoke({}) or {}
    assert result["verdict"] == "HELD"
    assert result["pinned"] is True
    assert Path(str(result["report_path"])).is_file()
    payload = json.loads(Path(str(result["report_path"])).read_text(encoding="utf-8"))
    assert payload["pinned_sha256"] == _EXPECTED_PIN_SHA256
    assert payload["lane"] == "next_step_advice"


def test_prompt_edit_flips_verdict_to_drifted(witness: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.next_step_advice as mod

    monkeypatch.setattr(mod, "_PROMPT_ZH", mod._PROMPT_ZH + "改动")
    result = build_next_step_graph().invoke({}) or {}
    assert result["verdict"] == "DRIFTED"
    assert result["pinned"] is False


def test_intake_packet_is_deterministic(witness: Path) -> None:
    out = intake_node({})
    assert out["packet_identical"] is True
    assert out["messages_shape_ok"] is True
    assert out["live_requested"] is False


def test_verify_refuses_heled_without_pin() -> None:
    assert verify_node({"pinned": False, "packet_identical": True, "messages_shape_ok": True})["verdict"] == "DRIFTED"
    assert verify_node({"pinned": True, "packet_identical": True, "messages_shape_ok": True})["verdict"] == "HELD"
