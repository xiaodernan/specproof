"""Shared witness-lane nodes for the StateGraph family.

Several witness graphs end their chain with a ``verdict`` node that merely
carries the state forward — the verdict is chosen upstream (by strike/search),
and this node exists so every chain reads intake → strike → verdict → report
→ END. One implementation, one inspectable identity; a copy per lane would
drift and would not be the same verifier.
"""
from __future__ import annotations

from typing import Any


def verdict_node(state: Any) -> Any:
    return state


def verdict_word_hits(text: str, words: tuple[str, ...]) -> list[str]:
    """Report info-only verdict words present in an answer; never grade them.

    Three witness graphs (ask-the-book, next-step, stress-digest) used identical
    copies of this one-line scan with only their word tuple differing. One
    implementation, one identity — the word list stays in each lane, which is
    where the meaning lives.
    """
    return [w for w in words if w in (text or "")]


def sealed_verify(state: Any) -> dict[str, str]:
    """The HELD/DRIFTED seal check shared by two-language sealed lanes.

    next-step and stress-digest carried byte-identical bodies (the ratchet
    caught the copy). Both return the same two-state verdict from the same
    six facts, so there is one decision here, not two.
    """
    ok = bool(state.get("pinned"))
    ok = ok and bool(state.get("packet_identical")) and bool(state.get("messages_shape_ok"))
    if state.get("live_requested"):
        ok = ok and bool(state.get("sealed_zh")) and bool(state.get("sealed_en"))
        ok = ok and "errored" not in state.get("notes", "")
    return {"verdict": "HELD" if ok else "DRIFTED"}


def cli_report(builder: Any) -> int:
    """One CLI entry point for witness graphs that print a verdict + report.

    covenant-witness and exhibit-copilot had identical ``main`` bodies whose
    only difference was the builder they called; the builder is now the
    argument, so the printing decision lives in exactly one place.
    """
    result = builder().invoke({}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0
