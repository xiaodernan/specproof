"""next_step_graph — the fourteenth lamp: the book reads its own ledger.

The ``/next-step/advice`` lane differs from every other public lane in one
respect: its packet is derived from the repo tree itself — commits, ledger
sections, worldbook volumes, library pairs, chronicle entries, unit-test
file count. This lamp watches the lane: byte-pinned prompts, a deterministic
packet, one public endpoint, one booking party — the book.

Offline (default) the graph performs no network at all: it pins the two lane
prompts by SHA-256 and re-derives the packet twice to prove determinism.
``--live`` (or ``SPECPROOF_NEXT_STEP_LIVE=1``) spends the two strikes and
records exactly what the gateway returned — cached bytes, wall seconds,
chars, info-only word hits; it never hands down a verdict on anything.

Verdict vocabulary: HELD / DRIFTED — the court is never in this room.
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

_LANE = "next_step_advice"

#: Pin of the lane's two prompts. Any edit to _PROMPT_ZH or _PROMPT_EN flips
#: the lamp to DRIFTED until a human reads and bumps the pin deliberately.
_EXPECTED_PIN_SHA256 = "3e3bcd6dbc8675548b45c7bfcf645878056494ba73d186b1da49d3cd6da5d5cf"

_INFO_VERDICT_WORDS = ("通过", "未通过", "approved", "verdict")


class NextStepState(TypedDict, total=False):
    pinned: bool
    packet_identical: bool
    messages_shape_ok: bool
    notes: str
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
    live_requested: bool
    pin_sha256: str


def _lane_pin() -> str:
    from api import next_step_advice as mod

    return hashlib.sha256((mod._PROMPT_ZH + "\n---\n" + mod._PROMPT_EN).encode("utf-8")).hexdigest()


def intake_node(state: NextStepState) -> NextStepState:  # noqa: ARG001
    import api.next_step_advice as mod

    notes: list[str] = []
    pin = _lane_pin()
    pinned = pin == _EXPECTED_PIN_SHA256

    packet_identical = False
    try:
        p1 = mod.build_next_step_packet()
        p2 = mod.build_next_step_packet()
        packet_identical = p1 == p2 and bool(p1)
        notes.append(
            f"packet keys={sorted(p1)}; commits={p1.get('commits')} "
            f"chronicle={p1.get('chronicle_entries')} worldbooks={p1.get('worldbooks_volumes')}"
        )
    except Exception as exc:  # noqa: BLE001 - packet unreadable is a finding, not a verdict
        notes.append(f"packet unreadable: {type(exc).__name__}: {exc}")

    messages_shape_ok = False
    try:
        packet = mod.build_next_step_packet()
        packet_text = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        zh_msgs = mod._prompt("zh", packet_text)
        en_msgs = mod._prompt("en", packet_text)
        messages_shape_ok = (
            zh_msgs[0].role == "system" and en_msgs[0].role == "system"
            and zh_msgs[-1].role == "user" and en_msgs[-1].role == "user"
        )
        zb = len((zh_msgs[0].content or "").encode("utf-8"))
        eb = len((en_msgs[0].content or "").encode("utf-8"))
        notes.append(f"codex bytes zh={zb} en={eb}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"messages unreadable: {type(exc).__name__}: {exc}")

    return {
        "pinned": pinned,
        "pin_sha256": pin,
        "packet_identical": packet_identical,
        "messages_shape_ok": messages_shape_ok,
        "live_requested": os.environ.get("SPECPROOF_NEXT_STEP_LIVE") == "1",
        "notes": "; ".join(notes),
    }


def _verdict_word_hits(text: str) -> list[str]:
    return [w for w in _INFO_VERDICT_WORDS if w in (text or "")]


def strike_node(state: NextStepState) -> NextStepState:
    if not state.get("live_requested"):
        return {"notes": (state.get("notes", "") + "; live strike skipped "
                          "(set SPECPROOF_NEXT_STEP_LIVE=1 or pass --live)").strip("; ")}

    import api.next_step_advice as mod

    async def _one(locale: str) -> dict[str, Any]:
        try:
            result = await mod.generate_next_step_advice(locale)
            usage = result.get("usage") or {}
            return {
                "answer": result.get("advice") or "",
                "chars": len((result.get("advice") or "").strip()),
                "cached_tokens": int(
                    usage.get("prompt_cache_hit_tokens") or usage.get("cached_tokens") or 0
                ),
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "info_hits": _verdict_word_hits(result.get("advice") or ""),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "answer": "",
                "chars": 0,
                "cached_tokens": 0,
                "prompt_tokens": 0,
                "info_hits": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

    zh, en = asyncio.run(_one("zh")), asyncio.run(_one("en"))
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


def verify_node(state: NextStepState) -> NextStepState:
    ok = bool(state.get("pinned"))
    ok = ok and bool(state.get("packet_identical")) and bool(state.get("messages_shape_ok"))
    if state.get("live_requested"):
        ok = ok and bool(state.get("sealed_zh")) and bool(state.get("sealed_en"))
        ok = ok and "errored" not in state.get("notes", "")
    return {"verdict": "HELD" if ok else "DRIFTED"}


from agent.graphs._witness import verdict_node  # noqa: E402  (pass-through, one identity per repo)


def report_node(state: NextStepState) -> NextStepState:
    out_dir = Path(os.environ.get("SPECPROOF_NEXT_STEP_WITNESS_DIR") or ROOT / "docs" / "evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    day = stamp[:10]
    payload = {
        "generated_utc": stamp,
        "lane": _LANE,
        "pinned_sha256": state.get("pin_sha256") or _EXPECTED_PIN_SHA256,
        "pinned": bool(state.get("pinned")),
        "packet_identical": bool(state.get("packet_identical")),
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
    target = out_dir / f"next-step-advice-{day}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    zc = payload['zh_cached_tokens'] if payload['zh_cached_tokens'] is not None else 'not struck'
    ec = payload['en_cached_tokens'] if payload['en_cached_tokens'] is not None else 'not struck'

    _live_str = 'yes — zh/en, cache-key `specproof-next-step-advice`'
    md = [
        "# Next-Step Advice · the book reads its own ledger (no verdicts, one hum)",
        "",
        f"**verdict: {payload['verdict']}** · pinned={payload['pinned']} · "
        f"packet_identical={payload['packet_identical']} · "
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
    (out_dir / f"next-step-advice-witness-{day}.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8")
    return {"report_path": str(target)}


def build_next_step_graph() -> Any:
    g = StateGraph(NextStepState)
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
        os.environ["SPECPROOF_NEXT_STEP_LIVE"] = "1"
    result = build_next_step_graph().invoke({}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
