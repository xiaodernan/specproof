"""Intake node execution tests (#186 backfill) — honest counters at the
intake node boundary.

The #186 landing (306687d) shipped the counters with zero behavioral tests;
this file drives the real node (no stubs — intake only reads the filesystem):

- intake_runs_total: every invocation (delta assertions — the registry is
  process-global);
- intake_repo_missing_total / intake_spec_missing_total: the two failure
  counters (each aborts the job at the preflight guard, but neither stops
  later checks inside this node — see the spec-read note below);
- intake_spec_read_total: fires whenever the spec file is readable — the
  repo and spec checks are independent, so a missing repo does NOT
  short-circuit the spec read (one run can tick repo_missing AND spec_read;
  "spec read" is a per-check outcome, not the job outcome).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.nodes.intake import intake_node
from observability.metrics import snapshot

_SPEC_TEXT = "Only authenticated users may change the account email.\n"

_COUNTERS = (
    "intake_runs_total",
    "intake_repo_missing_total",
    "intake_spec_missing_total",
    "intake_spec_read_total",
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


# ── the counter family ─────────────────────────────────────────────────────


def test_successful_intake_counts_runs_and_spec_read(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC_TEXT, encoding="utf-8")

    before = _before()
    result = intake_node({"repo_path": str(repo), "spec_path": str(spec)})

    assert _deltas(before) == {
        "intake_runs_total": 1,
        "intake_repo_missing_total": 0,
        "intake_spec_missing_total": 0,
        "intake_spec_read_total": 1,
    }
    assert result["requirement_text"] == _SPEC_TEXT
    assert result["errors"] == []


def test_missing_repo_counts_repo_missing_and_still_reads_spec(
    tmp_path: Path,
) -> None:
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC_TEXT, encoding="utf-8")

    before = _before()
    result = intake_node({
        "repo_path": str(tmp_path / "missing-repo"),
        "spec_path": str(spec),
    })

    assert _deltas(before) == {
        "intake_runs_total": 1,
        "intake_repo_missing_total": 1,
        # The checks are independent: a missing repo does not stop the spec
        # read, so both counters tick on this single run.
        "intake_spec_read_total": 1,
        "intake_spec_missing_total": 0,
    }
    assert any("Repository path does not exist" in e for e in result["errors"])
    assert result["requirement_text"] == _SPEC_TEXT


def test_missing_spec_counts_spec_missing_without_spec_read(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    before = _before()
    result = intake_node({
        "repo_path": str(repo),
        "spec_path": str(tmp_path / "missing-spec.md"),
    })

    assert _deltas(before) == {
        "intake_runs_total": 1,
        "intake_repo_missing_total": 0,
        "intake_spec_missing_total": 1,
        "intake_spec_read_total": 0,
    }
    assert result["requirement_text"] == ""
    assert any("Spec file does not exist" in e for e in result["errors"])


def test_both_missing_counts_both_failure_counters(tmp_path: Path) -> None:
    before = _before()
    result = intake_node({
        "repo_path": str(tmp_path / "no-repo"),
        "spec_path": str(tmp_path / "no-spec.md"),
    })

    assert _deltas(before) == {
        "intake_runs_total": 1,
        "intake_repo_missing_total": 1,
        "intake_spec_missing_total": 1,
        "intake_spec_read_total": 0,
    }
    assert len(result["errors"]) == 2


def test_prior_errors_survive_intake(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC_TEXT, encoding="utf-8")

    before = _before()
    state: dict[str, Any] = {
        "repo_path": str(repo),
        "spec_path": str(spec),
        "errors": ["upstream failure"],
    }
    result = intake_node(state)

    # The node appends to state["errors"] — it must not replace earlier ones.
    assert result["errors"] == ["upstream failure"]
    assert _deltas(before)["intake_runs_total"] == 1
