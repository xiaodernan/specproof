"""#78 — a gain is only a gain when both sides measured the same cases.

`specproof baseline` compares a naive diff-reader's Recall/Precision against
the SpecProof eval sidecar and prints the Go/No-Go #14 verdict ("+25pp
recall"). The report it writes has long carried the heading
"## 对比 (同一 case 集合)" — "same case set" — which nothing verified.

Before #77 that heading was accidentally honest: both sides walked every
`case-*` directory. Once eval started excluding the declared holdout by
default, the claim became false by construction (90 cases vs 100), and a
pool change would have been published as a model gain. These tests pin the
three things that keep it honest: one selection policy for both commands, a
label on both sidecars, and a refusal to subtract across pools.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

import cli.specproof.main  # noqa: F401  — sys.path bootstrap, as in other CLI tests
from cli.specproof.case_set import (
    CASE_SET_ALL,
    CASE_SET_HOLDOUT,
    CASE_SET_TUNING,
    pool_mismatch,
)
from cli.specproof.commands.baseline import baseline_cmd, render_report

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PY = ROOT / "cli" / "specproof" / "commands" / "baseline.py"
EVAL_PY = ROOT / "cli" / "specproof" / "commands" / "eval.py"


def _label(
    mode: str = CASE_SET_TUNING,
    excluded: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "excluded_holdout_cases": sorted(excluded or []),
        "declared_but_absent": [],
        "manifest_note": "",
    }


BASE_SUMMARY: dict[str, Any] = {
    "total_cases": 90,
    "recall": 50.0,
    "precision": 50.0,
    "f1": 50.0,
    "false_positives": 0,
    "negative_cases": 35,
}
SP_SIDECAR: dict[str, Any] = {"recall": 80.0, "precision": 90.0, "f1": 84.8}
ROWS: list[dict[str, Any]] = [
    {
        "case": "case-20-refactor",
        "should_detect": True,
        "verdict": "MISS",
        "contracts_found": [],
    }
]


def _render(note: str | None) -> str:
    return render_report(
        ROWS, BASE_SUMMARY, dict(SP_SIDECAR), "deterministic diff-reader",
        case_set_note=note,
    )


# ── the mismatch predicate ──────────────────────────────────────


def test_matching_pools_are_comparable() -> None:
    label = _label(excluded=["case-01-auth-bypass"])
    assert pool_mismatch(label, json.loads(json.dumps(label))) is None


def test_different_modes_cannot_be_subtracted() -> None:
    note = pool_mismatch(_label(CASE_SET_TUNING), _label(CASE_SET_HOLDOUT))
    assert note is not None
    assert CASE_SET_TUNING in note and CASE_SET_HOLDOUT in note


def test_same_mode_with_different_exclusions_is_still_a_different_pool() -> None:
    """Two tuning runs on different days can hold out different cases; the mode
    string alone would let a pool change read as a regression."""
    note = pool_mismatch(
        _label(excluded=["case-01-auth-bypass"]),
        _label(excluded=["case-01-auth-bypass", "case-02-transaction"]),
    )
    assert note is not None
    assert "case-02-transaction" in note


def test_an_unlabelled_sidecar_is_reported_as_unknown_not_assumed_equal() -> None:
    """Every sidecar written before #77 is unlabelled. Its pool is unknown,
    which is not the same as 'it matched'."""
    note = pool_mismatch(_label(), None)
    assert note is not None
    assert "case_set" in note


# ── the report: the suppressed verdict must be the note's doing ──


def test_report_prints_the_gain_when_the_pools_agree() -> None:
    """The control: without the note the same numbers must still produce the
    delta, so 'suppressed' below cannot be an always-on stub."""
    out = _render(None)
    assert "(同一 case 集合)" in out
    assert "+30.0pp" in out
    assert "Go/No-Go #14 (+25pp recall): **PASS**" in out


def test_report_refuses_a_gain_across_pools() -> None:
    note = "案例池模式不同：基线 tuning vs SpecProof all_not_isolated。"
    out = _render(note)
    assert "跨池不可比" in out
    assert "案例池不一致" in out
    assert "(同一 case 集合)" not in out
    assert "**PASS**" not in out
    assert "无法判定" in out
    # The individual measurements stay on the page; only the subtraction goes.
    assert "80.0" in out and "50.0" in out


# ── the commands: one policy, two consumers ─────────────────────


def test_both_commands_select_through_the_shared_policy() -> None:
    """A second copy of the filter is how the pools drift apart again."""
    for path in (BASELINE_PY, EVAL_PY):
        src = path.read_text(encoding="utf-8")
        assert "plan_case_dirs(" in src, path.name
        assert "case_dirs = plan.kept" in src, path.name
        assert "is_holdout(" not in src, f"{path.name} must not re-implement it"


def test_baseline_sidecar_carries_its_own_case_set() -> None:
    src = BASELINE_PY.read_text(encoding="utf-8")
    body = src.split("def baseline_cmd(", 1)[1]
    assert '"case_set": plan.as_json(),' in body


def test_baseline_isolates_before_it_needs_a_repo(tmp_path: Path) -> None:
    """Every case here is declared holdout, so the run must stop on the pool
    decision rather than reaching capture_diff against a directory that is not
    a git repository."""
    manifest = _manifest(tmp_path, ["case-01-auth-bypass"])
    cases = tmp_path / "golden-cases"
    (cases / "case-01-auth-bypass").mkdir(parents=True)

    result = CliRunner().invoke(
        baseline_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path),
         "--output", str(tmp_path / "r.md"),
         "--holdout-manifest", str(manifest)],
    )

    assert result.exit_code == 1, result.output
    assert f"{CASE_SET_TUNING} — 0 个案例参与本轮评测" in result.output
    assert "排除 1 个" in result.output
    assert not (tmp_path / "r.md").exists()


def _manifest(tmp_path: Path, case_ids: list[str]) -> Path:
    """A manifest in the shape HoldoutRegistry validates, not a guessed one."""
    path = tmp_path / "holdout-manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "note": "test manifest",
                "cases": [
                    {
                        "case_id": case_id,
                        "family": "authnz",
                        "added_at": "2026-08-19",
                        "status": "candidate",
                    }
                    for case_id in case_ids
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_baseline_writes_its_own_case_set_label(tmp_path: Path) -> None:
    """The label has to be in the artifact the command leaves behind.

    The repo here is not a git repository, so every case is skipped on an empty
    diff; the run still writes its sidecar, which is what a later reader trusts.
    """
    cases = tmp_path / "golden-cases"
    (cases / "case-20-refactor").mkdir(parents=True)
    out = tmp_path / "r.md"

    result = CliRunner().invoke(
        baseline_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path), "--output", str(out),
         "--holdout-manifest", str(_manifest(tmp_path, []))],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(out.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload["case_set"]["mode"] == CASE_SET_TUNING


def test_baseline_refuses_the_gain_when_the_sidecar_is_unlabelled(
    tmp_path: Path,
) -> None:
    """Wiring, not just the predicate: the command must notice a pre-#77 file.

    A stored SpecProof sidecar with no case_set says nothing about its pool, so
    the "+25pp recall" Go/No-Go cannot be printed from it.
    """
    cases = tmp_path / "golden-cases"
    (cases / "case-20-refactor").mkdir(parents=True)
    sidecar = tmp_path / "eval-report.results.json"
    sidecar.write_text(
        json.dumps(
            {"total_cases": 100, "recall": 80.0, "precision": 90.0, "f1": 84.8}
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        baseline_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path),
         "--output", str(tmp_path / "r.md"),
         "--specproof-results", str(sidecar),
         "--holdout-manifest", str(_manifest(tmp_path, []))],
    )

    assert result.exit_code == 0, result.output
    assert "案例池不一致" in result.output
    assert "无法求增益" in result.output
    assert "Go/No-Go" not in result.output


def test_baseline_rejects_the_two_case_set_flags_together(tmp_path: Path) -> None:
    cases = tmp_path / "golden-cases"
    (cases / "case-20-refactor").mkdir(parents=True)

    result = CliRunner().invoke(
        baseline_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path),
         "--include-holdout", "--only-holdout"],
    )

    assert result.exit_code != 0
    assert "互斥" in result.output


@pytest.mark.parametrize(
    "mode",
    [CASE_SET_TUNING, CASE_SET_ALL, CASE_SET_HOLDOUT],
)
def test_every_mode_is_named_in_the_sidecar_vocabulary(mode: str) -> None:
    """A mode nobody can write is a mode the label cannot carry."""
    assert pool_mismatch(_label(mode), _label(mode)) is None
