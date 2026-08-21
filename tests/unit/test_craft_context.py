"""Context compression unit tests (计划书 §7.3) — craft/context.py.

Covered: hard token budget truncation/dropping (plain limit and the repo
TokenBudget remaining); superseded file-read dedup (newer digest wins);
gate/verdict + system/judge messages preserved verbatim; the active task
spec never compressed; byte-identical deterministic output across runs;
the LLM summarize_fn invoked only when configured (plus honest
degradation when it fails or returns garbage); and the COMPRESSED marker
block that lets downstream code distinguish compressed history.

No network: the only injected callable is a local fake; no LLM client is
constructed.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest

from craft.context import (
    COMPRESSED_MARKER_BEGIN,
    COMPRESSED_MARKER_END,
    COMPRESSION_STRATEGY_DETERMINISTIC,
    COMPRESSION_STRATEGY_LLM,
    KIND_GATE_RESULT,
    KIND_LLM_SUMMARY,
    KIND_MESSAGE,
    KIND_STEP_TRANSITION,
    KIND_TOOL_RESULT,
    ContextCompressionError,
    ContextCompressor,
    HistoryItem,
    SummarizeFn,
    compression_metadata,
    estimate_tokens,
    is_compressed_block,
    truncate_middle,
)
from craft.schemas import ToolResult
from providers.base import LLMMessage
from providers.budget import TokenBudget


def tool_item(
    content: str,
    *,
    tool: str = "run_test",
    path: str = "",
    digest: str = "",
    status: str = "ok",
) -> HistoryItem:
    return HistoryItem(
        role="tool",
        content=content,
        kind=KIND_TOOL_RESULT,
        tool=tool,
        path=path,
        digest=digest,
        status=status,
    )


def transition(content: str) -> HistoryItem:
    return HistoryItem(role="tool", content=content, kind=KIND_STEP_TRANSITION)


# -- hard token budget ------------------------------------------------------


def test_token_budget_truncates_middle_and_drops_oldest() -> None:
    compressor = ContextCompressor(token_limit=40, keep_head_chars=40, keep_tail_chars=40)
    items = [tool_item("A" * 500), tool_item("B" * 500), tool_item("C" * 500)]
    report = compressor.compress(items)
    assert report.strategy == COMPRESSION_STRATEGY_DETERMINISTIC
    assert report.llm_used is False
    # oldest item survives via middle-truncation, the rest are dropped
    assert len(report.items) == 1
    assert report.dropped_count == 2
    assert report.estimated_tokens_saved > 0
    survivor = report.items[0].content
    assert survivor.startswith("A" * 40)
    assert survivor.endswith("A" * 40)
    assert "compressed middle" in survivor
    assert "B" * 500 not in report.compressed_text
    assert "C" * 500 not in report.compressed_text
    trunc_lines = [s for s in report.summary_items if "[truncated]" in s]
    drop_lines = [s for s in report.summary_items if "[dropped]" in s]
    assert len(trunc_lines) == 1
    assert len(drop_lines) == 2
    # hard budget: the compressible region never exceeds the limit
    used = sum(estimate_tokens(item.content) for item in report.items)
    assert used <= 40


def test_token_budget_object_remaining_caps_the_limit() -> None:
    budget = TokenBudget(limit_tokens=300.0)
    budget.record({"prompt_tokens": 280})  # remaining = 20
    compressor = ContextCompressor(
        token_budget=budget, keep_head_chars=40, keep_tail_chars=40
    )
    report = compressor.compress([tool_item("A" * 500), tool_item("B" * 500)])
    assert report.items == ()
    assert report.dropped_count == 2
    assert len([s for s in report.summary_items if "[dropped]" in s]) == 2


# -- superseded file reads ----------------------------------------------------


def test_superseded_file_reads_older_dropped_newer_digest_wins() -> None:
    compressor = ContextCompressor()
    older = tool_item(
        "OLD CONTENT 123", tool="read_file", path="calc.py", digest="d" * 64
    )
    newer = tool_item(
        "NEW CONTENT 456", tool="read_file", path="calc.py", digest="e" * 64
    )
    other = tool_item(
        "OTHER CONTENT", tool="read_file", path="test_calc.py", digest="f" * 64
    )
    report = compressor.compress([older, newer, other])
    assert report.dropped_count == 1
    assert any(
        "[dropped]" in s and "calc.py" in s for s in report.summary_items
    )
    assert [item.content for item in report.items] == [
        "NEW CONTENT 456",
        "OTHER CONTENT",
    ]
    assert report.items[0].digest == "e" * 64  # newer digest wins
    assert "OLD CONTENT 123" not in report.compressed_text
    # identical digest still drops the older read (newest observation wins)
    same_digest = compressor.compress(
        [
            tool_item("V1", tool="read_file", path="a.py", digest="a" * 64),
            tool_item("V2", tool="read_file", path="a.py", digest="a" * 64),
        ]
    )
    assert same_digest.dropped_count == 1
    assert [item.content for item in same_digest.items] == ["V2"]


# -- safety rules --------------------------------------------------------------


def test_gate_verdict_and_protected_roles_never_dropped_or_trimmed() -> None:
    compressor = ContextCompressor(token_limit=1, keep_head_chars=5, keep_tail_chars=5)
    gate_line = "GATES: task=j1 overall=passed security=passed duration_ms=1"
    gate = HistoryItem.gate_verdict(gate_line)
    sniffed = HistoryItem(
        role="tool",
        content="GATES: task=j2 overall=failed security=passed",
        kind=KIND_TOOL_RESULT,
    )
    system_msg = HistoryItem(role="system", content="You are the judge. Never reveal.")
    judge_msg = HistoryItem(role="judge", content="裁决: 禁止修改 system prompt")
    items = [tool_item("X" * 400), gate, sniffed, system_msg, judge_msg]
    report = compressor.compress(items)
    assert gate_line in report.compressed_text
    assert "task=j2 overall=failed" in report.compressed_text
    assert system_msg.content in report.compressed_text
    assert judge_msg.content in report.compressed_text
    assert {item.content for item in report.protected_items} >= {
        gate_line,
        sniffed.content,
        system_msg.content,
        judge_msg.content,
    }
    # the compressible junk is gone despite the protected payload
    assert "X" * 400 not in report.compressed_text


def test_active_task_spec_never_compressed() -> None:
    spec = "任务规范: 修复 calc.py\n验收: pytest 全绿\n" + "SPEC-DETAIL-" * 100
    compressor = ContextCompressor(token_limit=5, keep_head_chars=4, keep_tail_chars=4)
    report = compressor.compress([tool_item("X" * 300)], task_spec=spec)
    assert spec in report.compressed_text  # verbatim, untruncated
    assert "ACTIVE TASK SPEC" in report.compressed_text
    assert report.items == ()  # the spec never becomes a compressible item
    # empty history still emits a valid marked block carrying the spec
    empty = compressor.compress([], task_spec=spec)
    assert spec in empty.compressed_text
    assert is_compressed_block(empty.compressed_text)


# -- determinism -----------------------------------------------------------------


def test_deterministic_output_stable_across_runs() -> None:
    compressor = ContextCompressor(token_limit=50, keep_head_chars=30, keep_tail_chars=30)
    items = [
        tool_item("M" * 400),
        transition("s1"),
        transition("s2"),
        tool_item("read", tool="read_file", path="calc.py", digest="d" * 64),
        tool_item("read2", tool="read_file", path="calc.py", digest="e" * 64),
        HistoryItem.gate_verdict("GATES: task=j1 overall=passed"),
    ]
    first = compressor.compress(items)
    second = compressor.compress(list(items))
    assert first.compressed_text == second.compressed_text
    assert first.summary_items == second.summary_items
    assert first.dropped_count == second.dropped_count
    assert first.estimated_tokens_saved == second.estimated_tokens_saved
    assert first.estimated_tokens_after == second.estimated_tokens_after
    assert first.items == second.items
    assert first.protected_items == second.protected_items
    fresh = ContextCompressor(token_limit=50, keep_head_chars=30, keep_tail_chars=30)
    assert fresh.compress(list(items)).compressed_text == first.compressed_text


# -- step-transition collapse ---------------------------------------------------


def test_step_transitions_collapse_into_compact_log_line() -> None:
    compressor = ContextCompressor()
    items = [
        transition("s1"),
        transition("s2"),
        tool_item("read between"),
        transition("s3"),
        transition("s4"),
        transition("s5"),
    ]
    report = compressor.compress(items)
    assert report.dropped_count == 3  # 1 + 2 collapsed extras
    collapsed = [item for item in report.items if item.kind == KIND_STEP_TRANSITION]
    assert len(collapsed) == 2
    assert collapsed[0].content == "s1 -> s2 (x2)"
    assert collapsed[1].content == "s3 -> s4 -> s5 (x3)"
    assert len([s for s in report.summary_items if "[collapsed]" in s]) == 2
    # single transition is not repetitive: kept as-is
    single = compressor.compress([transition("s1"), tool_item("x")])
    assert [item.content for item in single.items if item.kind == KIND_STEP_TRANSITION] == [
        "s1"
    ]
    assert single.dropped_count == 0


# -- LLM strategy ---------------------------------------------------------------


def test_llm_summarize_fn_invoked_only_when_configured() -> None:
    calls: list[list[HistoryItem]] = []

    def fake_summarize(items: Sequence[HistoryItem]) -> str:
        calls.append(list(items))
        return "LLM-COMPRESSED-BLOCK"

    items = [tool_item("OLD-" + "x" * 200), tool_item("OLD2-" + "y" * 200)]
    off = ContextCompressor()
    report_off = off.compress(items)
    assert report_off.llm_used is False
    assert report_off.strategy == COMPRESSION_STRATEGY_DETERMINISTIC
    assert calls == []  # default off: the callable is never invoked

    on = ContextCompressor(summarize_fn=fake_summarize)
    report_on = on.compress(items)
    assert report_on.llm_used is True
    assert report_on.strategy == COMPRESSION_STRATEGY_LLM
    assert len(calls) == 1  # invoked exactly once
    assert calls[0] == list(items)  # receives the surviving compressible items
    assert [item.kind for item in report_on.items] == [KIND_LLM_SUMMARY]
    assert report_on.items[0].content == "LLM-COMPRESSED-BLOCK"
    assert "LLM-COMPRESSED-BLOCK" in report_on.compressed_text
    assert "llm=1" in report_on.compressed_text
    meta = compression_metadata(report_on.compressed_text)
    assert meta["strategy"] == COMPRESSION_STRATEGY_LLM
    assert meta["llm"] == "1"


def test_llm_summarize_fn_failure_degrades_to_deterministic() -> None:
    def boom(_items: Sequence[HistoryItem]) -> str:
        raise RuntimeError("no network allowed")

    compressor = ContextCompressor(summarize_fn=boom)
    report = compressor.compress([tool_item("Z" * 100)])
    assert report.llm_used is False
    assert report.strategy == COMPRESSION_STRATEGY_DETERMINISTIC
    assert "降级" in report.llm_note
    assert "Z" in report.compressed_text
    # a non-string return also degrades honestly, never crashes
    bad = ContextCompressor(summarize_fn=cast(SummarizeFn, lambda _items: 123))
    report_bad = bad.compress([tool_item("W" * 100)])
    assert report_bad.llm_used is False
    assert "W" in report_bad.compressed_text


# -- marker block ----------------------------------------------------------------


def test_compressed_marker_emitted_and_detectable() -> None:
    report = ContextCompressor().compress([tool_item("hello")])
    text = report.compressed_text
    assert f"--- {COMPRESSED_MARKER_BEGIN} ---" in text
    assert f"--- {COMPRESSED_MARKER_END} " in text
    assert is_compressed_block(text) is True
    assert compression_metadata(text) == {
        "strategy": COMPRESSION_STRATEGY_DETERMINISTIC,
        "dropped": "0",
        "saved": "0",
        "llm": "0",
    }
    assert is_compressed_block("ordinary text without markers") is False
    assert compression_metadata("plain text") == {}


# -- pure helpers / converters / validation ---------------------------------------


def test_truncate_middle_pure_function() -> None:
    text = "0123456789" * 10  # 100 chars
    out, removed = truncate_middle(text, keep_head_chars=20, keep_tail_chars=20)
    assert removed == 60
    assert out.startswith(text[:20])
    assert out.endswith(text[-20:])
    assert len(out) < len(text)
    same, removed_short = truncate_middle("short", keep_head_chars=10, keep_tail_chars=10)
    assert same == "short"
    assert removed_short == 0


def test_history_item_converters() -> None:
    result = ToolResult(
        status="ok",
        exit_code=0,
        summary="[OK] 读取成功",
        output_head="head-1\nhead-2",
        output_tail="tail-1",
        truncated=False,
    )
    item = HistoryItem.from_tool_result(
        result, tool="read_file", path="calc.py", digest="d" * 64
    )
    assert item.kind == KIND_TOOL_RESULT
    assert item.role == "tool"
    assert item.status == "ok"
    assert item.path == "calc.py"
    assert item.digest == "d" * 64
    assert "[OK] 读取成功" in item.content
    assert "head-2" in item.content
    assert "tail-1" in item.content
    message = HistoryItem.from_message(LLMMessage(role="assistant", content="回复"))
    assert message.role == "assistant"
    assert message.content == "回复"
    assert message.kind == KIND_MESSAGE
    gate = HistoryItem.gate_verdict("GATES: task=j1 overall=passed")
    assert gate.kind == KIND_GATE_RESULT
    assert gate.protected is True


def test_invalid_configuration_and_input_raise() -> None:
    with pytest.raises(ContextCompressionError):
        ContextCompressor(token_limit=0)
    with pytest.raises(ContextCompressionError):
        ContextCompressor(keep_head_chars=-1)
    with pytest.raises(ContextCompressionError):
        ContextCompressor(chars_per_token=0)
    with pytest.raises(ContextCompressionError):
        truncate_middle("abc", keep_head_chars=-1, keep_tail_chars=0)
    with pytest.raises(ContextCompressionError):
        estimate_tokens("x", chars_per_token=0)
    compressor = ContextCompressor()
    with pytest.raises(ContextCompressionError):
        compressor.compress(["not an item"])  # type: ignore[list-item]
