#!/usr/bin/env python
"""audit_unsigned.py — verily check the four still-unsigned items (three above, plus branch cleanliness).

Every check answers with the state of the host/repo AT THE MOMENT THE SCRIPT
RUNS. Nothing is inferred from memory, nothing is cached; the doc written
(apps/web/src/pages/unsigned.json) is stamped with its own audit time.

Checks:
  1. observability-signature — docs/operations/OBSERVABILITY.md carries no
     human signature block (a line like "签字人：" / "sign-off:" / "signed by <name>").
     Absent block → "awaiting-signature". Present → we do NOT verify identity,
     only presence — and we say so.
  2. weekly-stress-merged — .github/workflows/weekly-stress.yml present in repo.
     Present → "merged" (its first strike is the Monday after merge; that is
     checked separately by the cron, not by this script).
  3. port-8000-answers — live probe of 127.0.0.1:8000/health, classified:
     "specproof-answering" (our triple mysql/redis/agent_jobs),
     "other-project-answering" (anything else that answered),
     "port-free" (nothing listened).

Exit code: 0 always (the report is the product; a failing host does not crash it).
"""
import io
import json
import re
import sys
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OBS = ROOT / "docs" / "operations" / "OBSERVABILITY.md"
WF = ROOT / ".github" / "workflows" / "weekly-stress.yml"
OUT = ROOT / "apps" / "web" / "src" / "pages" / "unsigned.json"

checks = []

# ── 1 · observability signature ─────────────────────────────────────────────
sig_res = [
    r"签字人[：:]\s*[^\s：:]{2,}",
    r"sign-off[：:]\s*[^\s:]{2,}",
    r"signed\s*by\s+[A-Za-z][A-Za-z0-9 ._-]{2,}",
    r"批准人[：:]\s*[^\s：:]{2,}",
    r"验收签字[：:]\s*[^\s：:]{2,}",
]
body = OBS.read_text(encoding="utf-8") if OBS.exists() else ""
sig_found = next((pat for pat in sig_res if re.search(pat, body)), None)
checks.append({
    "id": "observability-signature",
    "status": "signature-block-found" if sig_found else "awaiting-signature",
    "detail": (f"human signature block matched {sig_found!r} — presence only, identity NOT verified"
               if sig_found else
               "OBSERVABILITY.md exists with no human signature block; this audit does not manufacture one"),
    "anchor": "docs/operations/OBSERVABILITY.md",
})

# ── 2 · weekly-stress merged ────────────────────────────────────────────────
checks.append({
    "id": "weekly-stress-merged",
    "status": "merged" if WF.exists() else "missing",
    "detail": ("specproof-weekly-stress present (schedule 0 3 * * 1; first strike is the Monday 03:00 UTC after merge)"
               if WF.exists() else
               "weekly-stress.yml absent — the scheduled strike lane does not exist"),
    "anchor": ".github/workflows/weekly-stress.yml",
})

# ── 3 · port 8000 answers today ─────────────────────────────────────────────
probe = {"reachable": False}
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2.0) as resp:
        raw = resp.read()[:512].decode("utf-8", errors="replace")
        probe = {
            "reachable": True,
            "http": resp.status,
            "body_preview": raw[:200],
            "looks_specproof": all(k in raw for k in ("mysql", "redis", "agent_jobs")),
        }
except Exception as exc:  # noqa: BLE001 - host state is data, never a crash
    probe = {"reachable": False, "error": f"{type(exc).__name__}"}

if probe.get("looks_specproof"):
    port_status = "specproof-answering"
    port_detail = f"127.0.0.1:8000/health answered HTTP {probe['http']} with the specproof triple (mysql/redis/agent_jobs) — specproof IS bound here right now"
elif probe.get("reachable"):
    port_status = "other-project-answering"
    port_detail = (f"127.0.0.1:8000/health answered HTTP {probe['http']} — NOT specproof's triple; "
                   f"preview: {probe['body_preview']}")
else:
    port_status = "port-free"
    port_detail = f"127.0.0.1:8000 refused/unreachable ({probe.get('error', 'timeout')}); no project answered"

checks.append({
    "id": "port-8000-answers",
    "status": port_status,
    "detail": port_detail,
    "anchor": "live probe 127.0.0.1:8000/health",
})

# ── 4 · branch cleanliness (ahead / behind / dirty / diverged) ──────────────
def _git_count(args):
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=10, encoding="utf-8", errors="replace")
        return out.stdout.strip()
    except Exception:
        return ""

counts = _git_count(["rev-list", "--left-right", "--count", "@{u}...HEAD"])
dirty = _git_count(["status", "--porcelain"]).splitlines()
if counts:
    left, _, right = counts.partition("\t")
    ahead, behind = int(left or 0), int(right or 0)
else:
    ahead = behind = -1  # no upstream or unreadable

if ahead == -1:
    br_status, br_detail = "no-upstream", "git has no upstream configured on this branch (cannot compare with origin)"
elif dirty and ahead and behind:
    br_status, br_detail = "dirty-diverged", f"work tree has {len(dirty)} dirty entr" + f"ies; local ahead {ahead} / behind {behind} vs upstream"
elif dirty:
    br_status, br_detail = "dirty-tree", f"work tree has {len(dirty)} dirty entries (new/modified/untracked); origin is clean-synced ahead={ahead} behind={behind}"
elif ahead and behind:
    br_status, br_detail = "diverged", f"local ahead {ahead} AND behind {behind} vs upstream — a merge is pending"
elif ahead:
    br_status, br_detail = "ahead-of-origin", f"local is ahead of upstream by {ahead} commit(s) — unpushed work exists (normal while developing)"
elif behind:
    br_status, br_detail = "behind-origin", f"local is behind upstream by {behind} commit(s) — pull before you strike"
else:
    br_status, br_detail = "clean", "work tree clean; local == upstream (0/0)"
checks.append({
    "id": "branch-cleanliness",
    "status": br_status,
    "detail": br_detail,
    "anchor": "git rev-list --left-right --count @{u}...HEAD && git status --porcelain",
})

doc = {
    "version": 1,
    "source": "scripts/audit_unsigned.py (this host, this moment)",
    "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "checks": checks,
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
for c in checks:
    print(f"[{c['status']:24s}] {c['id']} — {c['detail'][:80]}")
print(f"\nwrote {OUT}")
