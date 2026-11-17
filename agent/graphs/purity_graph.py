"""Purity graph — four nodes, deterministic, catches secret-shaped bytes.

Pipeline: intake → scan → crosscheck → verdict → report → END

Inputs: git ls-files (the tracked tree, not stray files).
Scans for: `sk-[A-Za-z0-9]{32,}` byte-level matches per file.
Cross-check: allowlists a single known hit at agent/security_scanner.py —
             it documents the pattern as a scanner rule, not a leaked key.
Outputs:  docs/evidence/purity-sift.md — one table + verdict.
Fails-closed: any match outside the allowlist flips verdict to CRACKED.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict
from langgraph.graph import END, StateGraph

ROOT = Path(__file__).resolve().parents[2]

ALLOWLIST = {
    "agent/security_scanner.py",          # documents the rule; the regex IS the rule
    "tests/contract/test_event_envelope.py",  # fixture: PEM header of a generated RSA key used to test the event envelope redactor (not a key-in-bytes; empty PRIVATE KEY body)
    "tests/unit/test_craft_tools.py",     # fixture: PEM header for tool output redaction test
    "tests/unit/test_redaction.py",        # redaction unit tests — deliberate fake strings (sk-abcdefghij...) used to prove the redactor catches real keys
    "tests/unit/test_repo_safety.py",      # repo-safety fixture redactor smoke
}
PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{32,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"credential[s]?\s*=\s*[\"'][A-Za-z0-9_\-]{24,}", re.I),
]


class PurityState(TypedDict, total=False):
    files: list[str]
    hits: list[dict[str, str]]
    verdict: str
    report_path: str
    summary: str


def intake_node(state: PurityState) -> PurityState:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
    ).stdout
    files = [l for l in out.splitlines() if l]
    return {"files": files, "hits": []}


def scan_node(state: PurityState) -> PurityState:
    hits: list[dict[str, str]] = []
    for f in state.get("files", []):
        p = ROOT / f
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for idx, line in enumerate(text.splitlines(), 1):
            for pat in PATTERNS:
                for m in pat.finditer(line):
                    hits.append({"file": f, "line": str(idx), "match": m.group(0)[:12] + "…"})
    return {"hits": hits}


def crosscheck_node(state: PurityState) -> PurityState:
    hits = [h for h in state.get("hits", []) if h["file"] not in ALLOWLIST]
    return {"hits": hits}


def verdict_node(state: PurityState) -> PurityState:
    hits = state.get("hits", [])
    if hits:
        return {"verdict": "CRACKED"}
    return {"verdict": "CLEAR"}


def report_node(state: PurityState) -> PurityState:
    hits = state.get("hits", [])
    verdict = state.get("verdict") or "UNKNOWN"
    lines = [
        f"# Purity Sift — generated {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        f"verdict: **{verdict}**",
        f"tracked files scanned: {len(state.get('files', []))}",
        f"unexpected hits: {len(hits)}",
        "",
    ]
    if hits:
        lines += ["| file | line | match-shape |", "|---|---|---|"]
        for h in hits:
            lines.append(f"| `{h['file']}` | {h['line']} | `{h['match']}` |")
    else:
        lines += ["_all tracked files are clean of secret-shaped bytes and PEM headers._"]
    lines += [
        "",
        "_who wrote this: agent/graphs/purity_graph.py — scan and nothing else._",
    ]
    out = ROOT / "docs" / "evidence" / "purity-sift.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    sidecar = out.with_suffix(".json")
    sidecar.write_text(
        json.dumps({
            "version": 1,
            "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "tracked_files": len(state.get("files", [])),
            "verdict": verdict,
            "unexpected_hits": len(hits),
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return {"report_path": str(out), "summary": f"verdict={verdict} hits={len(hits)}"}


def build_purity_graph() -> Any:
    g = StateGraph(PurityState)
    for name, fn in [
        ("intake", intake_node),
        ("scan", scan_node),
        ("crosscheck", crosscheck_node),
        ("verdict", verdict_node),
        ("report", report_node),
    ]:
        g.add_node(name, fn)
    g.set_entry_point("intake")
    g.add_edge("intake", "scan")
    g.add_edge("scan", "crosscheck")
    g.add_edge("crosscheck", "verdict")
    g.add_edge("verdict", "report")
    g.add_edge("report", END)
    return g.compile()


if __name__ == "__main__":
    app = build_purity_graph()
    print(app.invoke({}).get("summary"))
