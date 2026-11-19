"""recall_graph.py — one StateGraph that asks the iron a real question.

Strikes a single ledger question through tokenisation → dual-field BM25 → verdict.
No LLM, no network, no state persisted anywhere but the report we print/score.

Usage:
    python agent/graphs/recall_graph.py "court 永不缓存" [--docs-dir docs] [--top 3]

The kernel of the tsx /recall page — every assert here can be replayed by anyone offline.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RecallState(TypedDict, total=False):
    query: str
    docs_dir: str
    top: int
    hits: list[dict[str, Any]]
    verdict: str
    detail: str
    generated_utc: str


def _query(state: RecallState) -> str:
    return state.get("query") or ""


_WORD = re.compile(r"[A-Za-z0-9_]{2,}")
_CJK = re.compile(r"[一-鿿]")


def _tokenize(text: str) -> list[str]:
    lower = text.lower()
    out: list[str] = list(_WORD.findall(lower))
    cjk = "".join(_CJK.findall(lower))
    for index in range(len(cjk)):
        out.append(cjk[index])
    for index in range(len(cjk) - 1):
        out.append(cjk[index:index + 2])
    return out


def _field_tokens(doc: dict[str, Any]) -> list[str]:
    return _tokenize(doc["title"]) + _tokenize(doc["body"])


def intake_node(state: RecallState) -> RecallState:
    if not _query(state).strip():
        return {"verdict": "MISSING-QUERY", "detail": "no query provided — nothing is being asked"}
    return {"verdict": "ASKED", "detail": "query received — walking the ledger now"}


def _build_idx(docs_dir: Path) -> dict[str, Any]:
    chronicle = (docs_dir.parent / "apps" / "web" / "src" / "pages" / "chronicle.json")
    corrections = (docs_dir.parent / "apps" / "web" / "src" / "pages" / "corrections.json")
    docs: list[dict[str, Any]] = []
    if chronicle.exists():
        for entry in json.loads(chronicle.read_text(encoding="utf-8")):
            docs.append({
                "kind": "ledger",
                "n": entry.get("n"),
                "title": str(entry.get("t") or ""),
                "body": str(entry.get("s") or ""),
            })
    if corrections.exists():
        corr = json.loads(corrections.read_text(encoding="utf-8"))
        items = corr.get("items") or []
        ids = corr.get("ids") or []
        for index, item in enumerate(items):
            rid = ids[index] if index < len(ids) else f"R{index + 1}"
            body = item if isinstance(item, str) else (item.get("body") or str(item))
            docs.append({"kind": "erratum", "n": rid, "title": rid, "body": body})
    return {"docs": docs}


K1, B = 1.5, 0.75
TITLE_WEIGHT, BODY_WEIGHT = 2.4, 1.0


def field_score(tokens: list[str], weight: float, term: str, avg_len: float) -> float:
    tf = tokens.count(term)
    if not tf:
        return 0.0
    norm = 1 - B + B * len(tokens) / (avg_len or 1.0)
    return weight * tf * (K1 + 1) / (tf + K1 * norm)


def search_node(state: RecallState) -> RecallState:
    docs_dir = Path(state.get("docs_dir") or "docs")
    docs = _build_idx(docs_dir)["docs"]
    if not docs:
        return {
            "verdict": "EVIDENCE-MISSING",
            "detail": "no ledger lines available; set docs-dir or restore files",
        }
    terms = list(dict.fromkeys(_tokenize(_query(state))))
    if not terms:
        return {
            "verdict": "MISSING-QUERY",
            "detail": "query produced zero tokens — nothing to match",
        }
    n_docs = len(docs)
    field_lists: list[tuple[list[str], list[str]]] = [
        (_tokenize(d["title"]), _tokenize(d["body"])) for d in docs]
    doc_len = [len(t) + len(b) or 1 for t, b in field_lists]
    avg_all = sum(doc_len) / n_docs
    avg_title = sum(len(t[0]) for t in field_lists) / n_docs
    avg_body = sum(len(t[1]) for t in field_lists) / n_docs
    df: dict[str, int] = {}
    for title_toks, body_toks in field_lists:
        for term in set(title_toks) | set(body_toks):
            df[term] = df.get(term, 0) + 1

    def idf(term: str) -> float:
        dfreq = df.get(term, 0)
        if dfreq == 0:
            return 0.0
        return math.log(1 + (n_docs - dfreq + 0.5) / (dfreq + 0.5))

    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        title_toks, body_toks = field_lists[i]
        score = 0.0
        for term in terms:
            w = idf(term)
            if w == 0:
                continue
            score += w * (
                field_score(title_toks, TITLE_WEIGHT, term, avg_title)
                + field_score(body_toks, BODY_WEIGHT, term, avg_body)
            )
        if score > 0:
            hits.append({
                "kind": doc["kind"], "n": doc["n"],
                "score": round(score, 4),
                "title": str(doc["title"])[:160],
                "body": str(doc["body"])[:220],
            })
    hits.sort(key=lambda entry: entry["score"], reverse=True)
    top = int(state.get("top") or 3)
    return {"hits": hits[:top], "verdict": "HIT" if hits else "MISS",
            "detail": f"{len(hits)} hits above zero (corpus={n_docs} lines, avg_len={avg_all:.1f})"}


from agent.graphs._witness import (  # noqa: E402
    verdict_node,  # absolute: same file runs as a script and as a module
)


def build_recall_graph() -> Any:
    graph = StateGraph(RecallState)
    for name, fn in [("intake", intake_node), ("search", search_node), ("verdict", verdict_node)]:
        graph.add_node(name, fn)
    graph.set_entry_point("intake")
    graph.add_edge("intake", "search")
    graph.add_edge("search", "verdict")
    graph.add_edge("verdict", END)
    return graph.compile()


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    query = " ".join(args).strip()
    docs = next(
        (arg.split("=", 1)[1] for arg in sys.argv[1:] if arg.startswith("--docs-dir=")),
        "docs")
    top = int(next((arg.split("=", 1)[1] for arg in sys.argv[1:] if arg.startswith("--top=")), "3"))
    result = build_recall_graph().invoke({"query": query, "docs_dir": docs, "top": top})
    print(f"query={query!r} verdict={result.get('verdict')}")
    for hit in result.get("hits", []):
        print(f"  score={hit['score']:.2f} {hit['kind']}#{hit['n']} | {hit['title'][:90]}")
