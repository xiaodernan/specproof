"""usage_ledger_graph.py — the ledger reports itself (offline).

Reads the local token-level usage ledger through the same honest aggregation
the Usage panel renders, and files a verdict:

    ANSWERED    the ledger holds >= 1 readable row in the window; the report
                is what the machine itself wrote, including the honest
                (unreported) protocol bucket — never backfilled with a zero
    UNAVAILABLE zero rows, a missing file, or a summary that raised:
                nothing is synthesized to make it look alive

This graph is not a judge of the cache. It does not grade evidence kinds,
never touches court's lane, and moves no threshold — it verifies the
bookkeeping: every call the product made landed its row, protocol got tagged
(or is honestly tagged "unknown"), errors were counted, and bytes exist.

Pattern: intake -> strike -> verdict -> report -> END

Usage:

    python agent/graphs/usage_ledger_graph.py

Writes docs/evidence/usage-ledger-witness.json + docs/evidence/usage-ledger-witness.md.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing_extensions import TypedDict

from langgraph.graph import END, StateGraph

from providers.usage_ledger import read_records, summarize
from storage.env_config import float_env


class UsageLedgerState(TypedDict, total=False):
    window_hours: float
    started_utc: str
    report_path: str
    summary: dict[str, Any]
    rows_read: int
    verdict: str
    notes: str


def intake_node(state: UsageLedgerState) -> UsageLedgerState:
    window = float_env("SPECPROOF_LEDGER_WINDOW_HOURS", 24.0)
    return {
        "window_hours": max(1.0, min(window, 24.0 * 30)),
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def strike_node(state: UsageLedgerState) -> UsageLedgerState:
    try:
        records = read_records()
        summary = summarize(records, window_hours=state.get("window_hours") or 24.0)
    except Exception as exc:  # noqa: BLE001 - an unreadable ledger is UNAVAILABLE, never a guess
        return {
            "verdict": "UNAVAILABLE",
            "notes": f"{type(exc).__name__}: {exc}",
            "rows_read": 0,
            "summary": {},
        }
    return {
        "summary": summary,
        "rows_read": len(records),
    }


def verdict_node(state: UsageLedgerState) -> UsageLedgerState:
    if state.get("verdict") == "UNAVAILABLE":
        return state
    summary = state.get("summary") or {}
    if int(summary.get("calls") or 0) > 0:
        return {"verdict": "ANSWERED"}
    return {"verdict": "UNAVAILABLE", "notes": "no rows in window"}


def report_node(state: UsageLedgerState) -> UsageLedgerState:
    out_dir = Path(os.environ.get("SPECPROOF_LEDGER_WITNESS_DIR") or (ROOT / "docs" / "evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = state.get("summary") or {}
    payload: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "verdict": state.get("verdict", "UNAVAILABLE"),
        "window_hours": state.get("window_hours"),
        "rows_read": state.get("rows_read", 0),
        "calls": summary.get("calls"),
        "errors": summary.get("errors"),
        "error_rate": summary.get("error_rate"),
        "streamed_ratio": summary.get("streamed_ratio"),
        "cached_tokens": summary.get("cached_tokens"),
        "hit_rate": summary.get("hit_rate"),
        "hit_basis_calls": summary.get("hit_basis_calls"),
        "by_lane": summary.get("by_lane"),
        "by_protocol": summary.get("by_protocol"),
        "latency_p50_ms": summary.get("latency_p50_ms"),
        "latency_p95_ms": summary.get("latency_p95_ms"),
        "notes": state.get("notes") or "",
    }
    (out_dir / "usage-ledger-witness.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    verdict = payload["verdict"]
    by_lane: list[dict[str, Any]] = payload.get("by_lane") or []
    md_lines = [
        "# Usage Ledger Witness",
        "",
        f"**verdict: {verdict}** · struck {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "| facet | value |",
        "|---|---|",
        f"| calls (window) | {payload['calls']} |",
        f"| errors | {payload['errors']} · rate {payload['error_rate']} |",
        f"| streamed share | {payload['streamed_ratio']} |",
        f"| cached tokens | {payload['cached_tokens']} · hit_rate {payload['hit_rate']} (basis {payload['hit_basis_calls']}) |",
        f"| latency p50/p95 | {payload['latency_p50_ms']} / {payload['latency_p95_ms']} ms |",
        "",
        "## By lane",
        "",
        "| lane | calls | prompt | cached | hit_rate |",
        "|---|---|---|---|---|",
    ]
    for row in by_lane:
        md_lines.append(
            f"| {row.get('lane')} | {row.get('calls')} | {row.get('prompt_tokens')} | {row.get('cached_tokens')} | {row.get('hit_rate')} |"
        )
    if not by_lane:
        md_lines.append("| (none) | | | | |")
    reasons = [payload.get("notes") or ""]
    (out_dir / "usage-ledger-witness.md").write_text(
        "\n".join(line for line in md_lines if line is not None) + "\n\n" + "\n".join(r for r in reasons if r) + "\n",
        encoding="utf-8",
    )
    return {"report_path": str(out_dir / "usage-ledger-witness.md")}


def build_usage_ledger_graph() -> Any:
    g = StateGraph(UsageLedgerState)
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
    result = build_usage_ledger_graph().invoke({}) or {}
    print(f"verdict={result.get('verdict')} rows_read={result.get('rows_read')}")
    print(f"report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
