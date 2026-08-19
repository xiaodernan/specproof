"""Context compression for the SpecCraft agent (计划书 §7.3) — craft/context.py.

A reusable, deterministic-by-default compressor for the agent's
conversation and tool-result history. Two strategies:

- deterministic (default, zero network):
    1. superseded file reads are dropped — same path, the newest
       observation wins (its digest replaces the older one);
    2. repetitive step transitions collapse into one compact log line;
    3. remaining old tool results are middle-truncated (first+last N
       chars per result, the middle replaced by a fixed marker);
    4. a hard token budget (the repo's TokenBudget remaining, or a
       char-based estimate of ~4 chars per token) drops the oldest
       compressible items that still do not fit.
    Every removal is recorded as a deterministic summary line.
- llm (opt-in): an injected summarize_fn callable rewrites the older
  turns into one compressed block. It is invoked ONLY when configured —
  by default it is None and nothing calls out (no network). When the
  callable fails or does not return a non-empty string, the
  deterministic strategy applies unchanged (honest degradation, never a
  faked summary).

Safety rules (enforced here, never by convention):
- the active task spec is copied verbatim into its own marked block —
  never truncated, never dropped, never reworded;
- gate/verdict results are always preserved verbatim (kind="gate_result",
  protected=True, or content starting with "GATES:");
- system/judge messages are never altered — they pass through untouched;
- the compressed output is wrapped in a COMPRESSED marker block
  (COMPRESSED_MARKER_BEGIN / COMPRESSED_MARKER_END) so downstream code
  can distinguish compressed from raw history via is_compressed_block().

Purity: the compressor holds only immutable configuration; compress()
never mutates its inputs and there is no randomness and no clock — the
same input always yields byte-identical output (the unit tests rely on
that). The hard token budget is enforced on the compressible region
only; protected content is exempt (safety outranks the budget).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from providers.base import LLMMessage
from providers.budget import TokenBudget

from .schemas import ToolResult

COMPRESSED_MARKER_BEGIN = "COMPRESSED CONTEXT BEGIN"
COMPRESSED_MARKER_END = "COMPRESSED CONTEXT END"
COMPRESSION_STRATEGY_DETERMINISTIC = "deterministic"
COMPRESSION_STRATEGY_LLM = "llm"

DEFAULT_CONTEXT_TOKEN_LIMIT = 8000
DEFAULT_KEEP_HEAD_CHARS = 600
DEFAULT_KEEP_TAIL_CHARS = 1200
CHARS_PER_TOKEN = 4

KIND_MESSAGE = "message"
KIND_TOOL_RESULT = "tool_result"
KIND_STEP_TRANSITION = "step_transition"
KIND_GATE_RESULT = "gate_result"
KIND_LLM_SUMMARY = "llm_summary"

PROTECTED_ROLES: frozenset[str] = frozenset({"system", "judge"})

class ContextCompressionError(ValueError):
    """Compressor configuration or input is invalid."""


@dataclass(frozen=True)
class HistoryItem:
    """One history record the compressor consumes.

    kind     — message | tool_result | step_transition | gate_result |
               llm_summary (see the KIND_* constants);
    role     — the message role ("system"/"user"/"assistant"/"tool");
    content  — the verbatim text;
    tool / path / digest / status — optional metadata used by the
               file-read dedupe ("same path, newer digest wins") and by
               the summary lines;
    protected — True keeps the item verbatim regardless of kind/role
               (belt and braces for gate/verdict results).
    """

    role: str
    content: str
    kind: str = KIND_MESSAGE
    tool: str = ""
    path: str = ""
    digest: str = ""
    status: str = ""
    protected: bool = False

    @classmethod
    def from_message(cls, message: LLMMessage) -> HistoryItem:
        """LLMMessage -> HistoryItem (role/content carried over verbatim)."""
        return cls(role=message.role, content=message.content or "", kind=KIND_MESSAGE)

    @classmethod
    def from_tool_result(
        cls,
        result: ToolResult,
        *,
        tool: str = "",
        path: str = "",
        digest: str = "",
    ) -> HistoryItem:
        """ToolResult -> HistoryItem: status/summary/head/tail composed
        deterministically into content. Pass path+digest for file reads so
        the superseded-read dedupe can see them."""
        head_line = f"[{result.status}] {result.summary}"
        if result.exit_code is not None:
            head_line += f" (exit={result.exit_code})"
        parts = [head_line]
        if result.output_head:
            parts.append(f"--- output_head ---\n{result.output_head}")
        if result.output_tail:
            parts.append(f"--- output_tail ---\n{result.output_tail}")
        return cls(
            role="tool",
            content="\n".join(parts),
            kind=KIND_TOOL_RESULT,
            tool=tool,
            path=path,
            digest=digest,
            status=result.status,
        )

    @classmethod
    def gate_verdict(cls, content: str, *, role: str = "tool") -> HistoryItem:
        """Gate/verdict result — always protected, never dropped."""
        return cls(role=role, content=content, kind=KIND_GATE_RESULT, protected=True)


#: Optional-injection strategy: rewrites a sequence of older turns into one
#: compressed block. Default off — the compressor performs no network I/O.
SummarizeFn = Callable[[Sequence[HistoryItem]], str]


@dataclass(frozen=True)
class CompressionReport:
    """Outcome of one compression pass.

    summary_items — one deterministic line per removal/collapse;
    dropped_count — number of original history items removed (superseded
                    reads + collapsed transitions + budget drops);
    estimated_tokens_saved — (tokens of the original compressible items)
                    − (tokens of the surviving compressible items),
                    clamped to ≥ 0;
    estimated_tokens_after — token estimate of the whole marker-wrapped
                    compressed_text (protected + spec + summary included);
    items / protected_items — surviving compressible items and the
                    verbatim protected ones, in original relative order;
    compressed_text — the marker-wrapped block for prompt injection;
    llm_used / llm_note — whether summarize_fn produced the block, and
                    the degradation note when it did not.
    """

    strategy: str
    summary_items: tuple[str, ...]
    dropped_count: int
    estimated_tokens_saved: int
    estimated_tokens_after: int
    items: tuple[HistoryItem, ...]
    protected_items: tuple[HistoryItem, ...]
    compressed_text: str
    llm_used: bool
    llm_note: str = ""


# -- pure helpers -----------------------------------------------------------


def estimate_tokens(text: str, *, chars_per_token: int = CHARS_PER_TOKEN) -> int:
    """Char-based token estimate (same convention as craft/memory.py)."""
    if chars_per_token < 1:
        raise ContextCompressionError(
            f"chars_per_token 必须为正 (收到 {chars_per_token})"
        )
    return max(1, len(text) // chars_per_token + 1)


def truncate_middle(
    text: str, *, keep_head_chars: int, keep_tail_chars: int
) -> tuple[str, int]:
    """Keep first+last N chars of text, replace the middle with a fixed
    marker. Returns (truncated_text, removed_chars); a text shorter than
    head+tail comes back unchanged with removed_chars == 0."""
    if keep_head_chars < 0 or keep_tail_chars < 0:
        raise ContextCompressionError("keep_head_chars/keep_tail_chars 不能为负")
    if len(text) <= keep_head_chars + keep_tail_chars:
        return text, 0
    removed = len(text) - keep_head_chars - keep_tail_chars
    head = text[:keep_head_chars]
    tail = text[-keep_tail_chars:] if keep_tail_chars else ""
    marker = f"\n...[compressed middle: {removed} chars removed]...\n"
    return head + marker + tail, removed


def is_compressed_block(text: str) -> bool:
    """True when text carries the COMPRESSED marker block — downstream code
    uses this to distinguish compressed from raw history."""
    return (
        f"--- {COMPRESSED_MARKER_BEGIN} ---" in text
        and f"--- {COMPRESSED_MARKER_END} " in text
    )


_META_RE = re.compile(r"strategy=(\S+) dropped=(\d+) saved=(\d+) llm=([01])")


def compression_metadata(text: str) -> dict[str, str]:
    """Parse the END-marker metadata of a compressed block; {} when the
    block is absent or malformed (never raises on untrusted text)."""
    end_line = ""
    for line in text.splitlines():
        if f"--- {COMPRESSED_MARKER_END} " in line:
            end_line = line
            break
    if not end_line:
        return {}
    match = _META_RE.search(end_line)
    if match is None:
        return {}
    return {
        "strategy": match.group(1) or "",
        "dropped": match.group(2) or "",
        "saved": match.group(3) or "",
        "llm": match.group(4) or "",
    }


def describe_item(item: HistoryItem) -> str:
    """Compact deterministic item descriptor for summary lines."""
    parts = [item.kind]
    if item.tool:
        parts.append(f"tool={item.tool}")
    if item.path:
        parts.append(f"path={item.path}")
    if item.status:
        parts.append(f"status={item.status}")
    return " ".join(parts)


def render_item(item: HistoryItem) -> str:
    """Deterministic rendering of one item into the compressed block."""
    tags = [f"kind={item.kind}", f"role={item.role}"]
    if item.tool:
        tags.append(f"tool={item.tool}")
    if item.path:
        tags.append(f"path={item.path}")
    if item.digest:
        tags.append(f"digest={item.digest}")
    if item.status:
        tags.append(f"status={item.status}")
    return f"[{' '.join(tags)}]\n{item.content}"


def _short_digest(digest: str) -> str:
    if not digest:
        return "(无)"
    if len(digest) <= 16:
        return digest
    return digest[:16] + "..."


def _clip(text: str, limit: int = 240) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _is_protected(item: HistoryItem) -> bool:
    if item.protected:
        return True
    if item.kind == KIND_GATE_RESULT:
        return True
    if item.role in PROTECTED_ROLES:
        return True
    return item.content.startswith("GATES:")


# -- compressor --------------------------------------------------------------


class ContextCompressor:
    """Deterministic context compressor with an opt-in LLM summarizer.

    Stateless across calls: one instance is safe to reuse, and compress()
    is pure with respect to its inputs (no clock, no randomness, no
    mutation). summarize_fn defaults to None — the deterministic strategy
    runs and no callable is ever invoked.
    """

    def __init__(
        self,
        *,
        token_limit: int = DEFAULT_CONTEXT_TOKEN_LIMIT,
        token_budget: TokenBudget | None = None,
        keep_head_chars: int = DEFAULT_KEEP_HEAD_CHARS,
        keep_tail_chars: int = DEFAULT_KEEP_TAIL_CHARS,
        chars_per_token: int = CHARS_PER_TOKEN,
        summarize_fn: SummarizeFn | None = None,
    ) -> None:
        if token_limit <= 0:
            raise ContextCompressionError(f"token_limit 必须为正 (收到 {token_limit})")
        if keep_head_chars < 0 or keep_tail_chars < 0:
            raise ContextCompressionError("keep_head_chars/keep_tail_chars 不能为负")
        if chars_per_token < 1:
            raise ContextCompressionError(
                f"chars_per_token 必须为正 (收到 {chars_per_token})"
            )
        self._token_limit = token_limit
        self._token_budget = token_budget
        self._head = keep_head_chars
        self._tail = keep_tail_chars
        self._cpt = chars_per_token
        self._summarize_fn = summarize_fn

    def compress(
        self, items: Sequence[HistoryItem], *, task_spec: str = ""
    ) -> CompressionReport:
        """Compress a history into a marker-wrapped block + report.

        items must be in chronological order (oldest first; later items
        win dedupe). The active task spec is passed separately and is
        copied verbatim into its own block — never compressed. The hard
        token budget applies to the compressible region only; protected
        items (gates/verdicts/system/judge) are exempt by design.
        """
        source = list(items)
        for item in source:
            if not isinstance(item, HistoryItem):
                raise ContextCompressionError(
                    f"历史条目必须是 HistoryItem (收到 {type(item).__name__})"
                )
        protected: list[HistoryItem] = []
        compressible: list[HistoryItem] = []
        for item in source:
            if _is_protected(item):
                protected.append(item)
            else:
                compressible.append(item)

        summary: list[str] = []
        before_tokens = sum(
            estimate_tokens(item.content, chars_per_token=self._cpt)
            for item in compressible
        )

        kept, notes = self._dedupe_file_reads(compressible)
        dropped = len(compressible) - len(kept)
        summary.extend(notes)

        pre_collapse = len(kept)
        kept, notes = self._collapse_step_transitions(kept)
        dropped += pre_collapse - len(kept)
        summary.extend(notes)

        strategy = COMPRESSION_STRATEGY_DETERMINISTIC
        llm_used = False
        llm_note = ""
        summarize_fn = self._summarize_fn
        if summarize_fn is not None:
            try:
                block = summarize_fn(kept)
            except Exception as exc:
                llm_note = (
                    f"summarize_fn 调用失败, 降级为确定性压缩: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                if isinstance(block, str) and block.strip():
                    strategy = COMPRESSION_STRATEGY_LLM
                    llm_used = True
                    summary.append(
                        f"[llm_summary] {len(kept)} 条旧记录由 summarize_fn "
                        "压缩为一个摘要块"
                    )
                    kept = [
                        HistoryItem(
                            role="assistant",
                            content=block,
                            kind=KIND_LLM_SUMMARY,
                        )
                    ]
                else:
                    llm_note = "summarize_fn 未返回非空字符串, 降级为确定性压缩"

        kept, notes, budget_dropped = self._apply_token_budget(kept)
        dropped += budget_dropped
        summary.extend(notes)

        after_tokens = sum(
            estimate_tokens(item.content, chars_per_token=self._cpt) for item in kept
        )
        saved = max(0, before_tokens - after_tokens)

        text = self._compose(
            kept,
            protected,
            task_spec,
            summary,
            strategy=strategy,
            dropped=dropped,
            saved=saved,
            llm_used=llm_used,
        )
        return CompressionReport(
            strategy=strategy,
            summary_items=tuple(summary),
            dropped_count=dropped,
            estimated_tokens_saved=saved,
            estimated_tokens_after=estimate_tokens(text, chars_per_token=self._cpt),
            items=tuple(kept),
            protected_items=tuple(protected),
            compressed_text=text,
            llm_used=llm_used,
            llm_note=llm_note,
        )

    # -- deterministic passes --------------------------------------------------

    def _effective_limit(self) -> int:
        """Hard budget: TokenBudget remaining when one is configured,
        otherwise the configured plain token limit."""
        budget = self._token_budget
        if budget is None:
            return self._token_limit
        return max(0, min(self._token_limit, int(budget.remaining)))

    @staticmethod
    def _dedupe_file_reads(
        items: list[HistoryItem],
    ) -> tuple[list[HistoryItem], list[str]]:
        """Drop superseded file reads: for each path only the newest read
        (highest index) survives — its digest wins over older ones."""
        newest_index: dict[str, int] = {}
        for index, item in enumerate(items):
            if item.kind == KIND_TOOL_RESULT and item.path:
                newest_index[item.path] = index
        kept: list[HistoryItem] = []
        notes: list[str] = []
        for index, item in enumerate(items):
            if (
                item.kind == KIND_TOOL_RESULT
                and item.path
                and newest_index[item.path] != index
            ):
                notes.append(
                    f"[dropped] 旧文件读取被同路径新读取取代: {item.path} "
                    f"(旧digest={_short_digest(item.digest)})"
                )
                continue
            kept.append(item)
        return kept, notes

    @staticmethod
    def _collapse_step_transitions(
        items: list[HistoryItem],
    ) -> tuple[list[HistoryItem], list[str]]:
        """Collapse each run of consecutive step transitions into one
        compact log line ('s1 -> s2 -> s3 (x3)')."""
        kept: list[HistoryItem] = []
        notes: list[str] = []
        index = 0
        while index < len(items):
            if items[index].kind != KIND_STEP_TRANSITION:
                kept.append(items[index])
                index += 1
                continue
            end = index
            while end < len(items) and items[end].kind == KIND_STEP_TRANSITION:
                end += 1
            run = items[index:end]
            if len(run) == 1:
                kept.append(run[0])
                index = end
                continue
            collapsed = " -> ".join(item.content for item in run) + f" (x{len(run)})"
            kept.append(
                HistoryItem(
                    role=run[0].role,
                    content=collapsed,
                    kind=KIND_STEP_TRANSITION,
                    tool=run[0].tool,
                )
            )
            notes.append(f"[collapsed] 重复步骤迁移折叠为一行: {_clip(collapsed)}")
            index = end
        return kept, notes

    def _apply_token_budget(
        self, items: list[HistoryItem]
    ) -> tuple[list[HistoryItem], list[str], int]:
        """Hard budget over the compressible region: middle-truncate what
        still fits, drop the oldest items that do not."""
        limit = self._effective_limit()
        kept: list[HistoryItem] = []
        notes: list[str] = []
        dropped = 0
        remaining = limit
        for item in items:
            tokens = estimate_tokens(item.content, chars_per_token=self._cpt)
            if tokens <= remaining:
                kept.append(item)
                remaining -= tokens
                continue
            truncated, removed = truncate_middle(
                item.content,
                keep_head_chars=self._head,
                keep_tail_chars=self._tail,
            )
            truncated_tokens = estimate_tokens(truncated, chars_per_token=self._cpt)
            if truncated != item.content and truncated_tokens <= remaining:
                kept.append(replace(item, content=truncated))
                remaining -= truncated_tokens
                notes.append(
                    f"[truncated] {describe_item(item)} 中段截断: "
                    f"移除 {removed} 字符 (~{tokens - truncated_tokens} tokens)"
                )
                continue
            dropped += 1
            notes.append(
                f"[dropped] {describe_item(item)} 超出硬 token 预算被丢弃 "
                f"(需 ~{truncated_tokens} tokens, 剩余 {remaining}, 上限 {limit})"
            )
        return kept, notes, dropped

    # -- composition -----------------------------------------------------------

    @staticmethod
    def _compose(
        kept: list[HistoryItem],
        protected: list[HistoryItem],
        task_spec: str,
        summary: list[str],
        *,
        strategy: str,
        dropped: int,
        saved: int,
        llm_used: bool,
    ) -> str:
        lines = [f"--- {COMPRESSED_MARKER_BEGIN} ---"]
        if task_spec:
            lines += [
                "",
                "=== ACTIVE TASK SPEC (从未压缩, verbatim) ===",
                task_spec,
                "=== END ACTIVE TASK SPEC ===",
            ]
        if protected:
            lines += [
                "",
                "=== PROTECTED CONTEXT (gate/verdict/system/judge, verbatim) ===",
            ]
            for index, item in enumerate(protected, 1):
                lines.append(f"[{index}] {render_item(item)}")
        if kept:
            lines += ["", "=== COMPRESSED HISTORY ==="]
            for index, item in enumerate(kept, 1):
                lines.append(f"[{index}] {render_item(item)}")
        if summary:
            lines += ["", "=== COMPRESSION SUMMARY ==="]
            lines += [f"- {line}" for line in summary]
        lines += [
            "",
            f"--- {COMPRESSED_MARKER_END} strategy={strategy} dropped={dropped} "
            f"saved={saved} llm={int(llm_used)} ---",
        ]
        return "\n".join(lines)


__all__ = [
    "CHARS_PER_TOKEN",
    "COMPRESSED_MARKER_BEGIN",
    "COMPRESSED_MARKER_END",
    "COMPRESSION_STRATEGY_DETERMINISTIC",
    "COMPRESSION_STRATEGY_LLM",
    "DEFAULT_CONTEXT_TOKEN_LIMIT",
    "DEFAULT_KEEP_HEAD_CHARS",
    "DEFAULT_KEEP_TAIL_CHARS",
    "CompressionReport",
    "ContextCompressionError",
    "ContextCompressor",
    "HistoryItem",
    "SummarizeFn",
    "compression_metadata",
    "estimate_tokens",
    "is_compressed_block",
    "truncate_middle",
]
