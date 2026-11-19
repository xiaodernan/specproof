"""ask_the_book_graph — the public lane watched by StateGraph (offline witness).

DP-style mirror of test_usage_ledger_graph.py: env-var witness-dir redirection,
real StateGraph build + invoke, no tokens spent in CI (live strike requires
SPECPROOF_ASK_THE_BOOK_LIVE=1 and is deliberately never set here).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.graphs.ask_the_book_graph import (
    _EXPECTED_PIN_SHA256,
    build_ask_the_book_graph,
    intake_node,
    verify_node,
)


@pytest.fixture()
def witness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "witness"
    monkeypatch.setenv("SPECPROOF_ASK_THE_BOOK_WITNESS_DIR", str(d))
    monkeypatch.delenv("SPECPROOF_ASK_THE_BOOK_LIVE", raising=False)
    return d


def test_graph_is_a_real_stategraph() -> None:
    g = build_ask_the_book_graph()
    assert g is not None


def test_offline_invoke_reports_heled_when_pin_holds(witness: Path) -> None:
    result = build_ask_the_book_graph().invoke({}) or {}
    assert result["verdict"] == "HELD"
    assert result["pinned"] is True
    assert Path(str(result["report_path"])).is_file()


def test_pin_drift_flips_verdict_to_drifted(witness: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import api.worldbook_ask as mod

    monkeypatch.setattr(mod, "_ZH_SYSTEM", mod._ZH_SYSTEM + "二次敲击")
    result = build_ask_the_book_graph().invoke({}) or {}
    assert result["verdict"] == "DRIFTED"
    assert result["pinned"] is False


def test_offline_report_never_claims_content_pass(witness: Path) -> None:
    result = build_ask_the_book_graph().invoke({}) or {}
    payload = json.loads(Path(str(result["report_path"])).read_text(encoding="utf-8"))
    import re

    md_path = re.sub(r"ask-the-book-(\d{4}-\d{2}-\d{2})\.json$", r"ask-the-book-witness-\1.md", str(result["report_path"]))
    md = Path(md_path).read_text(encoding="utf-8")
    assert payload["lane"] == "ask_the_book"
    assert payload["live_requested"] is False
    assert payload["verdict"] == "HELD"
    assert "the witness never decides whether an exhibit is green" in md
    assert payload["pinned_sha256"] == _EXPECTED_PIN_SHA256


def test_intake_sanitizer_and_fingerprint(witness: Path) -> None:
    out = intake_node({})
    assert out["sanitizer_ok"] is True
    assert out["fingerprint_ok"] is True
    assert out["messages_shape_ok"] is True
    assert out["prefix_identity_ok"] is True


def test_verify_refuses_heled_without_pin_even_offline() -> None:
    assert verify_node({"pinned": False, "sanitizer_ok": True, "messages_shape_ok": True, "fingerprint_ok": True})["verdict"] == "DRIFTED"
    assert verify_node({"pinned": True, "sanitizer_ok": True, "messages_shape_ok": True, "fingerprint_ok": True})["verdict"] == "HELD"
