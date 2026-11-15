#!/usr/bin/env python
"""Build dossier.json — the Golden Case Compendium as data for `#/dossier`.

Reads every case dir under golden-cases / golden-cases-attribution /
golden-cases-crosslang. Each case contributes:

  id            stable slug (e.g. case-gc-01 / att-02 / go-01)
  family        "standard" | "attribution" | "crosslang"
  number        the numeric id when present (else None)
  title         first Markdown heading of spec.md, trimmed of the leading "Case" / "#"
  severity      ground-truth expected_severity
  contract      ground-truth expected_contract (nullable)
  evidence_type ground-truth expected_evidence_type
  should_detect ground-truth should_detect
  base_defects / head_defects  attribution-carried counts (attribution family only)
  numbers{total, detect, blocker, major, none} — filenames give us counts, not truth values

Everything is derived from files committed to this repository; nothing is
pulled over the network, nothing invented.
"""
import io, json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "web" / "src" / "pages" / "dossier.json"

FAMILIES = [
    ("standard", ROOT / "golden-cases", r"^case-(\d+)-(.+)$"),
    ("attribution", ROOT / "golden-cases-attribution", r"^case-att-(\d+)-(.+)$"),
    ("crosslang", ROOT / "golden-cases-crosslang", r"^case-(go|ts)-(\d+)-(.+)$"),
]

def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

def title_of(spec: str, fallback: str) -> str:
    for line in spec.splitlines():
        s = line.strip()
        if s.startswith("#"):
            s = s.lstrip("# ").strip()
            # drop the leading "Case <n>:" token, the id is already there
            s = re.sub(r"^Case\s+[0-9a-zA-Z-]+[:：]\s*", "", s).strip()
            return s or fallback
    return fallback

cases = []
for family, base, rx in FAMILIES:
    if not base.exists():
        continue
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        m = re.match(rx, d.name)
        if not m:
            continue
        if family == "crosslang":
            number = int(m.group(2))
            slug = m.group(1) + "-" + m.group(2) + "-" + m.group(3)
        else:
            number = int(m.group(1))
            slug = d.name
        gt = read_json(d / "ground-truth.json")
        scn = read_json(d / "scenario.json")
        spec = read_text(d / "spec.md")
        attr = gt.get("attribution") if isinstance(gt, dict) else None
        base_defects = len((attr or {}).get("base_defects") or [])
        head_defects = len((attr or {}).get("head_defects") or [])
        cases.append({
            "id": slug,
            "family": family,
            "number": number,
            "title": title_of(spec, slug),
            "spec": spec.strip(),
            "severity": (gt.get("expected_severity") or "UNKNOWN"),
            "contract": gt.get("expected_contract"),
            "evidence_type": (gt.get("expected_evidence_type") or "unknown"),
            "should_detect": bool(gt.get("should_detect", False)),
            "base_ref": scn.get("base_ref"),
            "head_ref": scn.get("head_ref"),
            "base_defects": base_defects,
            "head_defects": head_defects,
            "path": d.relative_to(ROOT).as_posix(),
        })

cases.sort(key=lambda c: (c["family"], c["number"], c["id"]))
detectable = [c for c in cases if c["should_detect"]]
print(f"cases={len(cases)} detectable={len(detectable)}")
sev_counts = {}
for c in cases:
    sev_counts[c["severity"]] = sev_counts.get(c["severity"], 0) + 1
print("severity histogram:", sev_counts)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"version": 1, "cases": cases}, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", OUT)
