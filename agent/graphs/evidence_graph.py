"""Evidence review graph — a small, offline LangGraph StateGraph.

Purpose: prove that LangGraph is wired into this repository's knowledge
*inside the app itself*, not only in the heavy verify pipeline.

Pipeline (entirely local file analysis, never an LLM, never a network):

  intake → collect_series → verdict → emit_report → END

State (all channels declared; nothing else is allowed to leak):

  evidence_dir: str      docs/evidence
  rounds:       list     one normalized dict per *.json, newest first
  deltas:       list     worst_p99_ms diffs between consecutive files
  verdict:      str      OK | REGRESSION | EVIDENCE-MISSING | NO-DELTA
  report_path:  str      written markdown summary
  summary:      str      one-line outcome
  errors:       list     unreadable entries (fail-closed)

Fail-closed: unreadable JSON or missing directory → verdict "EVIDENCE-MISSING",
and the report is still written — with the failure called out loudly.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict
from langgraph.graph import END, StateGraph


class EvidenceState(TypedDict, total=False):
    evidence_dir: str
    rounds: list[dict[str, Any]]
    deltas: list[float]
    verdict: str
    report_path: str
    summary: str
    errors: list[str]


def intake_node(state: EvidenceState) -> EvidenceState:
    evidence_dir = Path(state.get("evidence_dir") or "docs/evidence")
    rounds: list[dict[str, Any]] = []
    errors: list[str] = list(state.get("errors") or [])
    if not evidence_dir.is_dir():
        errors.append(f"evidence dir not found: {evidence_dir}")
        return {"evidence_dir": str(evidence_dir), "rounds": [], "errors": errors}
    def order_key(path: Path):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            stamp = str(raw.get("started_utc", "")) or ""
            if stamp:
                return (1, stamp)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return (0, str(path.stat().st_mtime))
    for f in sorted(evidence_dir.glob("*.json"), key=order_key, reverse=True):
        if f.name.startswith(("audit-", "verify-", "weekly-")) and f.name.endswith("-summary.json"):
            continue
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.append(f"unreadable {f.name}: {exc}")
            continue
        if "rounds" not in raw:
            continue  # the audit JSON family (audit-links/evidence/residue/tick), not a stress exhibit
        rows = raw.get("rounds") or []
        worst_p99 = max((float(r.get("p99_ms", 0) or 0) for r in rows), default=0.0)
        rounds.append({
            "file": f.name,
            "started_utc": raw.get("started_utc", ""),
            "worst_p99_ms": worst_p99,
            "verdict": raw.get("verdict", "unknown"),
            "total_ok": sum(int(r.get("ok", 0) or 0) for r in rows),
            "total": sum(int(r.get("total", 0) or 0) for r in rows),
        })
    return {"evidence_dir": str(evidence_dir), "rounds": rounds, "errors": errors}


def collect_series_node(state: EvidenceState) -> EvidenceState:
    rounds = state.get("rounds") or []
    deltas: list[float] = []
    for i in range(len(rounds) - 1):
        deltas.append(rounds[i]["worst_p99_ms"] - rounds[i + 1]["worst_p99_ms"])
    return {"deltas": deltas}


def verdict_node(state: EvidenceState) -> EvidenceState:
    rounds = state.get("rounds") or []
    errors = state.get("errors") or []
    deltas = state.get("deltas") or []
    if errors or not rounds:
        return {"verdict": "EVIDENCE-MISSING"}
    if len(deltas) < 1:
        return {"verdict": "NO-DELTA"}
    worst_drift = max(deltas)
    if any(r["verdict"] != "OK" for r in rounds):
        return {"verdict": "REGRESSION"}
    if worst_drift > 25.0:
        return {"verdict": "REGRESSION"}
    return {"verdict": "OK"}


def emit_report_node(state: EvidenceState) -> EvidenceState:
    evidence_dir = Path(state.get("evidence_dir") or "docs/evidence")
    rounds = state.get("rounds") or []
    deltas = state.get("deltas") or []
    verdict = state.get("verdict") or "EVIDENCE-MISSING"
    lines = [
        f"# Evidence Tick — generated {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        f"verdict: **{verdict}**",
        f"entries: {len(rounds)}",
        "",
    ]
    for i, r in enumerate(rounds):
        d = f" · delta_vs_prev={deltas[i]:+.1f}ms" if i < len(deltas) else ""
        lines.append(f"- `{r['file']}` — p99≈{r['worst_p99_ms']:.1f}ms · verdict={r['verdict']} · {r['total_ok']}/{r['total']} ok{d}")
    if state.get("errors"):
        lines += ["", "errors:"] + [f"- {e}" for e in state["errors"]]
    lines += [
        "",
        "_This report is a deterministic pass of `agent/graphs/evidence_graph.py` — a StateGraph, not a log of wishes._",
    ]
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path = evidence_dir / "evidence-tick.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {"report_path": str(report_path), "summary": f"verdict={verdict} entries={len(rounds)}"}


def build_evidence_review_graph() -> Any:
    graph = StateGraph(EvidenceState)
    graph.add_node("intake", intake_node)
    graph.add_node("collect_series", collect_series_node)
    graph.add_node("verdict", verdict_node)
    graph.add_node("emit_report", emit_report_node)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "collect_series")
    graph.add_edge("collect_series", "verdict")
    graph.add_edge("verdict", "emit_report")
    graph.add_edge("emit_report", END)
    return graph.compile()


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/evidence"
    app = build_evidence_review_graph()
    result = app.invoke({"evidence_dir": out_dir})
    print(result.get("summary"))
