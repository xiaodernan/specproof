import subprocess
from pathlib import Path

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
    evidence = [ROOT / "docs" / "evidence" / f"purity-sift.{ext}" for ext in ("md", "json")]
    snapshots = [(p, p.read_bytes() if p.exists() else None) for p in evidence]
    try:
        subprocess.run(["git", "add", "_purity_fixture_for_test.py"], cwd=ROOT, check=False, capture_output=True)
        app = build_purity_graph()
        result = app.invoke({})
        assert result["verdict"] == "CRACKED", result
        assert any("purity_fixture" in h["file"] for h in result.get("hits", []))
    finally:
        subprocess.run(["git", "reset", "-q", "_purity_fixture_for_test.py"], cwd=ROOT, check=False, capture_output=True)
        fixture.unlink(missing_ok=True)
        # The graph always rewrites the canonical evidence with whatever it
        # just saw — the forced-hit scan must never leave that file CRACKED.
        for p, raw in snapshots:
            if raw is not None:
                p.write_bytes(raw)
