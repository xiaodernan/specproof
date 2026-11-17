"""night_watch_graph.py — the vow in one compiled line: evidence + purity + audit.

Composes the three existing StateGraphs into one end-to-end night's watch.
Each lane is struck independently and in sequence, and the watch closes only when all three are green.
A lane that throws, a lane that degrades, a lane that cannot find its art is CRACKED — never a quiet degradation.

Usage:
    python agent/graphs/night_watch_graph.py [evidence_dir]
Writes: docs/evidence/night-watch.md and docs/evidence/night-watch.json (git-tracked).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from datetime import UTC, datetime
from typing import Any

from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph

EVID = ROOT / "docs" / "evidence"


def _evidence_dir(state: "NightWatchState") -> Path:
    value: object = state.get("evidence_dir")
    return Path(value) if isinstance(value, str) and value else EVID


class NightWatchState(TypedDict, total=False):
    evidence_dir: str
    evidence_verdict: str
    evidence_summary: str
    purity_verdict: str
    purity_summary: str
    audit_verdict: str
    audit_summary: str
    findings: list[str]
    verdict: str
    report_path: str
    summary: str
    generated_utc: str


def _veto(verdict: str, ok_value: str) -> bool:
    return str(verdict).strip().upper() != ok_value


def evidence_node(state: NightWatchState) -> NightWatchState:
    from agent.graphs.evidence_graph import build_evidence_review_graph
    try:
        result = build_evidence_review_graph().invoke({"evidence_dir": str(_evidence_dir(state))}) or {}
    except Exception as exc:  # noqa: BLE001 - a lane that throws is a cracked watch
        return {"evidence_verdict": "CRACKED", "evidence_summary": f"evidence graph raised: {type(exc).__name__}: {exc}", "findings": (state.get("findings") or []) + ["evidence lane: unhandled error"]}
    verdict = str(result.get("verdict") or "CRACKED").upper()
    return {
        "evidence_verdict": verdict,
        "evidence_summary": str(result.get("summary", f"verdict={verdict}")),
        "findings": (state.get("findings") or []) + (["evidence lane reported no verdict"] if verdict == "OK" else []),
    }


def purity_node(state: NightWatchState) -> NightWatchState:
    from agent.graphs.purity_graph import build_purity_graph
    try:
        result = build_purity_graph().invoke({}) or {}
    except Exception as exc:  # noqa: BLE001
        return {"purity_verdict": "CRACKED", "purity_summary": f"purity graph raised: {type(exc).__name__}: {exc}", "findings": (state.get("findings") or []) + ["purity lane: unhandled error"]}
    summary = str(result.get("summary") or "")
    verdict = "CLEAR" if "CLEAR" in summary.upper() else ("CRACKED" if "CRACKED" in summary.upper() else "CRACKED")
    return {
        "purity_verdict": verdict,
        "purity_summary": summary or f"purity verdict={verdict}",
        "findings": (state.get("findings") or []) + (["purity lane reported nothing"] if not summary.strip() else []),
    }


def audit_node(state: NightWatchState) -> NightWatchState:
    from agent.graphs.auditor_graph import build_audit_chain_graph
    try:
        result = build_audit_chain_graph().invoke({}) or {}
    except Exception as exc:  # noqa: BLE001
        return {"audit_verdict": "CRACKED", "audit_summary": f"audit chain raised: {type(exc).__name__}: {exc}", "findings": (state.get("findings") or []) + ["audit lane: unhandled error"]}
    summary = str(result.get("summary") or "")
    verdict = "CLEAR" if "CLEAR" in summary.upper() else "CRACKED"
    return {
        "audit_verdict": verdict,
        "audit_summary": summary or f"audit chain verdict={verdict}",
        "findings": (state.get("findings") or []) + (["audit lane reported no verdict"] if not summary.strip() else []),
    }


def verdict_node(state: NightWatchState) -> NightWatchState:
    gates = (
        ("evidence", _veto(state.get("evidence_verdict", "CRACKED"), "OK")),
        ("purity", _veto(state.get("purity_verdict", "CRACKED"), "CLEAR")),
        ("audit", _veto(state.get("audit_verdict", "CRACKED"), "CLEAR")),
    )
    cracked = [name for name, bad in gates if bad]
    verdict = "CRACKED" if cracked else "CLEAR"
    return {
        "verdict": verdict,
        "findings": (state.get("findings") or []) + [f"{name} lane: not jade" for name in cracked],
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def report_node(state: NightWatchState) -> NightWatchState:
    out_dir = _evidence_dir(state)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "night-watch.md"
    sidecar = out_dir / "night-watch.json"
    generated = datetime.now(UTC).isoformat(timespec="seconds")
    rows = [
        "# Night Watch",
        "",
        f"**verdict: {state.get('verdict', 'CRACKED')}** · struck {generated}",
        "",
        "| lane | raw summary |",
        "|---|---|",
        f"| evidence | {state.get('evidence_summary', '—')} |",
        f"| purity   | {state.get('purity_summary', '—')} |",
        f"| audit    | {state.get('audit_summary', '—')} |",
        "",
        "CLAR rules: evidence must be OK · purity must be CLEAR · audit must be CLEAR. Anything else is CRACKED — and CRACKED is printed, not hidden.",
    ]
    if state.get("findings"):
        rows += ["", "findings:"]
        rows += [f"- {finding}" for finding in state["findings"]]
    report.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    sidecar.write_text(json.dumps({
        "version": 1,
        "generated_utc": generated,
        "verdict": state.get("verdict", "CRACKED"),
        "lanes": {
            "evidence": state.get("evidence_verdict"),
            "purity": state.get("purity_verdict"),
            "audit": state.get("audit_verdict"),
        },
        "findings": state.get("findings", []),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return {
        "report_path": str(report),
        "summary": f"verdict={state.get('verdict', 'CRACKED')} evidence={state.get('evidence_verdict')} purity={state.get('purity_verdict')} audit={state.get('audit_verdict')}",
    }


def build_night_watch_graph() -> Any:
    graph = StateGraph(NightWatchState)
    for name, fn in [
        ("evidence", evidence_node),
        ("purity", purity_node),
        ("audit", audit_node),
        ("verdict", verdict_node),
        ("report", report_node),
    ]:
        graph.add_node(name, fn)
    graph.set_entry_point("evidence")
    graph.add_edge("evidence", "purity")
    graph.add_edge("purity", "audit")
    graph.add_edge("audit", "verdict")
    graph.add_edge("verdict", "report")
    graph.add_edge("report", END)
    return graph.compile()


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else str(EVID)
    app = build_night_watch_graph()
    result = app.invoke({"evidence_dir": out})
    print(result.get("summary"))
