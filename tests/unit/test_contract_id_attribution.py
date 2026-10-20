"""contract_id attribution: the requirement → experiment → matrix chain (P3-6).

The roadmap's complaint is precise: "让 contract_id 从需求到实验到矩阵
一贯传递，不再用 DIFF-01 作为泛化兜底。"

The concrete failure this closes: when the differential experiment could
NOT run, its result was a single entry with a generic contract id. The
matrix drops results whose contract id is not a compiled contract, so
that entry VANISHED — and a contract with no result reads as "nothing was
found" instead of "the experiment could not run". These tests pin:

- a skipped/error differential names every contract it was meant to
  verify as UNVERIFIED, with the reason;
- the reason reaches the matrix row (not a generic fallback);
- a contract that was never compiled still produces no matrix row.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.nodes.build_matrix import build_matrix_node
from agent.nodes.run_differential import run_differential_node


def _contracts(*ids: str) -> list[dict[str, Any]]:
    return [
        {
            "id": cid,
            "version": 1,
            "requirement": f"requirement for {cid}",
            "checker_type": "http",
        }
        for cid in ids
    ]


def _state(contracts: list[dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "base_workspace": "",
        "head_workspace": "",
        "app_dir": "",
        "changed_symbols": [],
        "generation_record": {},
        "contracts": contracts,
        "generated_tests_path": "",
        "job_id": None,
    }
    state.update(overrides)
    return state


# ── the skipped path ───────────────────────────────────────────────────────


class TestSkippedDifferentialAttributesToContracts:
    def test_every_contract_gets_an_unverified_row(self) -> None:
        out = run_differential_node(_state(_contracts("AUTH-01", "UNIQUE-01")))  # type: ignore[arg-type]
        results = out["contract_results"]
        assert {r["contract_id"] for r in results} == {"AUTH-01", "UNIQUE-01"}
        assert all(r["result"] == "UNVERIFIED" for r in results)

    def test_the_row_carries_the_reason(self) -> None:
        out = run_differential_node(_state(_contracts("AUTH-01")))  # type: ignore[arg-type]
        row = out["contract_results"][0]
        assert "Workspace not prepared" in row["details"]
        assert row["experiment"] == "generated_test_differential"

    def test_no_contracts_means_no_rows(self) -> None:
        """Nothing was compiled ⇒ nothing to be unverified about."""
        out = run_differential_node(_state([]))  # type: ignore[arg-type]
        assert out["contract_results"] == []

    def test_a_contract_without_an_id_is_skipped(self) -> None:
        out = run_differential_node(_state([{"id": ""}]))  # type: ignore[arg-type]
        assert out["contract_results"] == []


# ── the matrix consumes the reason ─────────────────────────────────────────


class TestMatrixCarriesTheReason:
    def _matrix(self, state: dict[str, Any]) -> dict[str, Any]:
        out = build_matrix_node(state)  # type: ignore[arg-type]
        return out["matrix"]

    def test_the_row_is_unverified_with_the_specific_reason(self) -> None:
        state = _state(_contracts("AUTH-01"))
        diff = run_differential_node(state)  # type: ignore[arg-type]
        state = dict(state)
        state["diff_results"] = diff["diff_results"]
        state["contract_results"] = diff["contract_results"]
        matrix = self._matrix(state)
        row = next(r for r in matrix["rows"] if r["contract_id"] == "AUTH-01")
        assert row["result"] == "UNVERIFIED"
        assert "Workspace not prepared" in row["unverified_reason"]

    def test_the_generic_fallback_is_used_only_when_nothing_specific_said_why(
        self,
    ) -> None:
        """With an experiment name but no specific reason, the fallback is the
        INCONCLUSIVE one — the experiment WAS scheduled, it just produced no
        decidable evidence. Only a row with no experiment at all gets the
        "no experiment produced a result" wording.
        """
        state = _state(_contracts("AUTH-01"))
        state["contract_results"] = [{
            "contract_id": "AUTH-01",
            "result": "UNVERIFIED",
            "experiment": "generated_test_differential",
            "evidence_ref": "",
        }]
        matrix = self._matrix(state)
        row = next(r for r in matrix["rows"] if r["contract_id"] == "AUTH-01")
        assert "未得到可判定证据" in row["unverified_reason"]

    def test_no_experiment_at_all_uses_the_no_experiment_wording(self) -> None:
        state = _state(_contracts("AUTH-01"))
        state["contract_results"] = [{
            "contract_id": "AUTH-01",
            "result": "UNVERIFIED",
            "experiment": "",
            "evidence_ref": "",
        }]
        matrix = self._matrix(state)
        row = next(r for r in matrix["rows"] if r["contract_id"] == "AUTH-01")
        assert "没有任何实验产出结果" in row["unverified_reason"]

    def test_a_contract_never_compiled_produces_no_row(self) -> None:
        state = _state(_contracts("AUTH-01"))
        state["contract_results"] = [{
            "contract_id": "NOT-COMPILED",
            "result": "UNVERIFIED",
            "experiment": "x",
            "evidence_ref": "",
        }]
        matrix = self._matrix(state)
        assert all(r["contract_id"] != "NOT-COMPILED" for r in matrix["rows"])


# ── the reason survives the merge ──────────────────────────────────────────


def test_the_longest_specific_reason_wins() -> None:
    """Deterministic pick, never the entry order."""
    from agent.matrix_policy import _merged_unverified_reason

    group = [
        {"details": "short"},
        {"details": "a much longer and more specific reason"},
        {"details": "short"},
    ]
    assert _merged_unverified_reason(group) == "a much longer and more specific reason"


def test_no_details_means_no_specific_reason() -> None:
    from agent.matrix_policy import _merged_unverified_reason

    assert _merged_unverified_reason([{"details": ""}, {}]) == ""


@pytest.mark.parametrize("entry", [{}, {"details": "   "}, {"details": None}])
def test_blank_details_are_not_a_reason(entry: dict[str, Any]) -> None:
    from agent.matrix_policy import _merged_unverified_reason

    assert _merged_unverified_reason([entry]) == ""
