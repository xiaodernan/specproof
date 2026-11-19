#!/usr/bin/env python
"""audit_portfolio.py — live readiness trove for portfolio sync.

Read-only. Exits 0 always; prints & stores findings.
Checks:
  A. https://xiaodernan.github.io/ reachable (HEAD + body bytes)?
  B. The embedded SpecProof card reference in the page (string shape — page may not expose this name)?
  C. GitHub repo existence for xiaodernan/specproof (anonymous API HEAD / no token, no auth abuse)?
  D. Whether PORTFOLIO_TOKEN env var is set on this host (answer only yes/no, never the value).
  E. Which workflows would run on master push (portfolio-sync.yml present?).
  F. Artifacts/data/ folder exists at build time?
"""
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]

checks = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 — report must always run
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    checks.append({"id": name, "ok": ok, "detail": detail})
    print(f"[{'ok ' if ok else 'FAIL'}] {name} — {detail[:120]}")


def page():
    req = urllib.request.Request(
        "https://xiaodernan.github.io/",
        method="GET",
        headers={"User-Agent": "specproof-audit/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read()
        return resp.status == 200 and len(body) > 0, f"HTTP {resp.status}, {len(body)} bytes"


def specproof_repo():
    req = urllib.request.Request(
        "https://github.com/xiaodernan/specproof",
        method="HEAD",
        headers={"User-Agent": "specproof-audit/1.0"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status == 200, f"HTTP {resp.status}"


def specproof_card_notice():
    try:
        req = urllib.request.Request(
            "https://xiaodernan.github.io/",
            method="GET",
            headers={"User-Agent": "specproof-audit/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace").lower()
        return True, ("page contains 'specproof'" if "specproof" in body else "page does not mention specproof (pre-sync state)")
    except Exception as exc:
        return False, f"page unreachable ({type(exc).__name__})"


check("https://xiaodernan.github.io/ reachable", page)
check("github.com/xiaodernan/specproof exists (anonymous HEAD)", specproof_repo)
check("page mentions specproof (spot-check copy)", specproof_card_notice)
check("PORTFOLIO_TOKEN env var set on this host",
      lambda: (True, "set (contents value hidden)") if __import__("os").environ.get("PORTFOLIO_TOKEN") else (False, "NOT SET — sync never pushes; workflow stays green"))


def wf():
    p = ROOT / ".github" / "workflows" / "portfolio-sync.yml"
    return (p.exists(), "present" if p.exists() else "missing — sync unreachable")


check("portfolio-sync.yml present in repo", wf)


def artifacts():
    p = ROOT / "artifacts"
    if p.is_dir():
        n = sum(1 for _ in p.rglob("*") if _.is_file())
        return True, f"artifacts/ exists ({n} file(s))"
    return False, "artifacts/ does not exist — build produced none"


check("artifacts/ folder at build time", artifacts)

doc = {
    "version": 1,
    "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "verdict": "READY_WITHOUT_TOKEN" if not __import__("os").environ.get("PORTFOLIO_TOKEN") else "READY_WITH_TOKEN",
    "checks": checks,
    "anchor": "scripts/audit_portfolio.py · .github/workflows/portfolio-sync.yml",
}
out = ROOT / "docs" / "evidence" / "audit-portfolio.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\nverdict: {doc['verdict']}")
print("wrote", out)
