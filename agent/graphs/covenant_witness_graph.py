"""covenant_witness_graph — the eleventh lamp: the covenant, witnessed.

All five cacheable lanes (ai_summary · insight_advice · observe_advice ·
craft/investigators dig + runbook triads) carry one byte-identical Chinese
covenant as their first system message (``api/system_covenant.py``). The
prefix cache that the covenant was struck to activate only works while the
covenant stays byte-identical — a single quiet edit defeats it silently.

This graph reads the covenant; it never scores it, never strikes a model,
never moves it. Its whole job is to compute sha-256 of the covenant text,
verify the pins the covenant itself makes to the repository (every law names
files — they must exist), and write a receipt to
``docs/evidence/covenant-witness.{json,md}`` for the repo to keep.

Verdict vocabulary: HELD (all pins hold) / DRIFTED (any pin fails).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

from api.system_covenant import SPECROOF_COVENANT  # noqa: E402

_EXPECTED_LAWS = 11
_MIN_BYTES = 1000

# Pinned sha256 of the covenant as struck in #1969 (2026-11-17). Any single
# byte edited anywhere — one comma, one space — flips the verdict to DRIFTED.
PIN_SHA256 = "257a857782d8ea8f0b3af33792db2bcf685bedd577548a6be0986e143385418f"

# These are referenced by the covenant but are never tracked on purpose
# (they hold a key). Absence is not a failure — an unknown missing file is.
# This list is deliberately short and in-shadow of the purity sift.
_EXPECTED_UNTRACKED = frozenset({".local/llm.json"})


class CovenantWitnessState(TypedDict, total=False):
    bytes: int
    sha256: str
    laws: int
    referenced_paths: list[str]
    missing_paths: list[str]
    pinned: bool
    verdict: str
    report_path: str
    notes: str


_PATH_RE = re.compile(r"([a-zA-Z0-9_./-]+\.(?:py|md|json|yml|yaml|txt|env|example|toml|ini))")


def intake_node(state: CovenantWitnessState) -> CovenantWitnessState:  # noqa: ARG001
    raw = SPECROOF_COVENANT.encode("utf-8")
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def verify_node(state: CovenantWitnessState) -> CovenantWitnessState:
    text = SPECROOF_COVENANT
    laws = len([ln for ln in text.splitlines() if re.match(r"^[一二三四五六七八九十]+、", ln)])
    referenced = sorted(set(_PATH_RE.findall(text)))
    missing = [p for p in referenced if p not in _EXPECTED_UNTRACKED and not (ROOT / p).exists()]
    pinned = hashlib.sha256(SPECROOF_COVENANT.encode("utf-8")).hexdigest() == PIN_SHA256
    checks_ok = (
        len(SPECROOF_COVENANT.encode("utf-8")) >= _MIN_BYTES
        and laws == _EXPECTED_LAWS
        and not missing
        and pinned
    )
    return {
        "laws": laws,
        "referenced_paths": referenced,
        "missing_paths": missing,
        "pinned": pinned,
        "verdict": "HELD" if checks_ok else "DRIFTED",
    }


from agent.graphs._witness import verdict_node  # noqa: E402  (pass-through, one identity per repo)


def report_node(state: CovenantWitnessState) -> CovenantWitnessState:
    out_dir = ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "bytes": state.get("bytes", 0),
        "sha256": state.get("sha256", ""),
        "laws": state.get("laws", 0),
        "referenced_paths": state.get("referenced_paths", []),
        "missing_paths": state.get("missing_paths", []),
        "verdict": state.get("verdict", "DRIFTED"),
        "pinned": state.get("pinned", False),
    }
    (out_dir / "covenant-witness.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    md = [
        "# Covenant Witness",
        "",
        f"**verdict: {payload['verdict']}** · sha256 `{payload['sha256'][:12]}` · "
        f"{payload['bytes']} B · {payload['laws']}/{_EXPECTED_LAWS} laws "
        f"· pinned={payload['pinned']}",
        "",
        "## Pins (referenced paths that must exist)",
        "",
    ]
    for p in payload["referenced_paths"]:
        if p in _EXPECTED_UNTRACKED:
            mark, suffix = "☑️", "  (untracked by design)"
        elif p in payload["missing_paths"]:
            mark, suffix = "❌", ""
        else:
            mark, suffix = "✅", ""
        md.append(f"- {mark} `{p}`{suffix}")
    if payload["missing_paths"]:
        md += ["", "## Missing", ""]
        for p in payload["missing_paths"]:
            md.append(f"- `{p}`")
    (out_dir / "covenant-witness.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"report_path": str(out_dir / "covenant-witness.md")}


def build_covenant_witness_graph() -> Any:
    g = StateGraph(CovenantWitnessState)
    g.add_node("intake", intake_node)
    g.add_node("verify", verify_node)
    g.add_node("verdict", verdict_node)
    g.add_node("report", report_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "verify")
    g.add_edge("verify", "verdict")
    g.add_edge("verdict", "report")
    g.add_edge("report", END)
    return g.compile()


def main() -> int:
    result = build_covenant_witness_graph().invoke({}) or {}
    print(f"verdict={result.get('verdict')} report={result.get('report_path')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
