"""Unit tests for scripts/summarize_leaderboard.py with a synthetic fixture.

The fixture (fixtures/swebench_leaderboard_synthetic.json) mirrors the live
shape of the leaderboard JSON embedded in https://www.swebench.com: a top-level
array of benchmark views, each {"name": ..., "results": [...]}, where the
"Verified" view carries per-submission agent/model/resolved/cost/date fields.

The script is loaded by path with importlib (scripts/ is not a package in this
repo, and an unrelated "scripts" package may shadow it on sys.path).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "summarize_leaderboard.py"
FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "swebench_leaderboard_synthetic.json"
)

TOP15_AGENTS = [
    "Delta Agent",
    "Beta Agent",
    "Epsilon Agent",
    "Zeta Agent",
    "Gamma Agent",
    "Eta Agent",
    "Theta Agent",
    "Iota Agent",
    "Kappa Agent",
    "Lambda Agent",
    "Mu Agent",
    "Alpha Agent",
    "Nu Agent",
    "Xi Agent",
    "Omicron Agent",
]


def _load_summarize() -> Any:
    """Load scripts/summarize_leaderboard.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "summarize_leaderboard_under_test", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses can resolve the module by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def summarize() -> Any:
    """The summarize_leaderboard module under test."""
    return _load_summarize()


@pytest.fixture
def blob() -> object:
    payload: object = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return payload


@pytest.fixture
def view(summarize: Any, blob: object) -> Any:
    return summarize.parse_verified_entries(blob)


def test_parses_verified_view_only(view: Any) -> None:
    assert view.total_submissions == 18
    assert view.excluded_without_resolved == 1
    assert [row.agent for row in view.rows] == TOP15_AGENTS + ["Pi Agent", "Sigma Agent"]


def test_sorts_by_resolved_then_date_then_agent(view: Any) -> None:
    agents = [row.agent for row in view.rows]
    resolved = [row.resolved for row in view.rows]
    assert resolved == sorted(resolved, reverse=True)
    # Same resolved % (79.2): the later date ranks first.
    assert agents.index("Delta Agent") < agents.index("Beta Agent")
    # Same resolved % (74.4): the later date ranks first.
    assert agents.index("Alpha Agent") < agents.index("Nu Agent")
    # Same resolved % and same date: agent name asc decides.
    assert agents.index("Pi Agent") < agents.index("Sigma Agent")


def test_model_field_falls_back_to_name(view: Any) -> None:
    delta = view.rows[0]
    assert delta.agent == "Delta Agent"
    assert delta.model == "Model D"
    beta = next(row for row in view.rows if row.agent == "Beta Agent")
    assert beta.model == "Beta Agent + Model B"
    assert beta.cost is None


def test_renders_table_with_formatting(summarize: Any, view: Any) -> None:
    markdown = summarize.render_markdown(
        view,
        limit=15,
        generated_at="2026-01-01 00:00 UTC",
        fetched_at="2025-12-31 23:59 UTC",
        raw_artifact="fixture.json",
    )
    assert "| # | Agent | Model | Resolved % | Cost (USD) | Date |" in markdown
    assert "| 1 | Delta Agent | Model D | 79.2 | $8.00 | 2025-12-01 |" in markdown
    assert (
        f"| 2 | Beta Agent | Beta Agent + Model B | 79.2 | {summarize.EM_DASH} "
        "| 2025-11-02 |"
        in markdown
    )
    assert "| 3 | Epsilon Agent | Model E | 78.8 | $200.50 | 2025-10-10 |" in markdown
    assert "| 4 | Zeta Agent | Model Z | 77.4 | $55.55 | 2025-10-11 |" in markdown
    assert "| 8 | Iota Agent | Model I | 75.6 | $1,000.00 | 2025-05-05 |" in markdown
    assert f"| 14 | Xi Agent | Model Xi | 73.9 | $7.77 | {summarize.EM_DASH} |" in markdown
    assert "Fetched: 2025-12-31 23:59 UTC" in markdown
    assert "1 Verified submission(s) are excluded" in markdown
    assert "2 further submission(s) are below the top 15." in markdown
    # Rows outside the top 15 must not appear.
    assert "Pi Agent" not in markdown
    assert "Distractor Agent" not in markdown


def test_zero_cost_is_shown_as_dollars(summarize: Any, view: Any) -> None:
    markdown = summarize.render_markdown(
        view,
        limit=15,
        generated_at="2026-01-01 00:00 UTC",
        fetched_at="2025-12-31 23:59 UTC",
        raw_artifact="fixture.json",
    )
    gamma_line = next(line for line in markdown.splitlines() if "Gamma Agent" in line)
    assert "$0.00" in gamma_line


def test_limit_truncates_rows(summarize: Any, view: Any) -> None:
    markdown = summarize.render_markdown(
        view,
        limit=5,
        generated_at="2026-01-01 00:00 UTC",
        fetched_at="2025-12-31 23:59 UTC",
        raw_artifact="fixture.json",
    )
    data_rows = [
        line
        for line in markdown.splitlines()
        if line.startswith("| ") and not line.startswith("| #")
    ]
    assert len(data_rows) == 5
    assert "Eta Agent" not in markdown
    assert "12 further submission(s) are below the top 5." in markdown


def test_missing_verified_view_raises(summarize: Any, blob: object) -> None:
    assert isinstance(blob, list)
    stripped: list[object] = [
        item
        for item in blob
        if isinstance(item, dict) and item.get("name") != "Verified"
    ]
    with pytest.raises(
        summarize.LeaderboardFormatError, match="no 'Verified' leaderboard view"
    ):
        summarize.parse_verified_entries(stripped)


def test_results_not_a_list_raises(summarize: Any) -> None:
    malformed: object = {"name": "Verified", "results": "not-a-list"}
    with pytest.raises(summarize.LeaderboardFormatError, match="no 'results' array"):
        summarize.parse_verified_entries(malformed)


def test_single_benchmark_object_blob(summarize: Any, blob: object) -> None:
    assert isinstance(blob, list)
    verified_item = next(
        item
        for item in blob
        if isinstance(item, dict) and item.get("name") == "Verified"
    )
    view = summarize.parse_verified_entries(verified_item)
    assert view.total_submissions == 18
    assert view.rows[0].agent == "Delta Agent"


def test_load_blob_rejects_invalid_json(summarize: Any, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(summarize.LeaderboardFormatError, match="not valid JSON"):
        summarize.load_blob(bad)


def test_main_writes_table_from_fixture(summarize: Any, tmp_path: Path) -> None:
    out = tmp_path / "leaderboard.md"
    exit_code = summarize.main(
        ["--raw", str(FIXTURE_PATH), "--out", str(out), "--limit", "15"]
    )
    assert exit_code == 0
    content = out.read_text(encoding="utf-8")
    assert "| 1 | Delta Agent | Model D | 79.2 | $8.00 | 2025-12-01 |" in content
    assert "FAILURE NOTE" not in content


def test_main_writes_failure_note_for_missing_raw(summarize: Any, tmp_path: Path) -> None:
    out = tmp_path / "leaderboard.md"
    exit_code = summarize.main(
        ["--raw", str(tmp_path / "missing.json"), "--out", str(out)]
    )
    assert exit_code == 1
    content = out.read_text(encoding="utf-8")
    assert "FAILURE NOTE" in content
    assert "cannot read" in content
    assert "| 1 |" not in content


def test_main_writes_failure_note_for_malformed_blob(summarize: Any, tmp_path: Path) -> None:
    raw = tmp_path / "raw.json"
    raw.write_text('{"name": "Verified", "results": "not-a-list"}', encoding="utf-8")
    out = tmp_path / "leaderboard.md"
    exit_code = summarize.main(["--raw", str(raw), "--out", str(out)])
    assert exit_code == 1
    content = out.read_text(encoding="utf-8")
    assert "FAILURE NOTE" in content
    assert "no 'results' array" in content
