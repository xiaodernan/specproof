"""`agent/contract_results.merge_contract_results` 的合并语义（PASS/FAIL/UNVERIFIED）。

这个模块存在的理由写在它自己的 docstring 里：LangGraph 按 channel 合并节点返回值，
后一个节点返回的 list 会**替换**前一个 —— 没有显式合并时，差分节点会把静态检查结果
擦掉，真实的 PASS/FAIL 行到矩阵阶段变成 UNVERIFIED。所以这把合并尺子一旦回归，
**不会报错**，只会把「有结论」悄悄变成「没结论」。

`test_checker_fixes.py` 已经钉了两条（FAIL 压过 PASS、合并不能丢掉其它契约）。
本门补上**没被钉住**的那几条：
1. FAIL 压过 PASS 的两个方向（既有的只测了「旧 PASS + 新 FAIL」）；
2. PASS 压过 UNVERIFIED 的两个方向；
3. **平局时后者胜**（`>=` 而非 `>`）—— 代码注释明说这是有意的：后者通常带着更强的证据
   （差分 sha256 vs 静态 finding id）；
4. 缺失 / 空 `contract_id` 的条目被丢弃；
5. 返回的是**副本**，改合并结果不会污染输入（节点状态里的原 dict 不该被就地改）；
6. 顺序按 `contract_id` **首次出现**排列；
7. 未知 `result`（或缺失 `result`）排在最末，输给任何已知结果。

只加测试，`agent/contract_results.py` 一字未动。
"""

from __future__ import annotations

from typing import Any

from agent.contract_results import merge_contract_results


def _row(cid: str, result: str, **extra: Any) -> dict[str, Any]:
    return {"contract_id": cid, "result": result, **extra}


# ── 优先级：FAIL > PASS > UNVERIFIED ───────────────────────────────────


def test_fail_beats_pass_in_both_orders() -> None:
    # 旧 FAIL + 新 PASS：FAIL 留下
    merged = merge_contract_results([_row("C-1", "FAIL")], [_row("C-1", "PASS")])
    assert merged == [_row("C-1", "FAIL")]
    # 旧 PASS + 新 FAIL：FAIL 留下
    merged = merge_contract_results([_row("C-1", "PASS")], [_row("C-1", "FAIL")])
    assert merged == [_row("C-1", "FAIL")]


def test_pass_beats_unverified_in_both_orders() -> None:
    merged = merge_contract_results(
        [_row("C-1", "UNVERIFIED")], [_row("C-1", "PASS")]
    )
    assert merged == [_row("C-1", "PASS")]
    merged = merge_contract_results(
        [_row("C-1", "PASS")], [_row("C-1", "UNVERIFIED")]
    )
    assert merged == [_row("C-1", "PASS")]


# ── 平局：后者胜（有意的契约，代码注释写明了理由） ─────────────────────


def test_tie_on_pass_lets_the_later_experiment_win() -> None:
    merged = merge_contract_results(
        [_row("C-1", "PASS", evidence="static-finding-id")],
        [_row("C-1", "PASS", evidence="differential-sha256")],
    )
    assert merged == [_row("C-1", "PASS", evidence="differential-sha256")]


def test_tie_on_fail_lets_the_later_experiment_win() -> None:
    merged = merge_contract_results(
        [_row("C-1", "FAIL", evidence="static")],
        [_row("C-1", "FAIL", evidence="differential")],
    )
    assert merged == [_row("C-1", "FAIL", evidence="differential")]


def test_tie_on_unverified_also_lets_the_later_win() -> None:
    merged = merge_contract_results(
        [_row("C-1", "UNVERIFIED", reason="no-workspace")],
        [_row("C-1", "UNVERIFIED", reason="no-differential")],
    )
    assert merged == [_row("C-1", "UNVERIFIED", reason="no-differential")]


# ── 键：缺失 / 空 contract_id 被丢弃 ──────────────────────────────────


def test_missing_or_empty_contract_id_is_skipped() -> None:
    merged = merge_contract_results(
        [{"result": "PASS"}, {"contract_id": "", "result": "FAIL"}, _row("C-1", "PASS")],
        [],
    )
    # 只钉 falsy id（缺失 / 空串）被丢弃。**不钉**「纯空白 id」（如 "   "）：
    # 现状 `if not cid` 会把它当成合法键留下，这是疑似缺陷（见 #398 队列），
    # 钉住它等于把缺陷写成契约，所以这里刻意不测。
    assert merged == [_row("C-1", "PASS")]


# ── 返回副本，不污染输入 ───────────────────────────────────────────────


def test_result_rows_are_copies_not_aliases() -> None:
    existing = [_row("C-1", "PASS", evidence="old")]
    incoming: list[dict[str, Any]] = []
    merged = merge_contract_results(existing, incoming)
    merged[0]["evidence"] = "mutated"
    assert existing[0]["evidence"] == "old"


# ── 顺序：按 contract_id 首次出现 ──────────────────────────────────────


def test_order_follows_first_appearance() -> None:
    merged = merge_contract_results(
        [_row("B", "PASS"), _row("A", "PASS")],
        [_row("A", "FAIL"), _row("C", "PASS")],
    )
    assert [r["contract_id"] for r in merged] == ["B", "A", "C"]
    # A 被 FAIL 覆盖，但位置仍在 B 之后
    assert merged[1] == _row("A", "FAIL")


# ── 未知 / 缺失 result 排最末 ──────────────────────────────────────────


def test_unknown_result_loses_to_any_known_result() -> None:
    # 旧 UNVERIFIED + 新未知：旧留下
    merged = merge_contract_results(
        [_row("C-1", "UNVERIFIED")], [_row("C-1", "SOMETHING_NEW")]
    )
    assert merged == [_row("C-1", "UNVERIFIED")]
    # 旧未知 + 新 UNVERIFIED：新留下
    merged = merge_contract_results(
        [_row("C-1", "SOMETHING_NEW")], [_row("C-1", "UNVERIFIED")]
    )
    assert merged == [_row("C-1", "UNVERIFIED")]


def test_missing_result_key_ranks_lowest() -> None:
    merged = merge_contract_results(
        [{"contract_id": "C-1", "evidence": "no-result-key"}],
        [_row("C-1", "UNVERIFIED")],
    )
    assert merged == [_row("C-1", "UNVERIFIED")]
