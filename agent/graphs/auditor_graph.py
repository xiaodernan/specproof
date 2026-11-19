"""Audit chain graph — Runs every audit this repository itself authored;
five lanes, one StateGraph, one rolled summary. No LLM, no network beyond
what the audit scripts already do, no invented checks:

  unsigned → court_lock → evidence → scratch_residue → portfolio → verdict → report → END

State:
  results:      list of {lane, exit, verdict} records
  verdict:      CLEAR | CRACKED | CLEAR-WITH-NOTES
  report_path:  what got written
  summary:      one-line outcome

Guard semantics: a non-zero exit from any audit OR a known-ungood JSON verdict
turns the whole chain CRACKED. Notes that are not failures (token missing)
do not crack anything.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _evidence_dir(state: AuditChainState) -> Path:
    d = state.get("evidence_dir")
    return Path(d) if d else ROOT / "docs" / "evidence"


class AuditChainState(TypedDict, total=False):
    results: list[dict[str, Any]]
    verdict: str
    report_path: str
    summary: str
    evidence_dir: str


def _run(script: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True,
        cwd=ROOT, timeout=30,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _read_json(state: AuditChainState, name: str) -> dict[str, Any] | None:
    p = _evidence_dir(state) / name
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def unsigned_node(state: AuditChainState) -> AuditChainState:
    code, out = _run("audit_unsigned.py")
    doc = _read_json(state, "../pages/unsigned.json")  # built in apps/web/src/pages
    fallback = ROOT / "apps" / "web" / "src" / "pages" / "unsigned.json"
    if doc is None and fallback.exists():
        doc = json.loads(fallback.read_text(encoding="utf-8"))
    last = out.splitlines()[-1] if out else "(no output)"
    last = last.replace(str(ROOT) + "\\", "<repo>/").replace(str(ROOT) + "/", "<repo>/")
    return {
        "results": state.get("results", []) + [{
            "lane": "unsigned",
            "exit": code,
            "verdict": ("four-lit lamps live" if code == 0 else "FAIL") + " — " + last.split("—")[-1].strip()[:160],
        }]
    }


def court_lock_node(state: AuditChainState) -> AuditChainState:
    code, out = _run("audit_court_lock.py")
    doc = _read_json(state, "../../apps/web/src/pages/courtLock.json")
    if doc is None:
        p = ROOT / "apps" / "web" / "src" / "pages" / "courtLock.json"
        if p.exists():
            doc = json.loads(p.read_text(encoding="utf-8"))
    verdict = (doc or {}).get("verdict") or "UNKNOWN"
    return {
        "results": state.get("results", []) + [{
            "lane": "court_lock",
            "exit": code,
            "verdict": f"verdict={verdict}",
        }]
    }


def evidence_node(state: AuditChainState) -> AuditChainState:
    code, out = _run("audit_evidence.py")
    doc = _read_json(state, "audit-evidence.json") or {}
    verdict = doc.get("verdict") or "UNKNOWN"
    return {
        "results": state.get("results", []) + [{
            "lane": "evidence",
            "exit": code,
            "verdict": f"verdict={verdict}",
        }]
    }


def scratch_node(state: AuditChainState) -> AuditChainState:
    code, out = _run("audit_scratch_residue.py")
    doc = _read_json(state, "audit-scratch-residue.json") or {}
    verdict = doc.get("verdict") or "unknown"
    return {
        "results": state.get("results", []) + [{
            "lane": "scratch_residue",
            "exit": code,
            "verdict": f"verdict={verdict} files={doc.get('files_count', 0)}",
        }]
    }


def portfolio_node(state: AuditChainState) -> AuditChainState:
    code, out = _run("audit_portfolio.py")
    doc = _read_json(state, "audit-portfolio.json") or {}
    verdict = doc.get("verdict") or "unknown"
    return {
        "results": state.get("results", []) + [{
            "lane": "portfolio",
            "exit": code,
            "verdict": f"verdict={verdict}",
        }]
    }


def verdict_node(state: AuditChainState) -> AuditChainState:
    results = state.get("results", [])
    bad = [
        r for r in results
        if r.get("exit") not in (0, None) or "BROKEN" in str(r.get("verdict", "")) or "DRIFT" in str(r.get("verdict", ""))
    ]
    return {"verdict": "CRACKED" if bad else "CLEAR"}


def report_node(state: AuditChainState) -> AuditChainState:
    results = state.get("results", [])
    verdict = state.get("verdict") or "CRACKED"
    lines = [
        f"# Audit Chain Roll — generated {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        f"verdict: **{verdict}**",
        f"lanes run: {len(results)}",
        "",
        "| lane | exit | verdict |",
        "|---|---|---|",
    ]
    for r in results:
        v = str(r.get("verdict", "")).replace("|", "/")
        lines.append(f"| {r.get('lane', '?')} | {r.get('exit', '?')} | {v[:120]} |")
    lines += [
        "",
        "_who wrote this: agent/graphs/audit_graph.py — deterministic subgraph; nobody edits the verdict by hand._",
    ]
    out_dir = _evidence_dir(state)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "audit-chain.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {
        "report_path": str(report),
        "summary": f"verdict={verdict} lanes={len(results)}",
    }


def build_audit_chain_graph() -> Any:
    graph = StateGraph(AuditChainState)
    for name, fn in [
        ("unsigned", unsigned_node),
        ("court_lock", court_lock_node),
        ("evidence", evidence_node),
        ("scratch_residue", scratch_node),
        ("portfolio", portfolio_node),
        ("verdict", verdict_node),
        ("report", report_node),
    ]:
        graph.add_node(name, fn)
    graph.set_entry_point("unsigned")
    graph.add_edge("unsigned", "court_lock")
    graph.add_edge("court_lock", "evidence")
    graph.add_edge("evidence", "scratch_residue")
    graph.add_edge("scratch_residue", "portfolio")
    graph.add_edge("portfolio", "verdict")
    graph.add_edge("verdict", "report")
    graph.add_edge("report", END)
    return graph.compile()


if __name__ == "__main__":
    app = build_audit_chain_graph()
    result = app.invoke({})
    print(result.get("summary"))
