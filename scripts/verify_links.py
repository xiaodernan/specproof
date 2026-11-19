#!/usr/bin/env python
"""verify_links.py — find dead relative markdown links inside docs/ and README.

Checks:
  [text](path)          → path resolves from the containing file, repo root, or ANY
                            of the tracked source roots (docs/, apps/web/src/, agent/,
                            cli/, services/, demo/)
  `path/file` in backticks → same roots; tokens carrying `...` ellipses are skipped,
                            as are .scratch/ and other intentionally-free places

Outputs: docs/evidence/audit-links.json ; prints a table of dead links.
Exit 0 always; the report is the product.
"""
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EXTRA = [ROOT / "README.md", ROOT / "AGENTS.md"]

ROOTED_PREFIXES = ("/", "http://", "https://", "mailto:", "#")
SKIP_PREFIXES = (".scratch/", "spec/", ".docs/", "src/main/", "config/", "../", "@", "git@", "node_modules/", ".claude/", ".workbuddy/", ".workbuddy-ai/", ".venv", ".venue/", ".vendor/", ".codex/", "opencode/", ".gradle/", ".tmp/", "/tmp/")
ROOTS = [ROOT, DOCS, DOCS / "operations", ROOT / "apps" / "web" / "src", ROOT / "apps" / "web", ROOT / "agent", ROOT / "cli", ROOT / "services", ROOT / "demo", ROOT / "apps", ROOT / "tests", ROOT / "down", ROOT / "app"]

def resolvable(base: Path, target: str) -> bool:
    t = target.split("#", 1)[0].split("?", 1)[0]
    if not t:
        return True
    if "..." in t or "*" in t or t.startswith(SKIP_PREFIXES):
        return True  # intentional placeholder or out-of-repo area
    if any((root / t).exists() for root in ROOTS):
        return True
    if (base / t).exists():
        return True
    if t.startswith("src/"):
        for root in ROOTS:
            stripped = t[4:].lstrip("/")
            cand = ROOT / "apps" / "web" / "src" / stripped
            if cand.exists():
                return True
            cand2 = root / "apps" / "web" / t
            if cand2.exists():
                return True
        if (ROOT / "apps" / "web" / t).exists():
            return True
    return False

report = []

def check_file(path: Path) -> list[dict]:
    out = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    base = path.parent
    skip_code_refs = path.name == "DEEP_OPTIMIZATION_PLAN.md"  # ledger = deliberate synthetic paths in examples
    for m in re.finditer(r'\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)', text):
        target = m.group(2)
        if any(target.startswith(p) for p in ROOTED_PREFIXES):
            continue
        t = target.split("#", 1)[0].split("?", 1)[0]
        if not t:
            continue
        if not resolvable(base, t):
            out.append({"kind": "md-link", "target": target, "text": m.group(1)[:80]})
    annotated_planned = {
        "MUTATION_PLAN.md": {"mutants/manifest.json"},
    }
    if skip_code_refs:
        pass  # code-ref scan intentionally off for the ledger; md-links above still enforced
    elif path.name in annotated_planned:
        for m in re.finditer(r'`([A-Za-z0-9_./@-]+/[A-Za-z0-9_./@-]+)`', text):
            tok = m.group(1)
            if tok in annotated_planned[path.name] and not (ROOT / tok).exists():
                out.append({"kind": "annotated-planned", "target": tok,
                            "note": "doc explicitly labels the file as not-yet-existing / to-be-generated"})
        return out
    else:
        for m in re.finditer(r'`([A-Za-z0-9_./@-]+/[A-Za-z0-9_./@-]+)`', text):
            tok = m.group(1)
            if any(tok.startswith(p) for p in ("http", "https", "git@", "@types", "node_modules")):
                continue
            if (
                tok.count("/") >= 1
                and any(tok.endswith(s) for s in (".sh", ".py", ".md", ".json", ".yml", ".yaml", ".toml", ".ps1", ".ts", ".tsx", ".js", ".go", ".java", ".svg", ".sql", ".proto", ".xml", ".html", ".css", ".lock"))
                and not resolvable(base, tok)
            ):
                out.append({"kind": "code-ref", "target": tok})
    return out

files = sorted(DOCS.rglob("*.md")) + [p for p in EXTRA if p.exists()]

total_dead = 0
total_planned = 0
report = []
for f in files:
    dead = check_file(f)
    if dead:
        planned = [d for d in dead if d["kind"] == "annotated-planned"]
        truly_dead = [d for d in dead if d["kind"] != "annotated-planned"]
        if truly_dead or planned:
            row = {"file": str(f.relative_to(ROOT)).replace("\\", "/")}
            if truly_dead:
                row["dead"] = truly_dead
                total_dead += len(truly_dead)
            if planned:
                row["annotated_planned"] = planned
                total_planned += len(planned)
            report.append(row)
files_with = sum(1 for r in report if r.get("dead"))

doc = {
    "version": 3,
    "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "files_checked": len(files),
    "files_with_dead_links": files_with,
    "total_dead_links": total_dead,
    "annotated_planned_count": total_planned,
    "report": report,
}
out = ROOT / "docs" / "evidence" / "audit-links.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"checked {len(files)} files; {len(report)} files carry dead links; {total_dead} total")
for r in report:
    print(f"\n{r['file']}")
    for d in r.get("dead", []):
            print(f"  [{d['kind']}] {d['target']}")
    for d in r.get("annotated_planned", []):
            print(f"  [{d['kind']}] {d['target']}")
print(f"\nwrote {out}")
