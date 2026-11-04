"""Matrix-build node execution tests (#199) — honest counters at the node
boundary, written WITH the landing (not backfilled).

build_matrix is a pure function of the state dict, so there is nothing to
stub: every case drives a real state fixture through the node. One case
per outcome word in BUILD_MATRIX_OUTCOMES:

- built: a normal build — the evidenced PASS row survives the node's own
  evaluate_verification gate unchanged;
- no_contracts: an empty contract list — the matrix is assembled from
  findings alone (here: zero rows at all);
- pass_downgraded: a PASS row WITHOUT evidence refs / experiment ids is
  refused by the node's gate and rewritten to UNVERIFIED with the gate's
  own reason and the re-verification next action;

plus build_matrix_runs_total on every path and a drift gate binding the
parity family's regex words to BUILD_MATRIX_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent.matrix_policy import NEXT_ACTION_UNVERIFIED
from agent.nodes.build_matrix import BUILD_MATRIX_OUTCOMES, build_matrix_node
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("build_matrix_runs_total",) + tuple(
    f"build_matrix_outcomes_{word}_total"
    for word in sorted(BUILD_MATRIX_OUTCOMES)
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
    deltas["build_matrix_runs_total"] = 1.0
    for word in words:
        deltas[f"build_matrix_outcomes_{word}_total"] = 1.0
    return deltas


_CONTRACT = {
    "id": "AUTH-01",
    "checker_type": "http",
    "requirement": "Unauthenticated requests must receive 401.",
}


def test_built_counts_built() -> None:
    state: dict[str, Any] = {
        "contracts": [dict(_CONTRACT)],
        "contract_results": [{
            "contract_id": "AUTH-01",
            "result": "PASS",
            "experiment": "EXP-1",
            "evidence_ref": "static:AUTH-01:abc",
        }],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["passed"] == 1
    row = matrix["rows"][0]
    assert row["result"] == "PASS", (
        "an evidenced PASS row must survive the node's own gate"
    )
    assert (row.get("unverified_reason") or "") == "", (
        "a kept PASS row carries no refusal reason"
    )
    assert _deltas(before) == _only("built")


def test_no_contracts_counts_no_contracts() -> None:
    before = _before()
    out = build_matrix_node({"contracts": []})  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["total_contracts"] == 0
    assert matrix["rows"] == []
    assert matrix["total_rows"] == 0
    assert _deltas(before) == _only("no_contracts")


def test_contracts_without_results_row_is_unverified() -> None:
    """Contracts present but no contract_results in state: rows are built
    from contracts only, with UNVERIFIED result (no evidence/experiment)."""
    state: dict[str, Any] = {
        "contracts": [dict(_CONTRACT)],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["total_contracts"] == 1
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert row["result"] == "UNVERIFIED", (
        "a contract with no result entry must be UNVERIFIED, not PASS"
    )
    assert _deltas(before) == _only("built")


def test_already_unverified_result_is_preserved() -> None:
    """contract_results with result already UNVERIFIED (e.g. from differential
    execution where no tests ran) is preserved as-is through build_matrix_node,
    not upgraded or downgraded."""
    state: dict[str, Any] = {
        "contracts": [dict(_CONTRACT)],
        "contract_results": [{
            "contract_id": "AUTH-01",
            "result": "UNVERIFIED",
            "experiment": "DIFF-01",
            "evidence_ref": "",
            "details": "Generated test executed no tests",
        }],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["total_contracts"] == 1
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert row["result"] == "UNVERIFIED", (
        "an already-UNVERIFIED result must stay UNVERIFIED, not be upgraded"
    )
    assert _deltas(before) == _only("built")


def test_multiple_contracts_merge_by_priority() -> None:
    """多合同、多结果进入 build_matrix_node：FAIL 优先于 UNVERIFIED，
    每份合同独立计算，互不干扰。"""
    state: dict[str, Any] = {
        "contracts": [
            {"id": "AUTH-01", "checker_type": "http", "requirement": "c1"},
            {"id": "TXN-01", "checker_type": "sql", "requirement": "c2"},
        ],
        "contract_results": [
            {"contract_id": "AUTH-01", "result": "FAIL",
             "experiment": "java_source_diff", "evidence_ref": "f-1",
             "details": "annotation removed"},
            {"contract_id": "TXN-01", "result": "UNVERIFIED",
             "experiment": "java_source_diff", "evidence_ref": "",
             "details": "no observable construct"},
        ],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["total_contracts"] == 2
    assert len(matrix["rows"]) == 2
    by_id = {row["contract_id"]: row for row in matrix["rows"]}
    assert by_id["AUTH-01"]["result"] == "FAIL"
    assert by_id["TXN-01"]["result"] == "UNVERIFIED"
    assert matrix["failed"] == 1
    assert matrix["unverified"] == 1
    assert matrix["passed"] == 0
    assert _deltas(before) == _only("built")
    state: dict[str, Any] = {
        "contracts": [dict(_CONTRACT)],
        # A PASS verdict with no evidence reference and no experiment id —
        # exactly what the node's own gate refuses to back.
        "contract_results": [{"contract_id": "AUTH-01", "result": "PASS"}],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["passed"] == 0
    assert matrix["unverified"] == 1
    row = matrix["rows"][0]
    assert row["result"] == "UNVERIFIED", (
        "a PASS without evidence/experiment must not survive the gate"
    )
    assert "缺少证据引用" in row["unverified_reason"]
    assert "缺少实验记录" in row["unverified_reason"]
    assert row["next_action"] == NEXT_ACTION_UNVERIFIED
    assert _deltas(before) == _only("pass_downgraded")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "build_matrix.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(
            r'incr\("build_matrix_outcomes_([a-z0-9_]+)_total"\)', source
        )
    )
    assert literals == set(BUILD_MATRIX_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(BUILD_MATRIX_OUTCOMES)}"
    )
    assert source.count('incr("build_matrix_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["build_matrix"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(BUILD_MATRIX_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(BUILD_MATRIX_OUTCOMES)}"
    )


def test_mixed_contracts_with_and_without_results() -> None:
    """多合同：部分有检验结果、部分无结果。有结果的按其结果呈现，
    无结果的自动标记 UNVERIFIED，互不干扰。"""
    state: dict[str, Any] = {
        "contracts": [
            {"id": "AUTH-01", "checker_type": "http", "requirement": "c1"},
            {"id": "TXN-01", "checker_type": "sql", "requirement": "c2"},
        ],
        "contract_results": [
            {"contract_id": "AUTH-01", "result": "PASS",
             "experiment": "java_source_diff", "evidence_ref": "ev-1"},
        ],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["total_contracts"] == 2
    assert len(matrix["rows"]) == 2
    by_id = {row["contract_id"]: row for row in matrix["rows"]}
    assert by_id["AUTH-01"]["result"] == "PASS"
    assert by_id["TXN-01"]["result"] == "UNVERIFIED"
    assert matrix["passed"] == 1
    assert matrix["unverified"] == 1
    assert matrix["failed"] == 0
    assert _deltas(before) == _only("built")


def test_multiple_results_same_contract_fail_wins() -> None:
    """同一合同有多个结果：FAIL 优先于 PASS，最终结果为 FAIL。"""
    state: dict[str, Any] = {
        "contracts": [
            {"id": "AUTH-01", "checker_type": "http", "requirement": "c1"},
        ],
        "contract_results": [
            {"contract_id": "AUTH-01", "result": "PASS",
             "experiment": "static_checks", "evidence_ref": "static-1",
             "details": "guarded construct intact"},
            {"contract_id": "AUTH-01", "result": "FAIL",
             "experiment": "differential", "evidence_ref": "diff-1",
             "details": "regression detected"},
        ],
    }
    before = _before()
    out = build_matrix_node(state)  # type: ignore[arg-type]

    matrix = out["matrix"]
    assert matrix["total_contracts"] == 1
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert row["contract_id"] == "AUTH-01"
    assert row["result"] == "FAIL", (
        "FAIL must win over PASS when same contract has multiple results"
    )
    assert matrix["failed"] == 1
    assert matrix["passed"] == 0
    assert matrix["unverified"] == 0
    assert _deltas(before) == _only("built")
