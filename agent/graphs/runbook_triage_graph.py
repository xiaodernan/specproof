"""runbook_triage_graph — the tenth lamp: the on-call triage lane, witnessed.

One knock against the /runbook-triage lane: does the model answer with repo-grounded facts,
and does it say INCONCLUSIVE when it cannot? This graph never judges the answer's quality —
it only measures whether the lane answered (CONFIRMED) or honestly refused (INCONCLUSIVE).
Offline by construction when no model is configured; the verdict stays INCONCLUSIVE rather
than a fabricated cause.

Pattern: intake -> strike -> verdict -> report -> END

Usage:
    HTTPS_PROXY=http://127.0.0.1:7897 python agent/graphs/runbook_triage_graph.py

Writes docs/evidence/runbook-triage.{json,md} (git-tracked snapshot).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json  # noqa: E402  (long-lived narrow imports, avoid the guard being mis-parsed)
from typing import Any  # noqa: E402

from langgraph.graph import END, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

from api.runbook_triage import generate_triage  # noqa: E402


class RunbookTriageState(TypedDict, total=False):
    alert: str
    verdict: str
    findings: list[dict[str, Any]]
    agents: list[dict[str, Any]]
    total_tokens_used: int
    generation_time_ms: int
    report_path: str
    notes: str


def intake_node(state: RunbookTriageState) -> RunbookTriageState:
    alert = (state.get("alert") or "").strip() or "SpecproofApiDown"
    return {"alert": alert}


def strike_node(state: RunbookTriageState) -> RunbookTriageState:
    alert = state.get("alert") or "SpecproofApiDown"
    try:
        result = asyncio.run(generate_triage(alert))
    except Exception as exc:  # noqa: BLE001 — the lane is witnessed, never faked green
        return {
            "verdict": "INCONCLUSIVE",
            "notes": f"{type(exc).__name__}: {exc}",
            "agents": [],
            "findings": [],
            "total_tokens_used": 0,
        }
    return {
        "alert": alert,
        "verdict": result.get("verdict", "INCONCLUSIVE"),
        "agents": result.get("agents", []),
        "findings": result.get("findings", []),
        "total_tokens_used": result.get("total_tokens_used", 0),
        "generation_time_ms": result.get("generation_time_ms", 0),
    }


from agent.graphs._witness import (  # noqa: E402
    verdict_node,  # shared pass-through, one identity per repo
)


def report_node(state: RunbookTriageState) -> RunbookTriageState:
    out_dir = ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "alert": state.get("alert"),
        "verdict": state.get("verdict", "INCONCLUSIVE"),
        "agents": state.get("agents", []),
        "findings": state.get("findings", []),
        "total_tokens_used": state.get("total_tokens_used", 0),
        "generation_time_ms": state.get("generation_time_ms", 0),
        "notes": state.get("notes", ""),
    }
    (out_dir / "runbook-triage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Runbook Triage",
        "",
        f"**verdict: {payload['verdict']}** · alert `{payload['alert']}` · generation_time_ms {payload.get('generation_time_ms')}",
        "",
        "## Agents",
        "",
        "| name | role | outcome | tokens |",
        "|---|---|---|---|",
    ]
    for a in payload.get("agents", []):
        md.append(f"| `{a.get('name')}` | {a.get('role')} | {a.get('outcome')} | {a.get('tokens', 0)} |")
    md += ["", "## Findings", ""]
    for f in payload.get("findings", []):
        md.append(f"- **{f.get('role')}** — {f.get('claim')}")
    if not payload.get("findings"):
        md.append("- (empty)")
    if payload.get("notes"):
        md += ["", f"notes: {payload['notes']}"]
    (out_dir / "runbook-triage.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"report_path": str(out_dir / "runbook-triage.md")}


def build_runbook_triage_graph() -> Any:
    g = StateGraph(RunbookTriageState)
    g.add_node("intake", intake_node)
    g.add_node("strike", strike_node)
    g.add_node("verdict", verdict_node)
    g.add_node("report", report_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "strike")
    g.add_edge("strike", "verdict")
    g.add_edge("verdict", "report")
    g.add_edge("report", END)
    return g.compile()


def main() -> int:
    alert = sys.argv[1] if len(sys.argv) > 1 else "SpecproofApiDown"
    result = build_runbook_triage_graph().invoke({"alert": alert}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
