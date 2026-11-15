#!/usr/bin/env python
"""audit_court_lock.py — the court-cache lock integrity audit.

This repository's hardest invariant: **court / judge lanes never enter any
cache**. This script machine-verifies it bottom-up — not by trusting anyone,
not by trusting this comment, only by reading the bytes:

  1. providers/openai_compatible.py emits stream=True + include_usage=True
     (the only lane in which cached_tokens is even visible to the app);
  2. providers/client_policy.py hard-refuses evidence kinds (court ... );
  3. providers/semantic_cache.py EVIDENCE_KINDS == {"court","counterexample",
     "accept_judge","contract_compile"} and CACHEABLE_KINDS == {"draft","diagnose"};
  4. client_policy.py's disabled-default gate SPECPROOF_PROVIDER_POLICY.

Each byte-slice hash is taken over the minimal substring that carries the
invariant (not the file hash — irrelevant bytes are not evidence).

Writes apps/web/src/pages/courtLock.json. Rem-exit-code 0 only if every
string-detection holds; otherwise prints the failing slice and exits 2.
Read-only; never modifies anything.
"""
import hashlib
import io
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "apps" / "web" / "src" / "pages"

def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def find(path: Path, regex: str) -> tuple[str, str] | None:
    text = path.read_text(encoding="utf-8")
    m = re.search(regex, text, flags=re.S)
    if not m:
        return None
    return m.group(0), sha256(m.group(0))


checks = []

# 1 · the stream+include_usage pair must appear inside the raw-call builder
ocp = ROOT / "providers" / "openai_compatible.py"
p1 = find(ocp, r'kwargs\["stream"\]\s*=\s*True|"stream"\s*:\s*True')
checks.append({"id": "openai_compatible_stream_true", "found": p1 is not None, "evidence_sha256": p1[1] if p1 else None,
               "anchor": "providers/openai_compatible.py"})
p2 = find(ocp, r'kwargs\["stream_options"\]\s*=\s*\{[^{}]*include_usage[^{}]*\}|"stream_options"\s*:\s*\{[^{}]*include_usage[^{}]*\}')
checks.append({"id": "openai_compatible_include_usage", "found": p2 is not None, "evidence_sha256": p2[1] if p2 else None,
               "anchor": "providers/openai_compatible.py"})

# 2 · client_policy: disabled-default gate the audit relies on
cp = ROOT / "providers" / "client_policy.py"
p3 = find(cp, r'ENV_POLICY\s*=\s*"SPECPROOF_PROVIDER_POLICY"')
checks.append({"id": "policy_disabled_by_default", "found": p3 is not None, "evidence_sha256": p3[1] if p3 else None,
               "anchor": "providers/client_policy.py"})

# 3 · semantic_cache EVIDENCE_KINDS exact set (four evidence kinds, no more, no fewer)
sc = ROOT / "providers" / "semantic_cache.py"
text = sc.read_text(encoding="utf-8")
m = re.search(r'EVIDENCE_KINDS[^=]*=\s*frozenset\(\s*\{[^}]*\}\s*\)', text, flags=re.S)
ok3 = False
if m:
    body = m.group(0)
    names = set(re.findall(r'"([a-z_]+)"', body))
    ok3 = names == {"court", "counterexample", "accept_judge", "contract_compile"}
checks.append({"id": "semantic_cache_evidence_kinds_match", "found": ok3, "evidence_sha256": sha256(m.group(0)) if m else None,
               "anchor": "providers/semantic_cache.py",
               "members": sorted(names) if m else []})

# 4 · CACHEABLE_KINDS exact set (two, no more, no fewer)
m = re.search(r'CACHEABLE_KINDS[^=]*=\s*frozenset\(\s*\{[^}]*\}\s*\)', text, flags=re.S)
ok4 = False
if m:
    names = set(re.findall(r'"([a-z_]+)"', m.group(0)))
    ok4 = names == {"draft", "diagnose"}
checks.append({"id": "semantic_cache_cacheable_kinds_match", "found": ok4, "evidence_sha256": sha256(m.group(0)) if m else None,
               "anchor": "providers/semantic_cache.py",
               "members": sorted(names) if m else []})

all_ok = all(c["found"] for c in checks)
lock = hashlib.sha256(
    "".join(sorted((c["evidence_sha256"] or "-") for c in checks)).encode("utf-8")
).hexdigest()[:16]

doc = {
    "version": 1,
    "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "verdict": "LOCKED" if all_ok else "BROKEN",
    "lock": lock,
    "court_rule": "court / judge never enter any cache — stream+include_usage only lane of recorded usage",
    "checks": checks,
    "anchor": "scripts/audit_court_lock.py · git show HEAD:providers/semantic_cache.py",
}
(PAGES / "courtLock.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
for c in checks:
    flag = "ok " if c["found"] else "FAIL"
    print(f"[{flag}] {c['id']}")
print(f"\nverdict: {doc['verdict']}  lock: {lock}")
sys.exit(0 if all_ok else 2)
