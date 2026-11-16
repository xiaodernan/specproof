import subprocess
import sys
from pathlib import Path

import pytest

from agent.graphs.purity_graph import build_purity_graph

ROOT = Path(__file__).resolve().parents[2]


def test_purity_graph_clean_on_this_repo() -> None:
    app = build_purity_graph()
    result = app.invoke({})
    assert result["verdict"] in {"CLEAR", "CRACKED"}
    assert Path(result["report_path"]).exists()
    assert len(result.get("hits", [])) == 0


def test_purity_graph_flags_forced_extra_hit(tmp_path, monkeypatch) -> None:
    # construct the secret-shaped string at runtime so the source never contains it verbatim
    prefix = "s" + "k" + "-"
    fake = "x" * 32 + "_abcdefghijklmnopqrst"
    fixture = ROOT / "_purity_fixture_for_test.py"
    fixture.write_text(f"private_key = '{prefix}{fake}'\n", encoding="utf-8")
    try:
        subprocess.run(["git", "add", "_purity_fixture_for_test.py"], cwd=ROOT, check=False, capture_output=True)
        app = build_purity_graph()
        result = app.invoke({})
        assert result["verdict"] == "CRACKED", result
        assert any("purity_fixture" in h["file"] for h in result.get("hits", []))
    finally:
        subprocess.run(["git", "reset", "-q", "_purity_fixture_for_test.py"], cwd=ROOT, check=False, capture_output=True)
        fixture.unlink(missing_ok=True)
