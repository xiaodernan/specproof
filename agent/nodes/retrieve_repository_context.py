"""retrieve_repository_context node — Elasticsearch repository retrieval (P2).

Indexes the HEAD workspace's Java sources into ES as symbol-level chunks,
then retrieves the most relevant symbols for the requirement text. The
result feeds the contract compiler so it works with repository evidence
instead of the spec text alone.

RAG 2.0 (卷IV 4.2): when embeddings are configured (LLM_EMBEDDING_* /
LLM_* env) the node switches to the hybrid pipeline — index_with_embeddings
+ retrieval.hybrid.hybrid_search (BM25 + vector RRF → graph expansion →
optional rerank). Without embeddings it keeps the deterministic BM25 +
graph path unchanged (卷IV 4.3). The active mode is logged and annotated
in retrieval_note; per-hit retrieval metadata (source/rank/rrf_score)
rides the repo_context channel.

Honesty contract: when Elasticsearch is unavailable the node records a
retrieval_note and continues with an empty context — it never fabricates
retrieved content and never blocks the pipeline on optional infra.
"""

from __future__ import annotations

import logging
import subprocess  # nosec B404 — git rev-parse only; argument list, no shell
from pathlib import Path
from typing import Any

from agent.state import Phase0State

logger = logging.getLogger(__name__)

_QUERY_STOPWORDS = (
    "must", "must not", "should", "shall", "requirements", "the", "a", "an",
    "for", "of", "api", "all", "and", "or",
)

# Domain terms per contract family: requirement prose rarely matches code
# tokens verbatim ("require authentication" vs "@PreAuthorize"), so the
# query is augmented with the vocabulary of the relevant checker family.
_FAMILY_TERMS = {
    "http": "preauthorize secured rolesallowed isauthenticated authentication 401 403",
    "sql": "transactional save existsby unique constraint rollback",
    "redis": "redistemplate delete ttl expire invalidate",
    "openapi": "requestmapping getmapping postmapping requestbody dto response",
    "rabbitmq": "convertandsend publish rabbit template exchange",
}


def _family_augmentation(requirement_text: str) -> str:
    lowered = requirement_text.lower()
    terms: list[str] = []
    if any(w in lowered for w in ("auth", "login", "401", "403", "permission", "role")):
        terms.append(_FAMILY_TERMS["http"])
    if any(w in lowered for w in ("unique", "transaction", "atomic", "constraint")):
        terms.append(_FAMILY_TERMS["sql"])
    if any(w in lowered for w in ("token", "cache", "redis", "session")):
        terms.append(_FAMILY_TERMS["redis"])
    if any(w in lowered for w in ("schema", "compat", "openapi", "endpoint")):
        terms.append(_FAMILY_TERMS["openapi"])
    if any(w in lowered for w in ("event", "message", "queue", "exactly once")):
        terms.append(_FAMILY_TERMS["rabbitmq"])
    return " ".join(terms)


def _read_java_files(workspace: str) -> dict[str, str]:
    root = Path(workspace) / "src" / "main" / "java"
    files: dict[str, str] = {}
    if not root.exists():
        return files
    for p in root.rglob("*.java"):
        try:
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
        except OSError:
            continue
    return files


def _query_terms(requirement_text: str) -> str:
    terms = [
        w for w in requirement_text.lower().split()
        if w not in _QUERY_STOPWORDS and len(w) > 2
    ]
    return " ".join(terms[:12]) + " " + _family_augmentation(requirement_text)


def retrieve_repository_context_node(state: Phase0State) -> dict[str, Any]:
    """Index head sources and retrieve requirement-relevant symbols."""
    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    requirement_text = state.get("requirement_text", "")

    if not head_workspace:
        return {
            "repo_context": [],
            "retrieval_note": "No head workspace — repository retrieval skipped",
        }

    app = str(Path(head_workspace) / app_dir) if app_dir else head_workspace
    files = _read_java_files(app)
    if not files:
        return {
            "repo_context": [],
            "retrieval_note": "No Java sources in head workspace — nothing to index",
        }

    head_sha = ""
    try:
        proc = subprocess.run(  # nosec B603 B607 — args from local repo state
            ["git", "-C", state.get("repo_path", ""), "rev-parse",
             state.get("head_ref", "head-v1")],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            head_sha = proc.stdout.strip()
    except Exception:
        head_sha = ""

    try:
        from storage.elasticsearch import ElasticsearchStore

        store = ElasticsearchStore()
        if not store.is_ready():
            return {
                "repo_context": [],
                "retrieval_note": "Elasticsearch unavailable — retrieval skipped",
            }
        repo_key = "repo:" + state.get("repo_path", "")
        query = _query_terms(requirement_text)

        from agent.repo_graph import RepoGraph

        graph = RepoGraph(files)

        from retrieval.embeddings import EmbeddingClient
        from retrieval.hybrid import hybrid_search

        embedder = EmbeddingClient.from_env()
        use_llm = bool(state.get("use_llm", True))

        if embedder.configured:
            # RAG 2.0 hybrid path (卷IV 4.2): index with vectors, then
            # BM25 + vector RRF → graph expansion → optional rerank.
            indexed_report = store.index_with_embeddings(
                repo_key, head_sha, files, embedder
            )
            outcome = hybrid_search(
                es=store,
                query=query,
                repo=repo_key,
                k=16,
                graph=graph,
                embedder=embedder,
                use_llm=use_llm,
            )
            meta = outcome.meta
            context = [
                {
                    "path": h.get("path", ""),
                    "symbol": h.get("symbol", ""),
                    "content": (h.get("content") or "")[:800],
                    "source": h.get("source", "hybrid"),
                    "rank": h.get("rank"),
                    "rrf_score": h.get("rrf_score"),
                }
                for h in outcome.results
            ]
            note = (
                "hybrid_rrf mode=" + str(meta.get("mode"))
                + " indexed=" + str(indexed_report.get("indexed", 0))
                + " embedded=" + str(indexed_report.get("embedded", 0))
                + " bm25_hits=" + str(meta.get("bm25_hits"))
                + " vector_hits=" + str(meta.get("vector_hits"))
                + " rerank=" + str(meta.get("rerank_mode"))
                + " embedding=" + str(meta.get("embedding_used") or "none")
                + " retrieved=" + str(len(context))
            )
            if meta.get("embedding_error"):
                note += " embedding_error=" + str(meta["embedding_error"])[:120]
            logger.info(
                "retrieval mode=hybrid_rrf rerank=%s bm25=%s vector=%s retrieved=%s",
                meta.get("rerank_mode"),
                meta.get("bm25_hits"),
                meta.get("vector_hits"),
                len(context),
            )
            return {"repo_context": context, "retrieval_note": note}

        # No embeddings configured: BM25 + symbol graph, exactly the
        # pre-RAG-2.0 behavior (卷IV 4.3 first row, rerank 保序).
        indexed = store.index_repository(repo_key, head_sha, files)
        hits = store.search_code(repo_key, query)

        # Symbol-graph augmentation (deterministic RAG): expand keyword hits
        # into their call neighborhood (callees/callers/siblings) so the
        # contract compiler sees the surrounding verification context.
        expanded = graph.expand_hits(
            [{k: h.get(k, "") for k in ("path", "symbol", "content")} for h in hits[:8]],
            hops=1,
        )
        merged = list(expanded) or [
            {k: h.get(k, "") for k in ("path", "symbol", "content")} for h in hits[:8]
        ]
        context = [
            {
                "path": h.get("path", ""),
                "symbol": h.get("symbol", ""),
                "content": (h.get("content") or "")[:800],
                "source": h.get("source", "bm25"),
            }
            for h in merged[:16]
        ]
        logger.info(
            "retrieval mode=bm25+graph hits=%s retrieved=%s",
            len(hits),
            len(context),
        )
        return {
            "repo_context": context,
            "retrieval_note": (
                "Indexed " + str(indexed) + " symbol chunks; "
                + str(len(context)) + " retrieved"
            ),
        }
    except Exception as exc:  # noqa: BLE001 — optional infra, honest degradation
        return {
            "repo_context": [],
            "retrieval_note": "Repository retrieval failed: " + str(exc)[:200],
        }
