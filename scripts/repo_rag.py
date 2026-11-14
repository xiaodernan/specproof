#!/usr/bin/env python
"""Repo-RAG — ask SpecProof questions; the answer comes from the repo, not the model's mood.

A deliberately dependency-free retrieval-augmented Q&A:

1. Corpus: every `*.md` under docs/ and the repository root's top-level docs
2. Retriever: char 2-gram TF-IDF, cosine similarity, no third-party index config
3. Generator: the configured LLM (via providers.config) — instructed to answer
   ONLY from the retrieved context and to cite the file+section it used.

Caching (two levels, both optional, both off the critical path):

* L1: process-local LRU (per run; instant);
* L2: Redis (`SPECPROOF_REDIS_URL`, default `redis://127.0.0.1:6379/3`, key
  `specproof:rag:v1:*`) — document token vectors keyed by
  `path + mtime_ns + size` (24h TTL) and final answers keyed by a sha256 of the
  normalized question (15min TTL). No Redis / no package → silently L1-only.
  `SPECPROOF_RAG_CACHE=0` disables both tiers entirely.

Usage:
    python scripts/repo_rag.py "缓存命中率到底什么意思"     # one-shot question
    python scripts/repo_rag.py --retrieve-only "..."      # show context, call no LLM
    python scripts/repo_rag.py --interactive                # REPL
    python scripts/repo_rag.py --stats "..."                # print cache hit/miss
"""

import argparse
import asyncio
import hashlib
import math
import os
import pickle
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORPUS_GLOBS = ("docs/**/*.md", "*.md")
MAX_DOC_CHARS = 20000
TOP_K = 5
_WORD_RE = re.compile(r"[A-Za-z0-9_一-鿿]+")
_REDIS_URL = os.environ.get("SPECPROOF_REDIS_URL", "redis://127.0.0.1:6379/3")
_CACHE_ENABLED = os.environ.get("SPECPROOF_RAG_CACHE", "1") != "0"
_CACHE_NS = "specproof:rag:v1:"
_DOC_TTL = 60 * 60 * 24        # 24h — doc fingerprint (path+mtime+size) is the key, so staleness self-heals
_Q_TTL = 60 * 15               # 15min — answers can drift as docs evolve


class TwoLevelCache:
    """L1 in-process LRU + L2 Redis. Any failure downgrades to the next level; never raises."""

    def __init__(self) -> None:
        self.l1: dict[str, object] = {}
        self.l1_order: list[str] = []
        self.stats = {"l1_hit": 0, "l2_hit": 0, "miss": 0, "redis": "off", "l2_ops_failed": 0}
        self.redis = None
        if not _CACHE_ENABLED:
            self.stats["redis"] = "disabled-by-env"
            return
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(_REDIS_URL, socket_timeout=1.5, socket_connect_timeout=1.5)
            client.ping()
            self.redis = client
            self.stats["redis"] = "ok"
        except Exception:
            self.stats["redis"] = "unavailable"

    def get(self, key: str):
        if key in self.l1:
            self.stats["l1_hit"] += 1
            return self.l1[key]
        if self.redis is not None:
            try:
                raw = self.redis.get(_CACHE_NS + key)
            except Exception:
                self.stats["l2_ops_failed"] += 1
                raw = None
            if raw is not None:
                try:
                    value = pickle.loads(raw)
                except Exception:
                    self.stats["l2_ops_failed"] += 1
                else:
                    self.l1_put(key, value)
                    self.stats["l2_hit"] += 1
                    return value
        self.stats["miss"] += 1
        return None

    def l1_put(self, key: str, value, max_l1: int = 512):
        if key in self.l1:
            self.l1_order.remove(key)
        self.l1[key] = value
        self.l1_order.append(key)
        while len(self.l1_order) > max_l1:
            evict = self.l1_order.pop(0)
            self.l1.pop(evict, None)

    def put(self, key: str, value, ttl: int):
        self.l1_put(key, value)
        if self.redis is not None:
            try:
                self.redis.setex(_CACHE_NS + key, ttl, pickle.dumps(value, protocol=5))
            except Exception:
                self.stats["l2_ops_failed"] += 1

    def snapshot(self) -> str:
        return (f"cache: redis={self.stats['redis']} l1_hit={self.stats['l1_hit']} "
                f"l2_hit={self.stats['l2_hit']} miss={self.stats['miss']} "
                f"l2_ops_failed={self.stats['l2_ops_failed']}")


_CACHE = TwoLevelCache()


def tokens(text: str) -> list[str]:
    def grams(word: str) -> list[str]:
        if len(word) <= 2:
            return [word]
        return [word[i:i + 2] for i in range(len(word) - 1)]
    out: list[str] = []
    for m in _WORD_RE.finditer(text):
        out.extend(grams(m.group(0).lower()))
    return out


def token_vector(text: str) -> dict[str, float]:
    counts: dict[str, int] = {}
    for tok in tokens(text):
        counts[tok] = counts.get(tok, 0) + 1
    total = sum(counts.values()) or 1
    return {tok: c / total for tok, c in counts.items()}


def doc_fingerprint(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return f"{path.relative_to(REPO).as_posix()}:{st.st_mtime_ns}:{st.st_size}"


def load_corpus() -> list[dict[str, str]]:
    docs = []
    for pattern in CORPUS_GLOBS:
        for path in sorted(REPO.glob(pattern)):
            if not path.is_file():
                continue
            fp = doc_fingerprint(path)
            if fp is None:
                continue
            cached = _CACHE.get(f"doc:{fp}")
            if cached is not None:
                # mtime+size fingerprint pins content; stale vectors are unreachable
                docs.append({"id": fp.split(":", 1)[0], "text": None, "tv": cached})  # type: ignore[arg-type]
                # text must still be readable for the final context window — read it cheaply without re-tokenizing
                try:
                    docs[-1]["text"] = path.read_text(encoding="utf-8", errors="ignore")[:MAX_DOC_CHARS]
                except OSError:
                    docs.pop()
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            body = raw[:MAX_DOC_CHARS]
            tv = token_vector(body)
            _CACHE.put(f"doc:{fp}", tv, _DOC_TTL)
            docs.append({"id": path.relative_to(REPO).as_posix(), "text": body, "tv": tv})
    return docs


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
- If the answer is NOT in the context, say exactly: 「上下文里没有这条」 / "the context does not contain this."
- Match the question's language (Chinese or English). Never invent.
"""


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip()).lower()


def question_key(question: str) -> str:
    return "q:" + hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()


def retrieve(question: str) -> list[tuple[dict[str, str], float]]:
    corpus = load_corpus()
    qvec = token_vector(question)
    scored = sorted(
        ((doc, cosine(qvec, doc["tv"])) for doc in corpus),
        key=lambda kv: kv[1], reverse=True,
    )[:TOP_K]
    return [(doc, score) for doc, score in scored if score > 0]


async def ask(question: str, retrieve_only: bool = False, show_stats: bool = False) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    started = time.perf_counter()
    scored = retrieve(question)
    context = "\n\n".join(
        f"--- [{doc['id']}] (relevance {score:.3f}) ---\n{(doc['text'] or '')[:2600]}" for doc, score in scored
    )
    if retrieve_only:
        print(f"retrieved {len(scored)} chunks in {time.perf_counter() - started:.2f}s\n")
        print(context)
        if show_stats:
            print(f"\n[{_CACHE.snapshot()}]")
        return 0

    cached_answer = _CACHE.get(question_key(question))
    if cached_answer is not None:
        print(f"[cache hit — answer reused; rerun with SPECPROOF_RAG_CACHE=0 to force a fresh call]\n")
        print(cached_answer)
        if show_stats:
            print(f"\n[{_CACHE.snapshot()}]")
        return 0

    from providers.config import load_model_config
    from providers.responses_protocol import normalize_base_url
    from openai import AsyncOpenAI

    try:
        cfg = load_model_config()
    except Exception as exc:  # noqa: BLE001
        print(f"model config unreadable: {exc}")
        return 2

    client = AsyncOpenAI(
        api_key=cfg["api_key"],
        base_url=normalize_base_url(cfg["base_url"]),
        max_retries=1,
        timeout=90.0,
    )
    print(f"retrieved {len(scored)} chunks in {time.perf_counter() - started:.2f}s\n")
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
        _CACHE.put(question_key(question), text, _Q_TTL)
        print(text)
        if show_stats:
            print(f"\n[{_CACHE.snapshot()}]")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"LLM call failed: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "repo rag")
    parser.add_argument("question", nargs="*", help="the question (quote it)")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--retrieve-only", action="store_true", help="print retrieved context; never call the LLM")
    parser.add_argument("--stats", action="store_true", help="print cache hit/miss snapshot at the end")
    args = parser.parse_args()
    if args.interactive:
        while True:
            try:
                q = input("question> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q:
                continue
            asyncio.run(ask(q, args.retrieve_only, args.stats))
            print()
        return 0
    if not args.question:
        parser.print_help()
        return 2
    return asyncio.run(ask(" ".join(args.question), args.retrieve_only, args.stats))


if __name__ == "__main__":
    raise SystemExit(main())
