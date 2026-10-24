"""`agent/contract_results.merge_contract_results` 的 id 卫生，必须与 `matrix_policy` 一致。

两个同名函数做的是同一件事（按 contract_id 合并每契约结果）：
- `agent.matrix_policy.merge_contract_results(entries)`（一参，build_matrix 用）的
  docstring 明说「Entries without a non-empty string contract_id are ignored」，
  并且**真的**做了 `raw_id.strip()` + `isinstance(raw_id, str)`，
  `test_matrix_policy.py::test_empty_entries_and_missing_contract_ids_are_ignored`
  还钉了 `"   "` 被忽略；
- `agent.contract_results.merge_contract_results(existing, incoming)`（两参，差分节点用）
  此前只做 `if not cid`，于是 **`"   "` 会变成一条幽灵行**、**`" C-1 "` 与 `"C-1"` 不会合并**、
  非字符串 id 也会被当成键。

本门钉住「两者对哪些 id 算数必须一致」，并把两参版的卫生钉死。
"""

from __future__ import annotations

from typing import Any

from agent.contract_results import merge_contract_results as merge_two_arg
from agent.matrix_policy import merge_contract_results as merge_one_arg


def _ids(rows: list[dict[str, Any]]) -> set[str]:
    return {row["contract_id"] for row in rows}


def test_whitespace_only_id_is_skipped() -> None:
    assert merge_two_arg([{"contract_id": "   ", "result": "PASS"}], []) == []


def test_padded_id_merges_with_unpadded_and_is_normalized() -> None:
    merged = merge_two_arg(
        [{"contract_id": "C-1", "result": "PASS"}],
        [{"contract_id": "  C-1  ", "result": "FAIL"}],
    )
    assert len(merged) == 1
    assert merged[0]["contract_id"] == "C-1"
    assert merged[0]["result"] == "FAIL"


def test_non_string_ids_are_skipped() -> None:
    assert merge_two_arg(
        [
            {"contract_id": 123, "result": "PASS"},
            {"contract_id": None, "result": "FAIL"},
        ],
        [],
    ) == []


def test_parity_with_matrix_policy_on_which_ids_survive() -> None:
    entries: list[dict[str, Any]] = [
        {"contract_id": "C-1", "result": "PASS"},
        {"contract_id": "  C-1  ", "result": "FAIL"},
        {"contract_id": "C-2", "result": "UNVERIFIED"},
        {"contract_id": "   ", "result": "PASS"},
        {"contract_id": "", "result": "FAIL"},
        {"result": "PASS"},
        {"contract_id": 123, "result": "PASS"},
        {"contract_id": None, "result": "PASS"},
    ]
    assert _ids(merge_two_arg(entries, [])) == _ids(merge_one_arg(entries)) == {
        "C-1",
        "C-2",
    }


def test_clean_ids_still_merge_with_priority() -> None:
    merged = merge_two_arg(
        [{"contract_id": "C-1", "result": "PASS"}],
        [{"contract_id": "C-1", "result": "FAIL"}],
    )
    assert merged == [{"contract_id": "C-1", "result": "FAIL"}]
