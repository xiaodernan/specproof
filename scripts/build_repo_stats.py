#!/usr/bin/env python
"""Build repoStats.json — real, on-disk measurements, no invented numbers.

This is what the "Iron Census" panel displays: file counts, LOC by language,
test counts, world-bible sizes, ledger size, demo repository status. Every
figure here is verifiable with tools like `git`, `find`, or `wc` — nothing is
estimated, nothing is faked.

The output lives at apps/web/src/pages/repoStats.json and is consumed by
#/stats (the Iron Census route).
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "apps" / "web" / "src" / "pages" / "repoStats.json"

IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "__pycache__", ".scratch", "dist",
    ".vite", ".pytest_cache",
}
IGNORE_PARTS = []  # exact dir segments whose whole subtree is skipped
IGNORE_PREFIXES = ("demo/spring-backend/target", ".mypy_cache", ".ruff_cache", "reports")
IGNORE_FILE_EXTS = {".class", ".jar", ".pyc", ".d", ".idx"}

LANG_MAP = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript/TSX",
    ".js": "JavaScript",
    ".mjs": "JavaScript/ESM",
    ".java": "Java",
    ".md": "Markdown",
    ".css": "CSS",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".sql": "SQL",
    ".json": "JSON",
    ".xml": "XML",
    ".html": "HTML",
    ".txt": "Text",
    ".sh": "Shell",
    ".ps1": "PowerShell",
}

def iter_files():
    try:
        raw = subprocess.check_output(
            ["git", "ls-files"], cwd=REPO,
        ).decode("utf-8", errors="ignore").splitlines()
    except subprocess.CalledProcessError:
        return
    for rel in raw:
        if not rel:
            continue
        path = REPO / rel
        if path.is_file():
            yield path

def count_locs(path: Path) -> tuple[int, bool]:
    try:
        data = path.read_bytes()
    except OSError:
        return 0, False
    if b"\x00" in data[:4096]:
        return len(data), True  # binary
    try:
        text = data.decode("utf-8", errors="ignore")
        return len(text.splitlines()), False
    except Exception:
        return 0, False

def main() -> int:
    files = list(iter_files())
    total_bytes = 0
    total_loc = 0
    by_lang: dict[str, dict[str, int]] = {}
    binaries = 0
    for path in files:
        size = path.stat().st_size
        total_bytes += size
        locs, is_binary = count_locs(path)
        if is_binary:
            binaries += 1
            continue
        total_loc += locs
        ext = path.suffix.lower()
        lang = LANG_MAP.get(ext, ext if ext else "(no ext)")
        bucket = by_lang.setdefault(lang, {"files": 0, "lines": 0, "bytes": 0})
        bucket["files"] += 1
        bucket["lines"] += locs
        bucket["bytes"] += size

    ledger_path = REPO / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md"
    ledger_kb = round(ledger_path.stat().st_size / 1024, 1) if ledger_path.exists() else 0

    world_zh = REPO / "docs" / "world" / "SPECROOF_WORLD.md"
    world_en = REPO / "docs" / "world" / "EN" / "SPECROOF_WORLD_EN.md"

    try:
        commit_count = int(subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=REPO,
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip())
    except Exception:
        commit_count = -1

    try:
        python_test_files = sum(1 for p in (REPO / "tests").rglob("test_*.py") if "/.venv/" not in str(p))
        web_test_files = sum(1 for p in (REPO / "apps" / "web" / "src").rglob("*.test.*"))
    except Exception:
        python_test_files = web_test_files = -1

    try:
        import re
        heading_re = re.compile(r"^## #\d+\s+", re.M)
        ledger_sections = len(heading_re.findall(ledger_path.read_text(encoding="utf-8", errors="ignore"))) if ledger_path.exists() else -1
    except Exception:
        ledger_sections = -1

    stats = {
        "generated_by": "scripts/build_repo_stats.py",
        "repository_files": len(files),
        "total_bytes": total_bytes,
        "total_lines_of_source": total_loc,
        "binary_files": binaries,
        "by_language": by_lang,
        "ledger_bytes_kB": ledger_kb,
        "ledger_sections": ledger_sections,
        "world_bytes_zh": world_zh.stat().st_size if world_zh.exists() else 0,
        "world_bytes_en": world_en.stat().st_size if world_en.exists() else 0,
        "git_commit_count": commit_count,
        "python_test_files": python_test_files,
        "web_test_files": web_test_files,
    }
    OUT.write_text(json.dumps(stats, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8", newline="\n")
    print(f"files: {len(files)}")
    print(f"LOC:   {total_loc}")
    print(f"bytes: {total_bytes / 1024/1024:.1f} MB")
    print(f"languages: {len(by_lang)}")
    print(f"ledger: {ledger_kb} KB")
    print(f"commits: {commit_count}")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.1f} KB)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
