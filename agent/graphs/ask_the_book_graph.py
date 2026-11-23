"""ask_the_book_graph — the thirteenth lamp: the public lane, witnessed.

The public ``/api/worldbook/ask`` lane is the one surface any anonymous reader
may strike. This lamp watches it: the system sandwiches (codex → covenant →
lane) stay byte-identical, the sanitizer keeps its promise, the fingerprint is
deterministic — and when the operator asks for a live strike, the model answers
in both languages without ever putting on the judge's gown.

Offline (default) the graph does not touch the network: fixtures pin the two
system prompts by SHA-256 so any edit to the lane flips this lamp to DRIFTED
with a human reading the line before anything lands. ``--live`` (or
``SPECPROOF_ASK_THE_BOOK_LIVE=1``) spends two cache-warmed tokens — one zh and
one en probe — and records exactly what the gateway returned (uncached, cached,
reasoning, wall seconds). It never renders an exhibit a verdict: this file has
no pass.

Verdict vocabulary: HELD (prefix bytes pinned, sanitizer deterministic,
messages build, model answered both languages when asked) / DRIFTED (any of
those failed or a live strike errored). The court is never in this room.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

_LANE = "ask_the_book"

#: Pin of the lane's two system prompts (\n---\n separator between zh and en).
#: Any edit to _ZH_SYSTEM or _EN_SYSTEM in api/worldbook_ask.py flips intake to
#: DRIFTED until a human reads the diff and bumps this pin deliberately.
_EXPECTED_PIN_SHA256 = "ae853cb5ea0870fa2537495aa6b6105908824834bc2ad004a944d321aaa9cd4e"

#: The canonical probe questions. Byte-identical across strikes by contract.
_ZH_PROBE = "这本书有没有审判权？"
_EN_PROBE = "Does this book have any verdict authority?"

#: Info-only list. The witness REPORTS these words if the model emits them; it
#: never grades them (a quote from the bible may legitimately contain them).
_INFO_VERDICT_WORDS = ("通过", "未通过", "approved", "release approved", " verdict ")


class AskTheBookState(TypedDict, total=False):
    pinned: bool
    prefix_identity_ok: bool
    sanitizer_ok: bool
    fingerprint_ok: bool
    messages_shape_ok: bool
    sealed_zh: str
    sealed_en: str
    zh_chars: int
    en_chars: int
    zh_cached_tokens: int
    en_cached_tokens: int
    zh_prompt_tokens: int
    en_prompt_tokens: int
    zh_info_hits: list[str]
    en_info_hits: list[str]
    verdict: str
    report_path: str
    notes: str
    live_requested: bool


def _lane_bytes() -> bytes:
    from api import worldbook_ask as mod

    return (mod._ZH_SYSTEM + "\n---\n" + mod._EN_SYSTEM).encode("utf-8")


def intake_node(state: AskTheBookState) -> AskTheBookState:  # noqa: ARG001
    """The cheapest true statements about the lane — no network, no tokens."""
    import api.worldbook_ask as mod

    notes: list[str] = []
    pinned = hashlib.sha256(_lane_bytes()).hexdigest() == _EXPECTED_PIN_SHA256

    clean = mod._sanitize_question(_ZH_PROBE)
    sanitizer_ok = 0 < len(clean) <= mod.MAX_QUESTION_CHARS
    overflow = mod._sanitize_question("x" * (mod.MAX_QUESTION_CHARS * 3))
    sanitizer_ok = sanitizer_ok and len(overflow) == mod.MAX_QUESTION_CHARS

    fp1 = mod.fingerprint("zh", _ZH_PROBE)
    fp2 = mod.fingerprint("zh", _ZH_PROBE)
    fingerprint_ok = fp1 == fp2 and len(fp1) == 64

    msgs = mod.build_ask_messages("zh", clean)
    en_msgs = mod.build_ask_messages("en", _EN_PROBE)
    # Message.content is str | None; the codex sandwich contract pins it to a
    # non-empty system string. Narrow once here so the byte-frozen checks below
    # speak in str terms (a None content fails the prefix checks honestly).
    system_content = msgs[0].content or "" if msgs else ""
    en_system_content = en_msgs[0].content or "" if en_msgs else ""
    shape_ok = (
        bool(msgs)
        and bool(en_msgs)
        and msgs[0].role == "system"
        and en_msgs[0].role == "system"
        and msgs[-1].role == "user"
        and en_msgs[-1].role == "user"
        and system_content.startswith("以下不是虚构")
        and len(system_content) == len(system_content.strip())
    )
    prefix_identity_ok = (
        system_content.startswith("以下不是虚构")
        and en_system_content.startswith("The following is not fiction")
        and system_content == system_content.strip()  # codex is byte-frozen, never re-wrapped
    )
    zh_bytes = len(system_content.encode("utf-8"))
    notes.append(
        f"codex_first sandwich {len(msgs)} msgs; zh codex bytes={zh_bytes}; "
        f"fingerprint={fp1[:12]} (deterministic={fingerprint_ok})"
    )
    if not prefix_identity_ok:  # pragma: no cover - defensive, lane contract holds
        notes.append("codex sandwich differs between invocations — investigate")

    return {
        "pinned": pinned,
        "prefix_identity_ok": prefix_identity_ok,
        "sanitizer_ok": sanitizer_ok,
        "fingerprint_ok": fingerprint_ok,
        "messages_shape_ok": shape_ok,
        "live_requested": os.environ.get("SPECPROOF_ASK_THE_BOOK_LIVE") == "1",
        "notes": "; ".join(notes),
    }


def strike_node(state: AskTheBookState) -> AskTheBookState:
    """The honest seam. Offline by default; --live (or env var) spends tokens."""
    if not state.get("live_requested"):
        return {"notes": (state.get("notes", "") + "; live strike skipped "
                          "(set SPECPROOF_ASK_THE_BOOK_LIVE=1 or pass --live)").strip("; ")}

    import api.worldbook_ask as mod

    async def _one(locale: str, question: str) -> dict[str, Any]:
        try:
            result = await mod.generate_ask_answer(question, locale)
            usage = result.get("usage") or {}
            return {
                "answer": result.get("answer") or "",
                "chars": len((result.get("answer") or "").strip()),
                "cached_tokens": int(
                    usage.get("prompt_cache_hit_tokens") or usage.get("cached_tokens") or 0
                ),
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "info_hits": verdict_word_hits(result.get("answer") or "", _INFO_VERDICT_WORDS),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - a refused strike is a recorded failure, never a product 500
            return {
                "answer": "",
                "chars": 0,
                "cached_tokens": 0,
                "prompt_tokens": 0,
                "info_hits": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

    zh, en = asyncio.run(_one("zh", _ZH_PROBE)), asyncio.run(_one("en", _EN_PROBE))
    notes = list(state.get("notes", "").split("; ")) if state.get("notes") else []
    for row, tag in ((zh, "zh"), (en, "en")):
        if row["error"]:
            notes.append(f"{tag} strike errored: {row['error']}")
        else:
            notes.append(
                f"{tag} strike ok chars={row['chars']} prompt_tokens={row['prompt_tokens']} "
                f"cached_tokens={row['cached_tokens']} info_hits={row['info_hits']}"
            )
    return {
        "sealed_zh": zh["answer"],
        "sealed_en": en["answer"],
        "zh_chars": zh["chars"],
        "en_chars": en["chars"],
        "zh_cached_tokens": zh["cached_tokens"],
        "en_cached_tokens": en["cached_tokens"],
        "zh_prompt_tokens": zh["prompt_tokens"],
        "en_prompt_tokens": en["prompt_tokens"],
        "zh_info_hits": zh["info_hits"],
        "en_info_hits": en["info_hits"],
        "notes": "; ".join(notes),
    }


def verify_node(state: AskTheBookState) -> AskTheBookState:
    ok = bool(state.get("pinned"))
    ok = ok and bool(state.get("sanitizer_ok")) and bool(state.get("messages_shape_ok"))
    ok = ok and bool(state.get("fingerprint_ok"))
    if state.get("live_requested"):
        ok = ok and bool(state.get("sealed_zh")) and bool(state.get("sealed_en"))
        ok = ok and "errored" not in state.get("notes", "")
    return {"verdict": "HELD" if ok else "DRIFTED"}


from agent.graphs._witness import verdict_node, verdict_word_hits  # noqa: E402


def report_node(state: AskTheBookState) -> AskTheBookState:
    env_dir = os.environ.get("SPECPROOF_ASK_THE_BOOK_WITNESS_DIR")
    out_dir = Path(env_dir) if env_dir else ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    day = stamp[:10]
    payload = {
        "generated_utc": stamp,
        "lane": _LANE,
        "pinned_sha256": _EXPECTED_PIN_SHA256,
        "pinned": bool(state.get("pinned")),
        "sanitizer_ok": bool(state.get("sanitizer_ok")),
        "fingerprint_ok": bool(state.get("fingerprint_ok")),
        "messages_shape_ok": bool(state.get("messages_shape_ok")),
        "verdict": state.get("verdict", "DRIFTED"),
        "live_requested": bool(state.get("live_requested")),
        "zh_chars": state.get("zh_chars"),
        "en_chars": state.get("en_chars"),
        "zh_prompt_tokens": state.get("zh_prompt_tokens"),
        "zh_cached_tokens": state.get("zh_cached_tokens"),
        "en_prompt_tokens": state.get("en_prompt_tokens"),
        "en_cached_tokens": state.get("en_cached_tokens"),
        "info_verdict_word_hits_zh": state.get("zh_info_hits"),
        "info_verdict_word_hits_en": state.get("en_info_hits"),
        "notes": state.get("notes", ""),
    }
    target = out_dir / f"ask-the-book-{day}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    zc = payload['zh_cached_tokens'] if payload['zh_cached_tokens'] is not None else 'not struck'
    ec = payload['en_cached_tokens'] if payload['en_cached_tokens'] is not None else 'not struck'

    _live_str = 'yes — zh/en, both cache-key `specproof-worldbook-ask`'
    md = [
        "# Ask-the-Book · the public lane, witnessed (no verdicts, one hum)",
        "",
        f"**verdict: {payload['verdict']}** · pinned={payload['pinned']} · "
        f"sanitizer_ok={payload['sanitizer_ok']} · fingerprint_ok={payload['fingerprint_ok']} · "
        f"messages_shape_ok={payload['messages_shape_ok']}",
        "",
        f"- live strike: {_live_str if payload['live_requested'] else 'not struck (offline)'}",
        f"- zh: {payload['zh_chars'] or 0} chars · "
        f"cached_tokens={zc}",
        f"- en: {payload['en_chars'] or 0} chars · "
        f"cached_tokens={ec}",
        f"- notes: {payload['notes']}",
        f"- info-only verdict-word hits (reported, never graded): "
        f"zh={payload['info_verdict_word_hits_zh']} · en={payload['info_verdict_word_hits_en']}",
        "",
        "*the witness never decides whether an exhibit is green — it watches"
        " the public lane, byte by byte.*",
    ]
    if state.get("sealed_zh"):
        md += ["", "## The zh answer (verbatim, not edited)", "", str(state["sealed_zh"])]
    if state.get("sealed_en"):
        md += ["", "## The en answer (verbatim, not edited)", "", str(state["sealed_en"])]
    (out_dir / f"ask-the-book-witness-{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"report_path": str(target)}


def build_ask_the_book_graph() -> Any:
    g = StateGraph(AskTheBookState)
    g.add_node("intake", intake_node)
    g.add_node("strike", strike_node)
    g.add_node("verify", verify_node)
    g.add_node("verdict", verdict_node)
    g.add_node("report", report_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "strike")
    g.add_edge("strike", "verify")
    g.add_edge("verify", "verdict")
    g.add_edge("verdict", "report")
    g.add_edge("report", END)
    return g.compile()


def main() -> int:
    if "--live" in sys.argv[1:]:
        os.environ["SPECPROOF_ASK_THE_BOOK_LIVE"] = "1"
    result = build_ask_the_book_graph().invoke({}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
