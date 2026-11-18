"""stress_digest_graph — the fifteenth lamp: the weekly strike gets read aloud.

The weekly-stress workflow archives bare numbers (p99/p95/err_rate, verdict
on a 5000 ms machine floor, an honesty line). Nobody reads them unless this
lamp is lit: byte-pinned prompts, a deterministic packet re-derived twice,
the 5000 ms floor echoed as a fact — never as a decision — and an offline
deterministic rounds table that even a runner with no network can emit.

Offline (default) the graph performs no network: it pins the two lane
prompts by SHA-256, re-derives the packet twice, and renders the offline
digest from the committed evidence file. ``--live`` (or
``SPECPROOF_STRESS_DIGEST_LIVE=1``) additionally spends the two strikes and
records exactly what the gateway returned — cached bytes, wall seconds,
chars, info-only word hits. It never hands down a verdict on anything; the
court is never in this room.
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

_LANE = "stress_digest"

#: Pin of the lane's two prompts. Any edit to _PROMPT_ZH or _PROMPT_EN flips
#: the lamp to DRIFTED until a human reads and bumps the pin deliberately.
_EXPECTED_PIN_SHA256 = "db498ac70d3cc6d05556454db3cc2288fac928b9c8dd5c1523568320a1382c2b"

_INFO_VERDICT_WORDS = ("通过", "未通过", "批准", "阻断", "放行", "approved", "blocked", "verdict")


class StressDigestState(TypedDict, total=False):
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
    from api import stress_digest as mod

    return hashlib.sha256((mod._PROMPT_ZH + "\n---\n" + mod._PROMPT_EN).encode("utf-8")).hexdigest()


def intake_node(state: StressDigestState) -> StressDigestState:  # noqa: ARG001
    import api.stress_digest as mod

    notes: list[str] = []
    pin = _lane_pin()
    pinned = pin == _EXPECTED_PIN_SHA256

    packet_identical = False
    try:
        p1 = mod.build_stress_packet()
        p2 = mod.build_stress_packet()
        packet_identical = p1 == p2 and bool(p1) and not p1.get("error")
        if p1.get("error"):
            notes.append(f"packet: {p1['error']}")
        else:
            notes.append(
                f"packet from {p1['evidence_file']}; worst_p99={p1['worst_p99_ms']}; "
                f"err_rate_any={p1['err_rate_any']}; floor_comparison={p1['floor_comparison']}"
            )
    except Exception as exc:  # noqa: BLE001 - packet unreadable is a finding, not a verdict
        notes.append(f"packet unreadable: {type(exc).__name__}: {exc}")

    messages_shape_ok = False
    try:
        packet = mod.build_stress_packet()
        packet_text = json.dumps(packet, ensure_ascii=False, sort_keys=True)
        zh_msgs = mod._prompt("zh", packet_text)
        en_msgs = mod._prompt("en", packet_text)
        messages_shape_ok = (
            zh_msgs[0].role == "system" and en_msgs[0].role == "system"
            and zh_msgs[-1].role == "user" and en_msgs[-1].role == "user"
        )
        notes.append(f"codex bytes zh={len(zh_msgs[0].content.encode('utf-8'))} en={len(en_msgs[0].content.encode('utf-8'))}")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"messages unreadable: {type(exc).__name__}: {exc}")

    return {
        "pinned": pinned,
        "pin_sha256": pin,
        "packet_identical": packet_identical,
        "messages_shape_ok": messages_shape_ok,
        "live_requested": os.environ.get("SPECPROOF_STRESS_DIGEST_LIVE") == "1",
        "notes": "; ".join(notes),
    }


def _verdict_word_hits(text: str) -> list[str]:
    return [w for w in _INFO_VERDICT_WORDS if w in (text or "")]


def strike_node(state: StressDigestState) -> StressDigestState:
    if not state.get("live_requested"):
        return {"notes": (state.get("notes", "") + "; live strike skipped "
                          "(set SPECPROOF_STRESS_DIGEST_LIVE=1 or pass --live)").strip("; ")}

    import api.stress_digest as mod

    async def _one(locale: str) -> dict[str, Any]:
        try:
            result = await mod.generate_stress_digest(locale)
            usage = result.get("usage") or {}
            return {
                "answer": result.get("digest") or "",
                "chars": len((result.get("digest") or "").strip()),
                "cached_tokens": int(usage.get("prompt_cache_hit_tokens") or usage.get("cached_tokens") or 0),
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "info_hits": _verdict_word_hits(result.get("digest") or ""),
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


def verify_node(state: StressDigestState) -> StressDigestState:
    ok = bool(state.get("pinned"))
    ok = ok and bool(state.get("packet_identical")) and bool(state.get("messages_shape_ok"))
    if state.get("live_requested"):
        ok = ok and bool(state.get("sealed_zh")) and bool(state.get("sealed_en"))
        ok = ok and "errored" not in state.get("notes", "")
    return {"verdict": "HELD" if ok else "DRIFTED"}


from agent.graphs._witness import verdict_node  # noqa: E402  (pass-through, one identity per repo)


def report_node(state: StressDigestState) -> StressDigestState:
    import api.stress_digest as mod

    evidence = os.environ.get("SPECPROOF_STRESS_EVIDENCE")
    out_dir = Path(os.environ.get("SPECPROOF_STRESS_DIGEST_DIR") or ROOT / "docs" / "evidence")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    day = stamp[:10]

    base: str | None = None
    if evidence:
        name = Path(evidence).name  # weekly-<run_id>.json or weekly-2026-11-18.json
        if name.startswith("weekly-") and name.endswith(".json"):
            base = "weekly-" + name[len("weekly-"):-len(".json")] + "-digest"
    base = base or f"stress-digest-{day}"

    packet = mod.build_stress_packet(evidence)
    mode = "live strike zh+en (aizzz gateway)" if state.get("live_requested") else "offline · deterministic table, no model"
    md_text = mod.render_digest_md(
        packet,
        reading_zh=state.get("sealed_zh") or None,
        reading_en=state.get("sealed_en") or None,
        mode=mode,
    )
    (out_dir / f"{base}.md").write_text(md_text, encoding="utf-8")

    payload = {
        "generated_utc": stamp,
        "lane": _LANE,
        "pinned_sha256": state.get("pin_sha256") or _EXPECTED_PIN_SHA256,
        "pinned": bool(state.get("pinned")),
        "packet_identical": bool(state.get("packet_identical")),
        "messages_shape_ok": bool(state.get("messages_shape_ok")),
        "verdict": state.get("verdict", "DRIFTED"),
        "live_requested": bool(state.get("live_requested")),
        "evidence_file": packet.get("evidence_file"),
        "worst_p99_ms": packet.get("worst_p99_ms"),
        "best_p99_ms": packet.get("best_p99_ms"),
        "floor_ms": mod.FLOOR_MS,
        "floor_comparison": packet.get("floor_comparison"),
        "err_rate_any": packet.get("err_rate_any"),
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
    target = out_dir / f"{base}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"report_path": str(target)}


def build_stress_digest_graph() -> Any:
    g = StateGraph(StressDigestState)
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
        os.environ["SPECPROOF_STRESS_DIGEST_LIVE"] = "1"
    result = build_stress_digest_graph().invoke({}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
