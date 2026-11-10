#!/usr/bin/env python3
"""Measure the payload-census consumer bindings against the pinned roster.

Why this script exists
----------------------
Every insertion in ``apps/web/src/api.ts`` moves the line numbers that the
payload-census gate (
    ``tests/unit/test_the_payload_the_frontend_declares_is_the_payload_a_route_publishes.py``)
pins by hand in
``CONSUMER_BINDING_ROSTER``. Red gates in #1526/#1541 showed
the same failure three times in one week. This script re-measures what the
gate's tree says and prints the per-style diff against the pinned tuples,
so a re-pin is a reviewed copy-paste instead of archaeology.

What this script does NOT do
----------------------------
It does **not** edit the gate or the docs. Re-pinning is a human + red-gate
step: update ``CONSUMER_BINDING_ROSTER`` in the test file, commit, and let
the suite confirm. This tool only answers "what does this tree measure right
now, and where does that disagree with what is pinned?"

Exit codes: 0 — measured == pinned for every style; 1 — drift found; 2 —
could not measure (module failed to import, repo incomplete).

The ``--json`` flag prints the same report machine-readably, suitable for
pasting into a commit message or a ledger section.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_MODULE = (
    ROOT / "tests" / "unit"
    / "test_the_payload_the_frontend_declares_is_the_payload_a_route_publishes.py"
)


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("test_payload_census_gate", TEST_MODULE)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {TEST_MODULE}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 — diagnostic tool; the reader must see the reason
        print(f"failed to import the gate module: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return module


def measured_by_style(mod) -> dict[str, list[tuple[str, int]]]:
    rows = mod.consumer_bindings(mod.REPO)
    by_style: dict[str, list[tuple[str, int]]] = {}
    for row in rows:
        by_style.setdefault(row.style, []).append((row.file, row.line))
    return {style: sorted(items) for style, items in by_style.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    mod = _load_gate_module()
    measured = measured_by_style(mod)
    pinned = {style: sorted(set(rows)) for style, rows in mod.CONSUMER_BINDING_ROSTER.items()}

    styles = sorted(set(measured) | set(pinned))
    report: dict[str, dict] = {}
    ok = True
    for style in styles:
        m_rows = measured.get(style, [])
        p_rows = pinned.get(style, [])
        gained = sorted(set(m_rows) - set(p_rows))
        lost = sorted(set(p_rows) - set(m_rows))
        match = not gained and not lost
        ok = ok and match
        report[style] = {
            "measured": m_rows,
            "pinned": p_rows,
            "gained": gained,
            "lost": lost,
            "match": match,
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    for style in styles:
        entry = report[style]
        status = "ok   " if entry["match"] else "DRIFT"
        print(
            f"[{status}] {style}: pinned={len(entry['pinned'])} "
            f"measured={len(entry['measured'])}"
        )
        for file_, line in entry["gained"]:
            print(f"        gained  {file_}:{line}")
        for file_, line in entry["lost"]:
            print(f"        lost    {file_}:{line}")
    print()
    if ok:
        print("payload census rosters match the measured tree")
        return 0
    print(
        "DRIFT found — re-pin CONSUMER_BINDING_ROSTER in "
        "tests/unit/test_the_payload_the_frontend_declares_is_the_payload_a_route_publishes.py "
        "and re-run that file; this script changed nothing."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
