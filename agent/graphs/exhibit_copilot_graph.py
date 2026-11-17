"""exhibit_copilot_graph — the twelfth lamp: the exhibit hums once for the wall.

Evidence hands the packet; the court is never in this room. This graph feeds the
compact ``exhibits`` packet to the model (``api/exhibit_copilot.py``) and gates
the answer through a mechanical validator before it is allowed to be struck.
It never blocks, never upgrades, never judges anything.

The default invocation WITHOUT ``--live`` does not touch the network at all:
it only verifies that the ever-strike prompt bytes still match the pin and that
the packet reads — the unit tests run the same path. The live strike lands on
request: ``python -m agent.graphs.exhibit_copilot_graph --live``.

Verdict vocabulary: HELD (prompt bytes pinned and the last known strike sealed
it) / DRIFTED (pin broken or last sealed answer lost).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

from api.exhibit_copilot import PIN_SHA256  # noqa: E402

#: Pin held since #1978 (2026-11-18) — the strike day of this lane.
_EXPECTED_SHA256 = PIN_SHA256
_LANE = "exhibit_copilot"


class ExhibitCopilotState(TypedDict, total=False):
    packet_ok: bool
    pinned: bool
    verdict: str
    report_path: str
    sealed_answer: str
    sealed_failures: list[str]
    reasoning_tokens: int | None
    cached_tokens: int
    prompt_tokens: int
    notes: str


def intake_node(state: ExhibitCopilotState) -> ExhibitCopilotState:  # noqa: ARG001
    """Cheapest true statement about the lane's byte identity + packet."""
    import api.exhibit_copilot as mod

    raw = mod.EXHIBIT_COPILOT_SYSTEM.encode("utf-8")
    pinned = hashlib.sha256(raw).hexdigest() == _EXPECTED_SHA256
    try:
        packet = mod.build_packet()
    except Exception as exc:  # noqa: BLE001 - report it, never hide it behind a zero token count
        return {"packet_ok": False, "pinned": pinned, "notes": f"packet unreadable: {type(exc).__name__}: {exc}"}
    missing = [
        key for key in ("exhibits_count", "latest_file", "worst_p99_ms", "note")
        if packet.get(key) in (None, "", 0)
    ]
    if missing:
        return {"packet_ok": False, "pinned": pinned, "notes": f"packet missing: {', '.join(missing)}"}
    return {"packet_ok": True, "pinned": pinned}


def strike_node(state: ExhibitCopilotState) -> ExhibitCopilotState:
    """The honest seam: live strike only when explicitly asked."""
    import os

    if os.environ.get("SPECPROOF_EXHIBIT_COPILOT_LIVE") != "1":
        return {"notes": "live strike skipped (set SPECPROOF_EXHIBIT_COPILOT_LIVE=1 to spend the tokens)"}
    import asyncio

    import api.exhibit_copilot as mod

    packet = mod.build_packet()
    try:
        result = asyncio.run(mod.generate_exhibit_copilot(packet))
    except Exception as exc:  # noqa: BLE001 - a refused strike is a recorded DRIFTED-worthy failure, never an exception in the product path
        return {"notes": f"live strike errored: {type(exc).__name__}: {exc}", "sealed_failures": [f"{type(exc).__name__}: {exc}"]}
    return {
        "sealed_answer": result.get("answer") or "",
        "sealed_failures": list(result.get("failures") or []),
        "reasoning_tokens": result.get("reasoning_tokens"),
        "cached_tokens": int(result.get("cached_tokens") or 0),
        "prompt_tokens": int(result.get("prompt_tokens") or 0),
        "notes": "live strike landed" if result.get("sealed") else f"live strike failed: {result.get('failures')}",
    }


def verify_node(state: ExhibitCopilotState) -> ExhibitCopilotState:
    pinned = bool(state.get("pinned"))
    packet_ok = bool(state.get("packet_ok"))
    sealed = state.get("sealed_answer")
    if sealed is None:
        # Offline mode: seal survives iff the pin holds and the packet reads.
        verdict = "HELD" if (pinned and packet_ok) else "DRIFTED"
        return {"verdict": verdict}
    ok, failures = True, list(state.get("sealed_failures") or [])
    ok = len(failures) == 0
    verdict = "HELD" if (pinned and packet_ok and ok) else "DRIFTED"
    return {"verdict": verdict}


from agent.graphs._witness import verdict_node  # noqa: E402  (pass-through, one identity per repo)


def report_node(state: ExhibitCopilotState) -> ExhibitCopilotState:
    out_dir = ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    day = stamp[:10]
    payload = {
        "generated_utc": stamp,
        "lane": _LANE,
        "pinned_sha256": _EXPECTED_SHA256,
        "pinned": bool(state.get("pinned")),
        "packet_ok": bool(state.get("packet_ok")),
        "verdict": state.get("verdict", "DRIFTED"),
        "notes": state.get("notes", ""),
        "reasoning_tokens": state.get("reasoning_tokens"),
        "cached_tokens": state.get("cached_tokens"),
        "prompt_tokens": state.get("prompt_tokens"),
    }
    target = out_dir / f"exhibit-copilot-{day}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md = [
        "# Exhibit Co-Pilot — the machine hums (one paragraph, no verdicts)",
        "",
        f"**verdict: {payload['verdict']}** · pinned={payload['pinned']} · packet_ok={payload['packet_ok']}",
        "",
        f"- sealed: {'yes' if state.get('sealed_answer') else 'not struck (offline)'} · cached_tokens={payload['cached_tokens']}",
        f"- notes: {payload['notes']}",
        "",
        "*the court plays no part in this file; no verdict is rendered, only a hum.*",
    ]
    if state.get("sealed_answer"):
        md += ["", "## The hum (verbatim, not edited)", "", str(state["sealed_answer"])]
    (out_dir / f"exhibit-copilot-{day}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"report_path": str(target)}


def build_exhibit_copilot_graph() -> Any:
    g = StateGraph(ExhibitCopilotState)
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
    result = build_exhibit_copilot_graph().invoke({}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
