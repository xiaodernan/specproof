"""investigation_dig_graph — LLM-backed readonly investigation digger (the ninth lamp).

One knock sends three readonly roles (explorer / tester / security) into the
repository in parallel — the user's question plus bounded local facts — and
returns a verdict on whether the model actually found evidence. Offline by
construction when no model is configured: verdicts stay UNAVAILABLE, never a
fabricated green.

Verdict lexicon (fail-closed): EVIDENCE-GATHERED / INSUFFICIENT.

Pattern: intake -> strike -> verdict -> report -> END

Usage:

    HTTPS_PROXY=http://127.0.0.1:7897 python agent/graphs/investigation_dig_graph.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

from craft.investigators import investigate  # noqa: E402


class InvestigationDigState(TypedDict, total=False):
    question: str
    verdict: str
    report_path: str
    agents: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    total_tokens_used: int
    generation_time_ms: int


def intake_node(state: InvestigationDigState) -> InvestigationDigState:
    question = (state.get("question") or "").strip() or "本仓库这个变更做了什么？"
    return {"question": question}


def strike_node(state: InvestigationDigState) -> InvestigationDigState:
    workspace = ROOT
    try:
        result = asyncio.run(
            investigate(
                workspace,
                state.get("question") or "",
                timeout=45.0,
            )
        )
        return {
            "verdict": result.get("verdict", "INSUFFICIENT"),
            "findings": result.get("findings", []),
            "agents": result.get("agents", []),
            "total_tokens_used": result.get("total_tokens_used", 0),
            "generation_time_ms": result.get("generation_time_ms", 0),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "verdict": "INSUFFICIENT",
            "findings": [{"role": "strike", "claim": f"{type(exc).__name__}: {exc}", "evidence": "exception", "confidence": 0.0}],
            "agents": [],
        }


from agent.graphs._witness import (  # noqa: E402
    verdict_node,  # absolute: same file runs as a script and as a module
)


def report_node(state: InvestigationDigState) -> InvestigationDigState:
    out_dir = ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "question": state.get("question"),
        "verdict": state.get("verdict"),
        "agents": state.get("agents", []),
        "findings": state.get("findings", []),
        "total_tokens_used": state.get("total_tokens_used", 0),
        "generation_time_ms": state.get("generation_time_ms", 0),
    }
    (out_dir / "investigation-dig.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md = [
        "# Investigation Dig",
        "",
        f"**verdict: {payload['verdict']}** · generation_time_ms {payload['generation_time_ms']}",
        "",
        f"question: {payload['question']}",
        "",
        "## Agents",
        "",
        "| name | outcome | duration (s) | tokens |",
        "|---|---|---|---|",
    ]
    for a in payload.get("agents", []):
        md.append(f"| {a.get('name')} | {a.get('outcome')} | {a.get('duration_ms', 0) / 1000:.1f}s | {a.get('tokens', 0)} |")
    md += ["", "## Findings", ""]
    for f in payload.get("findings", []):
        md.append(f"- **{f.get('role')}** — {f.get('claim')}")
    if not payload.get("findings"):
        md.append("- (empty)")
    (out_dir / "investigation-dig.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"report_path": str(out_dir / "investigation-dig.md")}


def build_investigation_dig_graph() -> Any:
    g = StateGraph(InvestigationDigState)
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
    result = build_investigation_dig_graph().invoke({"question": sys.argv[1] if len(sys.argv) > 1 else "本仓库做了什么？"}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
