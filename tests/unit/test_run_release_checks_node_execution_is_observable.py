"""RELEASE-tier node execution tests (#201) — honest counters at the node
boundary, written WITH the landing (not backfilled).

The sandbox re-run seam is stubbed (late import from run_deep_experiments);
the capsule integrity gate reads REAL zip files built in tmp. One case per
outcome word in RUN_RELEASE_OUTCOMES, plus the capsule-digit witness the
word reading rule leans on:

- not_requested: depth != RELEASE (or absent) — the healthy default;
- passed: the re-run matches the recorded verdict polarity and the empty
  capsule list stays an EMPTY list (pinned — not a fabricated pass);
- failed: the re-run flips the polarity — the gate refuses honestly;
- a bad capsule digest also lands on failed (isolated from the
  reproducibility gate, which passes in the same run);

plus run_release_checks_runs_total on every path and a drift gate binding
the parity family's regex words to RUN_RELEASE_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agent.nodes.run_release_checks import (
    RUN_RELEASE_OUTCOMES,
    run_release_checks_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("run_release_checks_runs_total",) + tuple(
    f"run_release_checks_outcomes_{word}_total"
    for word in sorted(RUN_RELEASE_OUTCOMES)
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["run_release_checks_runs_total"] = 1.0
    for word in words:
        deltas[f"run_release_checks_outcomes_{word}_total"] = 1.0
    return deltas


def _stub_rerun(
    monkeypatch: pytest.MonkeyPatch, *, exit_code: int
) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def fake(app: str, generated: str) -> dict[str, Any]:
        calls.append((app, generated))
        return {"exit_code": exit_code, "mode": "local", "error": ""}

    monkeypatch.setattr(
        "agent.nodes.run_deep_experiments._run_test_via_sandbox", fake
    )
    return calls


def _state(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "depth": "RELEASE",
        "generated_tests_path": str(tmp_path / "SpecProofGeneratedTest.java"),
        "head_workspace": str(tmp_path / "head"),
        "app_dir": "",
        "diff_results": [{
            "evidence_type": "base_pass_head_fail",
            "head_exit_code": 0,
        }],
        "capsules": [],
        "output_dir": str(tmp_path / "reports"),
    }
    state.update(overrides)
    return state


def test_not_requested_counts_not_requested() -> None:
    before = _before()
    out = run_release_checks_node({})  # type: ignore[arg-type]

    assert out == {
        "release_results": {},
        "release_note": "RELEASE tier not requested",
    }
    assert _deltas(before) == _only("not_requested")


def test_passed_counts_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_rerun(monkeypatch, exit_code=0)

    before = _before()
    out = run_release_checks_node(_state(tmp_path))  # type: ignore[arg-type]

    assert len(calls) == 1
    results = out["release_results"]
    assert results["passed"] is True
    assert results["gates"]["reproducibility"]["rerun_head_pass"] is True
    assert results["gates"]["capsule_integrity"] == [], (
        "no capsules is an EMPTY list — the gate checked nothing, which the "
        "veto layer reads as 未判定, never a fabricated pass"
    )
    assert out["release_note"] == "RELEASE gates: PASSED"
    report = tmp_path / "reports" / "release-report.json"
    assert report.is_file()
    assert json.loads(report.read_text(encoding="utf-8"))["passed"] is True
    assert _deltas(before) == _only("passed")


def test_reproducibility_flip_counts_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_rerun(monkeypatch, exit_code=2)

    before = _before()
    out = run_release_checks_node(_state(tmp_path))  # type: ignore[arg-type]

    results = out["release_results"]
    assert results["passed"] is False
    gate = results["gates"]["reproducibility"]
    assert gate["first_head_pass"] is True
    assert gate["rerun_head_pass"] is False
    assert out["release_note"] == "RELEASE gates: FAILED"
    assert _deltas(before) == _only("failed")


def test_bad_capsule_digest_counts_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_rerun(monkeypatch, exit_code=0)
    bad_zip = tmp_path / "capsule-F1.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"finding_id": "F1", "manifest_digest": "sha256:deadbeef"}),
        )

    before = _before()
    out = run_release_checks_node(  # type: ignore[arg-type]
        _state(tmp_path, capsules=[str(bad_zip)])
    )

    results = out["release_results"]
    assert results["gates"]["reproducibility"]["passed"] is True, (
        "this case isolates the capsule gate — reproducibility must hold"
    )
    assert results["gates"]["capsule_integrity"] == [
        {"capsule": str(bad_zip), "digest_ok": False}
    ]
    assert results["passed"] is False
    assert _deltas(before) == _only("failed")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "run_release_checks.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(
            r'incr\("run_release_checks_outcomes_([a-z0-9_]+)_total"\)', source
        )
    )
    assert literals == set(RUN_RELEASE_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(RUN_RELEASE_OUTCOMES)}"
    )
    assert source.count('incr("run_release_checks_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["run_release_checks"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(RUN_RELEASE_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(RUN_RELEASE_OUTCOMES)}"
    )
