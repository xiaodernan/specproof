#!/usr/bin/env python
"""Coarse mixed-script residue detector for the web source.

SpecProof's rule: a surface renders Chinese or English — never a mixed
"规划中 Planning"-style label unless the pair is deliberately bilingual
(page-local `Record<Locale, ...>` files, which are exempt here).

This script is a COARSE filter, not a gate: it flags any string literal that
contains both a CJK run and an ASCII run of ≥3 letters, then classifies the
match as

* bucket B — an *intentional tech term* (git, docker, cached_tokens, ...),
* bucket A — a *suspicious* leftover (e.g. "等待计划审批 Awaiting approval"
  in a file that renders unconditionally),
* bucket C — *coordinated bilinguals* (2026-11-17 re-derivation): literals
  whose line carries an inline bilingual switch (`zh ?`, `isZh ?`,
  `locale === "zh" ?`) or sits inside an `L(zh, en)` call — the EN branch is
  the translation's sibling, not a stray English word inside zh prose.

Bucket A needs a human eye; bucket B is the intentional mixed-script style
this repo allows inside zh prose ("`base_pass_head_fail` 意味着……").

Exit code is always 0 — this is an advisory report for humans, never a
blocking gate (its false-positive rate is too high for CI).
"""

import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# The report contains CJK + symbols; Windows consoles default to GBK and
# UnicodeEncodeError mid-print would truncate it. Force UTF-8 output.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001 - best-effort console fix only
    pass

REPO = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
# Dispositioned by inspection (2026-11-15, round 2): the whole ui-kit/ directory
# is the dev-only style guide — ControlRoomPreview (14) is hero-showcase demo
# data, UiKit.tsx (75) demo fruit-rows etc. Intentional zh+en pairs, never
# rendered for customers. Human-eye cleared; does not drive bucket A down silently.
EXEMPT = re.compile(
    r"(strings\.ts|\.copy\.ts|__tests__|\.test\.|i18n|ui-kit/"
    r"|tour\.ts"          # zh edition of the Grand Tour; en edition verbatim in tour.copy.ts
    r"|agent/util\.ts"    # verbatim backend STATUS_LABELS mirror; rendered only via AGENT_STATUS_GLOSS; pinned by parity test
    r"|healthCategories\.ts"  # Record<Locale,…> object with zh+en siblings, each literalpaired on both sides
    r"|demo\.ts)"         # DEMO_*_ZH / DEMO_*_EN side-by-side; zh edition pairs with en verbatim
)
LITERAL = re.compile(r'"[^"\n]{2,300}"|\'[^\'\n]{2,300}\'|`[^`\n]{2,300}`')
CJK = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
#: An inline bilingual switch on the same line makes the pair deliberate:
#:    {L("中文字面", "English twin")}
#:    {zh ? "中文字面" : "English twin"}
#:    {isZh ? "中文字面" : "English twin"}
#:    locale === "zh" ? ...
#: or the literal itself rides a locale record key / bilingual array key:
#:    { zh: "中文字面", en: "English twin" }
#:    const SUGGESTED_ZH = [...]
#: this repo's pages also use a local helper `T("…", "…")` alias of L().
#: Any of these markers on the literal's line -> bucket C, not A.
COORDINATED = re.compile(
    r'\bL\s*\(|\bzh\s*\?|\bisZh\s*\?|\blocale\s*===?\s*["\']zh["\']\s*\?'
    r'|\bzh\s*:|\b[A-Za-z_][A-Za-z0-9_]*_ZH\b|\bT\s*\('
)

# Latin words that are accepted inside zh prose as tech terms / product names.
TECH = {
    "git", "github", "gitlab", "docker", "kubernetes", "redis", "mysql", "minio", "rabbitmq",
    "eureka", "oauth", "jwt", "rbac", "ci", "cd", "sdk", "api", "http", "https", "sql", "json",
    "yaml", "xml", "html", "css", "js", "ts", "tsx", "jsx", "node", "npm", "npx", "pip", "python",
    "await", "async", "curl", "repo", "repos", "commit", "commits", "branch", "branches", "tag",
    "tags", "readme", "diff", "loc", "cache", "caches", "cached", "tokens", "prompt", "stream",
    "streams", "usage", "latency", "flag", "hash", "hashes", "blob", "sha", "sha256", "spec",
    "specs", "scan", "queue", "topics", "agent", "rag", "llm", "model", "specproof",
    "wkapi", "gpt", "sol", "log", "logs", "test", "tests", "mock", "fixture", "fixtures",
    "id", "ids", "ok", "kb", "mb", "gb", "ms", "fps", "db", "http2", "grpc", "tls", "ssh",
    "nginx", "uvicorn", "spring", "cloud", "gateway", "microservice", "microservices",
}


def latin_runs(text: str):
    return [m.group(0).lower() for m in LATIN.finditer(text)]


def classify(literal: str) -> str:
    latin = latin_runs(literal)
    if not latin:
        return "B"
    if all(token in TECH or token.rstrip("s") in TECH for token in latin):
        return "B"
    return "A"


def _open_call_spans(text: str, callee: str) -> list[tuple[int, int]]:
    """Every (start, end) span of an `L(` call, with strings and parens inside
    strings respected. A literal located inside such a span is the zh branch of
    a coordinated bilingual call, not an untranslated leftover."""
    spans: list[tuple[int, int]] = []
    marker = callee + "("
    i = 0
    while True:
        start = text.find(marker, i)
        if start == -1:
            break
        # must not be a suffix of an identifier (fooL(bar) != L(bar))
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            i = start + 1
            continue
        depth = 1
        j = start + len(marker)
        in_str = None
        while j < len(text) and depth:
            ch = text[j]
            if in_str:
                if ch == in_str:
                    in_str = None
                elif ch == "\\":
                    j += 1
            elif ch in '"\'`':
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            j += 1
        spans.append((start, j))
        i = j
    return spans


def main() -> int:
    if not REPO.is_dir():
        print(f"repo not found at {REPO}", file=sys.stderr)
        return 2
    a_files = Counter()
    a_total = 0
    b_total = 0
    c_total = 0
    a_examples = defaultdict(list)
    for p in REPO.rglob("*"):
        if p.suffix not in (".ts", ".tsx"):
            continue
        rel = p.relative_to(REPO).as_posix()
        if EXEMPT.search(rel):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.splitlines()
        l_spans = _open_call_spans(text, "L")
        for m in LITERAL.finditer(text):
            lit = m.group(0)
            if not CJK.search(lit):
                continue
            line_no = text.count("\n", 0, m.start())
            on_line = lines[line_no] if line_no < len(lines) else ""
            # marker on the same line, or on either of the two lines above it
            # (the `{zh\n  ? "literal" ...}` expansion)
            context_lines = "\n".join(
                lines[max(0, line_no - k)] for k in (2, 1, 0)
            )
            if COORDINATED.search(on_line) or COORDINATED.search(context_lines) or any(
                s <= m.start() < e for s, e in l_spans
            ):
                c_total += 1
                continue
            bucket = classify(lit)
            if bucket == "A":
                a_total += 1
                a_files[rel] += 1
                if len(a_examples[rel]) < 4:
                    a_examples[rel].append(lit.strip("\"'`")[:110])
            else:
                b_total += 1
    print(f"bucket A (suspicious, needs human eye): {a_total} literals in {len(a_files)} files")
    print(f"bucket B (intentional tech terms / product names): {b_total} literals")
    print(f"bucket C (coordinated bilingual ternaries / L() calls): {c_total} literals")
    print()
    for rel, n in a_files.most_common():
        print(f"{n:3}  {rel}")
        for e in a_examples[rel]:
            print(f"      - {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
