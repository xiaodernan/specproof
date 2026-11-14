#!/usr/bin/env python
"""Repo-RAG — ask SpecProof questions; the answer comes from the repo, not the model's mood.

A deliberately dependency-free retrieval-augmented Q&A:

1. Corpus: every `*.md` under docs/ and the repository root's top-level docs
2. Retriever: char 2-gram TF-IDF, cosine similarity, no third-party index config
3. Generator: the configured LLM (via providers.config) — instructed to answer
   ONLY from the retrieved context and to cite the file+section it used.

Usage:
    python scripts/repo_rag.py "缓存命中率到底什么意思"     # one-shot question
    python scripts/repo_rag.py --interactive                # REPL
"""

import argparse
import asyncio
import io
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS_GLOBS = ("docs/**/*.md", "*.md")
MAX_DOC_CHARS = 20000
TOP_K = 5
_WORD_RE = re.compile(r"[A-Za-z0-9_一-鿿]+")


def tokens(text: str) -> list[str]:
    def grams(word: str) -> list[str]:
        if len(word) <= 2:
            return [word]
        return [word[i:i + 2] for i in range(len(word) - 1)]
    out: list[str] = []
    for m in _WORD_RE.finditer(text):
        out.extend(grams(m.group(0).lower()))
    return out


def load_corpus() -> list[dict[str, str]]:
    docs = []
    for pattern in CORPUS_GLOBS:
        for path in sorted(REPO.glob(pattern)):
            if not path.is_file():
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            body = raw[:MAX_DOC_CHARS]
            docs.append({
                "id": path.relative_to(REPO).as_posix(),
                "text": body,
                "tv": token_vector(body),
            })
    return docs


def token_vector(text: str) -> dict[str, float]:
    counts: dict[str, int] = {}
    for tok in tokens(text):
        counts[tok] = counts.get(tok, 0) + 1
    total = sum(counts.values()) or 1
    return {tok: c / total for tok, c in counts.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a.get(tok, 0.0) * b.get(tok, 0.0) for tok in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


SYSTEM_PROMPT = """You are SpecProof's documentarian. Answer ONLY from the retrieved context below.
Rules:
- Quote or closely paraphrase; cite like [docs/operations/FOO.md §N].
- If the answer is NOT in the context, say exactly: 「上下文里没有这条」/ “the context does not contain this.”
- Match the question's language (Chinese or English). Never invent.
"""


async def ask(question: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from providers.config import load_model_config
    from providers.responses_protocol import normalize_base_url
    from openai import AsyncOpenAI

    try:
        cfg = load_model_config()
    except Exception as exc:  # noqa: BLE001
        print(f"model config unreadable: {exc}")
        return 2

    corpus = load_corpus()
    qvec = token_vector(question)
    scored = sorted(
        ((doc, cosine(qvec, doc["tv"])) for doc in corpus),
        key=lambda kv: kv[1], reverse=True,
    )[:TOP_K]
    context = "\n\n".join(
        f"--- [{doc['id']}] (relevance {score:.3f}) ---\n{doc['text'][:2600]}" for doc, score in scored if score > 0
    )
    client = AsyncOpenAI(
        api_key=cfg["api_key"],
        base_url=normalize_base_url(cfg["base_url"]),
        max_retries=1,
        timeout=90.0,
    )
    print(f"retrieved {len(scored)} chunks from {len(corpus)} documents\n")
    try:
        resp = await client.chat.completions.create(
            model=cfg["model"],
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"# Retrieved context\n\n{context}\n\n# Question\n{question}"},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        print(text)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"LLM call failed: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "repo rag")
    parser.add_argument("question", nargs="*", help="the question (quote it)")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    if args.interactive:
        while True:
            try:
                q = input("question> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q:
                continue
            asyncio.run(ask(q))
            print()
        return 0
    if not args.question:
        parser.print_help()
        return 2
    return asyncio.run(ask(" ".join(args.question)))


if __name__ == "__main__":
    raise SystemExit(main())
