#!/usr/bin/env python
"""Demo doctor — one command self-check of the demo repository.

The user guide tells a newcomer to run the demo verification:

    specproof verify --repo demo/spring-backend --base base --head head-v1 \
        --spec demo/requirement.txt --depth FAST --no-llm

If any load-bearing link is broken (missing tag, stale requirement, missing
demo), the guide lies. This script is the signature on that promise: it
fails loudly and prints exactly what is broken.

Checks (no Docker, no network, no LLM):

  1. demo/spring-backend exists and is a git work tree          [fail if not]
  2. tags `base` and `head-v1` both resolve                     [fail if not]
  3. they point at *different* commits                           [fail if not]
  4. the base..head diff is non-empty and < 5000 changed lines   [fail if not]
  5. demo/requirement.txt exists, non-empty, names an evidence
     family (AUTH / UNIQUE / TOKEN / COMPAT / EVENT)             [fail if not]
  6. the demo working tree is clean                              [FAIL with --strict-clean, otherwise WARN]

Exit codes: 0 = healthy (warnings allowed), 1 = a hard check failed,
2 = demo repo not present (e.g. a shallow clone without the demo).

Usage:
    python scripts/demo_doctor.py [--json] [--strict-clean]
"""

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "demo" / "spring-backend"
SPEC = REPO / "demo" / "requirement.txt"
EVIDENCE_FAMILIES = re.compile(r"AUTH|UNIQUE|TOKEN|COMPAT|EVENT", re.IGNORECASE)
MAX_DIFF_LINES = 5000


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(DEMO), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Self-check the SpecProof demo repository.")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--strict-clean", action="store_true", help="fail on a dirty demo working tree")
    args = parser.parse_args()

    results: list[dict] = []

    def check(name: str, status: str, detail: str) -> None:
        """status: PASS | WARN | FAIL"""
        results.append({"check": name, "status": status, "detail": detail})

    def emit(code: int) -> int:
        if args.json:
            print(json.dumps({"exit": code, "checks": results}, ensure_ascii=False))
            return code
        mark = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}
        for r in results:
            print(f"[{mark[r['status']]}] {r['check']} — {r['detail']}")
        verdict = "healthy" if code == 0 else ("demo missing" if code == 2 else "unhealthy")
        warns = sum(1 for r in results if r["status"] == "WARN")
        print(f"\nverdict: {verdict} (exit {code}, {warns} warning(s))")
        return code

    if not DEMO.exists():
        check("1-demo-repo", "FAIL", f"demo repo missing at {DEMO} — shallow clone without demo?")
        return emit(2)

    # 1. git work tree
    try:
        inside = git("rev-parse", "--is-inside-work-tree") == "true"
    except Exception as exc:  # noqa: BLE001 - doctor must convert failures into checks
        check("1-demo-repo", "FAIL", f"not a git work tree: {exc}")
        return emit(2)
    check("1-demo-repo", "PASS" if inside else "FAIL", str(DEMO))

    # 2/3. tags resolve and differ
    base = head = ""
    try:
        base, head = git("rev-parse", "base^{commit}"), git("rev-parse", "head-v1^{commit}")
        check("2-tags-resolve", "PASS" if base and head else "FAIL",
              f"base={base[:8]} head-v1={head[:8]}")
        check("3-tags-differ", "PASS" if base != head else "FAIL",
              "distinct commits" if base != head else "base and head-v1 point at the same commit — the demo proves nothing")
    except Exception as exc:  # noqa: BLE001
        check("2-tags-resolve", "FAIL", str(exc))
        check("3-tags-differ", "FAIL", "skipped — tag unresolvable")

    # 4. diff size
    if base and head and base != head:
        numstat = git("diff", "--numstat", base, head)
        changed = sum(int(part) for line in numstat.splitlines() for part in line.split("\t")[:2] if part.isdigit())
        ok = 0 < changed <= MAX_DIFF_LINES
        check("4-diff-scope", "PASS" if ok else "FAIL",
              f"{changed} changed line(s)" + ("" if changed else " — base..head is empty, the demo proves nothing"))
    else:
        check("4-diff-scope", "FAIL", "skipped — tags not usable")

    # 5. requirement.txt
    if SPEC.exists():
        text = SPEC.read_text(encoding="utf-8", errors="replace")
        families = sorted({m.group(0).upper() for m in EVIDENCE_FAMILIES.finditer(text)})
        ok = bool(text.strip()) and bool(families)
        check("5-requirement", "PASS" if ok else "FAIL",
              f"{len(text.splitlines())} lines, evidence families: {', '.join(families) or 'NONE'}")
    else:
        check("5-requirement", "FAIL", f"missing {SPEC}")

    # 6. cleanliness
    status = git("status", "--porcelain")
    if not status.strip():
        check("6-clean-tree", "PASS", "clean")
    else:
        files = len(status.strip().splitlines())
        detail = f"{files} uncommitted change(s) in demo repo working tree"
        check("6-clean-tree", "FAIL" if args.strict_clean else "WARN", detail)

    return emit(1 if any(r["status"] == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    sys.exit(main())
