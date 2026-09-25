"""#77 — `specproof eval` must isolate the declared holdout cases, and must say
which pool it measured.

`agent/holdout.py` shipped a validated registry, a human-owned manifest and its
own unit tests, while the eval command never imported it: every published
Recall/Precision was computed with the "hidden" cases still sitting in the
pool. The registry's docstring recorded that the flag was deferred because
another lane was editing eval.py — that lane cleared and the debt stayed.

Two things make this a real feature rather than a filter:
- the case-set label travels with the run (header + machine-readable sidecar),
  because `specproof baseline` diffs sidecars it otherwise cannot tell apart;
- a manifest that will not load is never read as "nothing is held out".
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
    plan_case_dirs,
)
from cli.specproof.commands.eval import eval_cmd


def _dirs(*names: str) -> list[Path]:
    return [Path(name) for name in names]


def _manifest(
    tmp_path: Path,
    case_ids: list[str],
    *,
    note: str = "Retroactive partial isolation (honest caveat).",
) -> Path:
    """A manifest in the shape HoldoutRegistry validates, not a guessed one."""
    path = tmp_path / "holdout-manifest.json"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "note": note,
        "cases": [
            {
                "case_id": case_id,
                "family": "authnz",
                "added_at": "2026-08-19",
                "status": "candidate",
            }
            for case_id in case_ids
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _cases_dir(tmp_path: Path, *names: str) -> Path:
    root = tmp_path / "golden-cases"
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


# ── the selection itself ────────────────────────────────────────


def test_default_run_drops_declared_holdout_cases(tmp_path: Path) -> None:
    """No flag = isolation on; that is the whole point of declaring a set."""
    manifest = _manifest(tmp_path, ["case-01-auth-bypass"])

    plan = plan_case_dirs(
        _dirs("case-01-auth-bypass", "case-20-refactor"),
        include_holdout=False,
        only_holdout=False,
        manifest_path=str(manifest),
    )

    assert plan.mode == CASE_SET_TUNING
    assert [d.name for d in plan.kept] == ["case-20-refactor"]
    assert plan.excluded == ["case-01-auth-bypass"]


def test_only_holdout_runs_just_the_declared_cases(tmp_path: Path) -> None:
    """Without this side there is no way to report a held-out number at all."""
    manifest = _manifest(tmp_path, ["case-01-auth-bypass", "case-03-clean-pr"])

    plan = plan_case_dirs(
        _dirs("case-01-auth-bypass", "case-02-transaction", "case-03-clean-pr"),
        include_holdout=False,
        only_holdout=True,
        manifest_path=str(manifest),
    )

    assert plan.mode == CASE_SET_HOLDOUT
    assert [d.name for d in plan.kept] == ["case-01-auth-bypass", "case-03-clean-pr"]
    assert plan.excluded == ["case-02-transaction"]


def test_include_holdout_merges_the_pool_and_says_so(tmp_path: Path) -> None:
    """The old behaviour stays reachable — but never mislabelled as isolated."""
    manifest = _manifest(tmp_path, ["case-01-auth-bypass"])

    plan = plan_case_dirs(
        _dirs("case-01-auth-bypass", "case-20-refactor"),
        include_holdout=True,
        only_holdout=False,
        manifest_path=str(manifest),
    )

    assert plan.mode == CASE_SET_ALL
    assert len(plan.kept) == 2
    assert plan.excluded == []
    header = "\n".join(plan.header_lines())
    assert "未做 holdout 隔离" in header
    assert "--include-holdout" in header


def test_the_retroactive_caveat_travels_with_the_run(tmp_path: Path) -> None:
    """The manifest's own honesty note must reach the operator, not stay in a file."""
    note = "Retroactive partial isolation: declared AFTER earlier eval rounds ran."
    manifest = _manifest(tmp_path, ["case-01-auth-bypass"], note=note)

    plan = plan_case_dirs(
        _dirs("case-01-auth-bypass", "case-20-refactor"),
        include_holdout=False,
        only_holdout=False,
        manifest_path=str(manifest),
    )

    assert note in "\n".join(plan.header_lines())
    assert plan.as_json()["manifest_note"] == note


def test_declared_case_absent_from_the_pool_is_reported(tmp_path: Path) -> None:
    """A typo'd or moved case must not read as "isolation happened"."""
    manifest = _manifest(tmp_path, ["case-77-does-not-exist"])

    plan = plan_case_dirs(
        _dirs("case-20-refactor"),
        include_holdout=False,
        only_holdout=False,
        manifest_path=str(manifest),
    )

    assert plan.kept == [Path("case-20-refactor")]
    assert plan.excluded == []
    assert plan.unknown_declared == ["case-77-does-not-exist"]
    assert "既没跑它们也没排除它们" in "\n".join(plan.header_lines())


# ── a manifest that cannot be read is not "no holdout" ──────────


def test_unreadable_manifest_fails_closed_when_isolation_is_assumed(
    tmp_path: Path,
) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with pytest.raises(Exception) as raised:
        plan_case_dirs(
            _dirs("case-20-refactor"),
            include_holdout=False,
            only_holdout=False,
            manifest_path=str(broken),
        )

    message = str(raised.value)
    assert "holdout manifest" in message
    assert "--include-holdout" in message


def test_unreadable_manifest_only_warns_when_isolation_was_turned_off(
    tmp_path: Path,
) -> None:
    """Nothing is being held out here, so the run must still be allowed."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    plan = plan_case_dirs(
        _dirs("case-20-refactor"),
        include_holdout=True,
        only_holdout=False,
        manifest_path=str(broken),
    )

    assert plan.mode == CASE_SET_ALL
    assert [d.name for d in plan.kept] == ["case-20-refactor"]


# ── the CLI wiring: reachable, labelled, and honest about an empty pool ──


def test_cli_excludes_holdout_without_any_flag(tmp_path: Path) -> None:
    """The pool here is entirely declared holdout, so an unisolated run would
    measure 2 cases and a green exit would look like a verdict."""
    cases = _cases_dir(tmp_path, "case-01-auth-bypass", "case-02-transaction")
    manifest = _manifest(tmp_path, ["case-01-auth-bypass", "case-02-transaction"])
    report = tmp_path / "out" / "eval-report.html"

    result = CliRunner().invoke(
        eval_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path), "--output", str(report),
         "--holdout-manifest", str(manifest)],
    )

    out = result.output
    assert result.exit_code == 1, out
    assert f"{CASE_SET_TUNING} — 0 个案例参与本轮评测" in out
    assert "排除 2 个" in out
    # The distinction the old build got wrong: an emptied-by-isolation pool is
    # not "this directory has no cases".
    assert "No case directories found" not in out
    # Zero measured cases must not leave behind a report that reads as a run.
    assert not report.exists()
    assert not report.with_suffix(".results.json").exists()


def test_cli_records_the_case_set_in_the_machine_readable_sidecar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A label nobody can read after the fact is not a label.

    `specproof baseline` diffs the sidecar, not the console: without the case
    set inside the JSON, a holdout run and a tuning run have the same shape and
    a pool change is reported as a model regression.

    The pipeline is patched out and must never be reached: the cases have no
    spec.md, so each one SKIPs before the graph. That pins the selection test
    as a selection test — no verification runs, no worktrees, no reports
    written into the repo's tracked docs/eval directory.
    """
    import agent.graph

    class _MustNotRun:
        def invoke(self, _state: Any) -> dict[str, Any]:
            raise AssertionError("a case without spec.md must not reach the pipeline")

    monkeypatch.setattr(
        agent.graph, "build_phase0_graph", lambda *_a, **_k: _MustNotRun()
    )

    cases = _cases_dir(tmp_path, "case-01-auth-bypass", "case-20-refactor")
    note = "Declared retroactively; earlier rounds already saw these cases."
    manifest = _manifest(tmp_path, ["case-01-auth-bypass"], note=note)
    report = tmp_path / "out" / "eval-report.html"

    result = CliRunner().invoke(
        eval_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path), "--output", str(report),
         "--holdout-manifest", str(manifest)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(
        report.with_suffix(".results.json").read_text(encoding="utf-8")
    )
    case_set = payload["case_set"]
    assert case_set["mode"] == CASE_SET_TUNING
    assert case_set["excluded_holdout_cases"] == ["case-01-auth-bypass"]
    assert case_set["manifest_note"] == note
    assert "case-01-auth-bypass" not in json.dumps(payload["cases"])


def test_cli_rejects_the_two_case_set_flags_together(tmp_path: Path) -> None:
    cases = _cases_dir(tmp_path, "case-20-refactor")

    result = CliRunner().invoke(
        eval_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path),
         "--include-holdout", "--only-holdout"],
    )

    assert result.exit_code != 0
    assert "互斥" in result.output


def test_the_shipped_manifest_still_leaves_the_sample_floors_met() -> None:
    """Default-on isolation must not starve --gate's sample floors.

    Measured 2026-09-26 against the real repo: the shipped manifest declares
    case-01..case-10 of 100 case dirs, and the 90 that remain are 55 positive /
    35 negative against floors of 10 / 5. Re-derived from the files here so the
    claim cannot rot silently when someone declares another case.
    """
    from agent.holdout import HoldoutRegistry

    cases = sorted(
        d for d in Path("golden-cases").iterdir()
        if d.is_dir() and d.name.startswith("case-")
    )
    registry = HoldoutRegistry.load()
    kept = [d for d in cases if not registry.is_holdout(d.name)]
    positive = negative = 0
    for d in kept:
        gt = d / "ground-truth.json"
        if not gt.exists():
            continue
        if json.loads(gt.read_text(encoding="utf-8")).get("should_detect"):
            positive += 1
        else:
            negative += 1

    assert len(cases) >= 20, "this guard is meaningless on a toy pool"
    assert kept, "isolation must not empty the tuning pool"
    assert positive >= 10, f"only {positive} should-detect cases left for --gate"
    assert negative >= 5, f"only {negative} negative cases left for --gate"
