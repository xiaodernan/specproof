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
  in a file that renders unconditionally).

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

REPO = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
EXEMPT = re.compile(r"(strings\.ts|\.copy\.ts|__tests__|\.test\.|i18n)")
LITERAL = re.compile(r'"[^"\n]{2,300}"|\'[^\'\n]{2,300}\'|`[^`\n]{2,300}`')
CJK = re.compile(r"[一-鿿]")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")

# Latin words that are accepted inside zh prose as tech terms / product names.
TECH = {
    "git", "github", "gitlab", "docker", "kubernetes", "redis", "mysql", "minio", "rabbitmq",
    "eureka", "oauth", "jwt", "rbac", "ci", "cd", "sdk", "api", "http", "https", "sql", "json",
    "yaml", "xml", "html", "css", "js", "ts", "tsx", "jsx", "node", "npm", "npx", "pip", "python",
    "await", "async", "curl", "repo", "repos", "commit", "commits", "branch", "branches", "tag",
    "tags", "readme", "diff", "loc", "cache", "caches", "cached", "tokens", "prompt", "stream",
    "streams", "usage", "latency", "flag", "hash", "hashes", "blob", "sha", "sha256", "spec",
    "specs", "scan", "queue", "topics", "agent", "rag", "llm", "model", "model", "specproof",
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


def main() -> int:
    if not REPO.is_dir():
        print(f"repo not found at {REPO}", file=sys.stderr)
        return 2
    a_files = Counter()
    a_examples = defaultdict(list)
    b_total = 0
    a_total = 0
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
        for lit in LITERAL.findall(text):
            if not CJK.search(lit):
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
    print()
    for rel, n in a_files.most_common():
        print(f"{n:3}  {rel}")
        for e in a_examples[rel]:
            print(f"      - {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
