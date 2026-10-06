"""Run-static-checks node execution tests (#196) — honest counters at the
node boundary, written WITH the landing (not backfilled).

The checker seams (run_contract_checks / dispatch_checker /
contract_results_for — all imported at module level by the node) are
stubbed on the node module; the file reads and the shared
merge_contract_results run for real against tmp workspaces. One case per
outcome word in RUN_STATIC_OUTCOMES, plus the two verdict-shaping
behaviors the word reading rule leans on:

- inputs_missing: a missing workspace short-circuits before any checker
  (witness: the run_contract_checks stub would raise) and passes the
  existing contract_results through untouched;
- checked: the registry ran, every checker returned; a BLOCKER finding is
  capped to MAJOR/0.85 and the PASS result carries the snapshot digest;
- checker_failures: a crashed checker rides out in out["checker_failures"]
  untouched (exempt from the cap loop) while sibling BLOCKERs are capped
  — the crash must not read as "no problems found";
- removed base sources downgrade a static PASS to UNVERIFIED (still a
  checked run — the word does not lie about "ran");

plus run_static_checks_runs_total on every path and a drift gate binding
the parity family's regex words to RUN_STATIC_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import agent.nodes.run_static_checks as static_module
from agent.nodes.run_static_checks import RUN_STATIC_OUTCOMES, run_static_checks_node
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("run_static_checks_runs_total",) + tuple(
    f"run_static_checks_outcomes_{word}_total"
    for word in sorted(RUN_STATIC_OUTCOMES)
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
    deltas["run_static_checks_runs_total"] = 1.0
    for word in words:
        deltas[f"run_static_checks_outcomes_{word}_total"] = 1.0
    return deltas


class _Recorder:
    """Stub callable that records every invocation."""

    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return self.result


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / "src" / "main" / "java" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _stub_checkers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    findings: list[dict[str, Any]] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> tuple[_Recorder, _Recorder, _Recorder]:
    run_checks = _Recorder(list(findings or []))
    monkeypatch.setattr(static_module, "run_contract_checks", run_checks)
    dispatch = _Recorder([])
    monkeypatch.setattr(static_module, "dispatch_checker", dispatch)
    results_for = _Recorder(list(results or []))
    monkeypatch.setattr(static_module, "contract_results_for", results_for)
    return run_checks, dispatch, results_for


def _state(
    base: str, head: str, contract_results: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "base_workspace": base,
        "head_workspace": head,
        "app_dir": "",
        "contracts": [],
        "contract_results": contract_results if contract_results is not None else [],
    }


def test_inputs_missing_short_circuits_and_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bomb(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("missing inputs must short-circuit before any checker")

    monkeypatch.setattr(static_module, "run_contract_checks", bomb)

    existing = [{"contract_id": "C0", "result": "FAIL"}]
    before = _before()
    out = run_static_checks_node(  # type: ignore[arg-type]
        {"base_workspace": "", "head_workspace": "x", "contract_results": existing}
    )

    assert out["static_findings"] == []
    assert out["contract_results"] is existing, (
        "the short circuit must pass the existing results through untouched"
    )
    assert _deltas(before) == _only("inputs_missing")


def test_checked_counts_checked_and_caps_blockers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = _tree(tmp_path / "base", {"A.java": "class A {}"})
    head = _tree(tmp_path / "head", {"A.java": "class A {}"})
    blast = {"type": "regression", "severity": "BLOCKER", "confidence": 0.99}
    _run, dispatch, _results = _stub_checkers(
        monkeypatch,
        findings=[blast],
        results=[{"contract_id": "C1", "result": "PASS",
                  "evidence_ref": None, "details": ""}],
    )

    before = _before()
    out = run_static_checks_node(_state(str(base), str(head)))  # type: ignore[arg-type]

    capped = out["static_findings"][0]
    assert capped["severity"] == "MAJOR"
    assert capped["confidence"] == 0.85
    assert "cannot produce BLOCKER" in capped["p0_5_note"]

    result = out["contract_results"][0]
    assert result["result"] == "PASS"
    assert result["evidence_ref"].startswith("static:C1:"), (
        "a kept PASS must carry the snapshot digest identifying its inputs"
    )
    assert "snapshot digest" in result["details"]

    assert [call[0][0] for call in dispatch.calls] == [
        "check_schema_sql", "check_test_weakening",
    ], "no-contract runs dispatch exactly the two named heterogeneous checkers"
    assert "checker_failures" not in out
    assert _deltas(before) == _only("checked")


def test_checker_crash_counts_checker_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = _tree(tmp_path / "base", {"A.java": "class A {}"})
    head = _tree(tmp_path / "head", {"A.java": "class A {}"})
    crash = {"type": "checker_failed", "checker": "check_schema_sql",
             "error": "boom"}
    blast = {"type": "regression", "severity": "BLOCKER", "confidence": 0.99}
    _stub_checkers(monkeypatch, findings=[crash, blast], results=[])

    before = _before()
    out = run_static_checks_node(_state(str(base), str(head)))  # type: ignore[arg-type]

    assert out["checker_failures"] == [crash]
    assert crash.get("severity") is None, (
        "CHECKER_FAILED is infrastructure evidence — exempt from the cap loop"
    )
    assert out["static_findings"][1]["severity"] == "MAJOR", (
        "a sibling BLOCKER source verdict is still capped in the same run"
    )
    assert _deltas(before) == _only("checker_failures")


def test_removed_sources_downgrade_pass_to_unverified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = _tree(tmp_path / "base", {"A.java": "class A {}",
                                     "Old.java": "class Old {}"})
    head = _tree(tmp_path / "head", {"A.java": "class A {}"})
    _stub_checkers(
        monkeypatch,
        results=[{"contract_id": "C1", "result": "PASS",
                  "evidence_ref": None, "details": ""}],
    )

    before = _before()
    out = run_static_checks_node(_state(str(base), str(head)))  # type: ignore[arg-type]

    result = out["contract_results"][0]
    assert result["result"] == "UNVERIFIED", (
        "a deleted base class cannot leave a static PASS standing"
    )
    assert result["evidence_ref"] is None
    assert "Java 源文件被删除" in result["details"]
    assert "Old.java" in result["details"]
    assert _deltas(before) == _only("checked"), (
        "the run still happened — the word does not lie about 'ran'"
    )


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "run_static_checks.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(
            r'incr\("run_static_checks_outcomes_([a-z0-9_]+)_total"\)', source
        )
    )
    assert literals == set(RUN_STATIC_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(RUN_STATIC_OUTCOMES)}"
    )
    assert source.count('incr("run_static_checks_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["run_static_checks"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(RUN_STATIC_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(RUN_STATIC_OUTCOMES)}"
    )
