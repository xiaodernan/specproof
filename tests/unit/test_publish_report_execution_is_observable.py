"""Publish report node execution tests (#187 backfill) — honest counters at
the publish_report node boundary.

The #187 landing (bafd22f) shipped the counters with zero behavioral tests;
this file drives the real node — renderer, lineage build and both file
writes run for real. Only the replay-report metadata sink is stubbed (the
real one reaches the shared object store):

- publish_report_runs_total: every attempt, including one that dies in
  lineage building;
- publish_report_success_total: fires only after BOTH artifacts exist on
  disk (HTML report + lineage JSON);
- the runs>success gap is honest: a lineage failure after the HTML write
  leaves the HTML on disk, no success tick, and no metadata entries for a
  half-complete artifact pair.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent.nodes.publish_report import publish_report_node
from observability.metrics import snapshot


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _stub_metadata_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, Path, str, tuple[str, ...]]]:
    """Replace the metadata sink with a recorder; the real function connects
    to the object store, and artifact writing must not depend on it."""
    calls: list[tuple[str, Path, str, tuple[str, ...]]] = []

    def fake(
        kind: str,
        path: str | Path,
        *,
        job_id: str = "",
        contract_ids: Any = (),
    ) -> None:
        calls.append((kind, Path(path), job_id, tuple(contract_ids)))

    monkeypatch.setattr(
        "storage.object_metadata.record_file_object_best_effort", fake
    )
    return calls


def _state(tmp_path: Path) -> dict[str, Any]:
    return {
        "job_id": "job-185b0001",
        "output_dir": str(tmp_path),
        "matrix": {"rows": [], "passed": 0, "failed": 0, "unverified": 0},
        "repo_path": "repo",
        "base_ref": "base",
        "head_ref": "head",
        "confirmed_findings": [],
        "errors": [],
        "requirement_text": (
            "Only authenticated users may change the account email."
        ),
        "contracts": [],
    }


# ── the counter family ─────────────────────────────────────────────────────


def test_successful_publish_counts_runs_and_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_metadata_recorder(monkeypatch)
    before_runs = _counter("publish_report_runs_total")
    before_success = _counter("publish_report_success_total")

    result = publish_report_node(_state(tmp_path))

    assert _counter("publish_report_runs_total") == before_runs + 1
    assert _counter("publish_report_success_total") == before_success + 1

    # Both artifacts exist on disk — success is only counted with them.
    report_path = Path(result["report_path"])
    lineage_path = Path(result["lineage_path"])
    assert report_path.is_file()
    assert lineage_path.is_file()
    # The lineage file name is the 8-char job slug, not the timestamp.
    assert lineage_path.name == "job-185b-lineage.json"
    assert result["lineage_root"]

    # The metadata sink saw exactly the pair, under the job id.
    assert [(c[0], c[1].resolve(), c[2]) for c in calls] == [
        ("replay_report", lineage_path.resolve(), "job-185b0001"),
        ("replay_report", report_path.resolve(), "job-185b0001"),
    ]


def test_lineage_failure_leaves_runs_above_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_metadata_recorder(monkeypatch)

    def boom(raw_state: object, built_at: str = "") -> Any:  # noqa: ARG001
        raise RuntimeError("simulated lineage failure")

    monkeypatch.setattr("evidence.lineage.build_lineage", boom)
    before_runs = _counter("publish_report_runs_total")
    before_success = _counter("publish_report_success_total")

    with pytest.raises(RuntimeError, match="simulated lineage failure"):
        publish_report_node(_state(tmp_path))

    assert _counter("publish_report_runs_total") == before_runs + 1
    # No success tick — the gap between runs and success is the honest
    # failure signal for a report without its lineage chain.
    assert _counter("publish_report_success_total") == before_success
    # The HTML landed before the failure: the gap is partial work, and the
    # metadata sink records nothing for a half-complete artifact pair.
    assert list(tmp_path.glob("verification-report-*.html"))
    assert len(list(tmp_path.glob("*-lineage.json"))) == 0
    assert calls == []
