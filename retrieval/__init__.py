"""RAG 2.0 retrieval package — embeddings, reranking, hybrid RRF fusion.

Implements 卷IV 4.1-4.5 of docs/design/GRAND_PLAN_V2.md:
EmbeddingClient (BYOK /embeddings), rerank (cross-encoder → LLM → off)
and hybrid_search (BM25 + vector RRF → graph expansion → rerank →
budget truncation) with an honest degradation matrix.

Note: the "rerank" attribute of this package is the SUBMODULE
(retrieval.rerank); the function is retrieval.rerank.rerank. The function
is also exported here as "rerank_candidates" so the submodule name is
never shadowed (introspection/monkeypatching stays unambiguous).
"""
from . import bench_queries, embeddings, hybrid, rerank, symbols
from .bench_queries import (
    QUERIES,
    RetrievalQuery,
    mrr,
    recall_at_k,
    summarize_bench,
)
from .embeddings import EmbeddingClient
from .hybrid import RRF_K, HybridOutcome, hybrid_search, rrf_fuse
from .rerank import RerankResult
from .rerank import rerank as rerank_candidates
from .symbols import (
    IndexStats,
    ParseResult,
    RepoIndex,
    Symbol,
    SymbolIndex,
    SymbolIndexer,
    index_repo,
)

__all__ = [
    "EmbeddingClient",
    "HybridOutcome",
    "IndexStats",
    "ParseResult",
    "QUERIES",
    "RRF_K",
    "RepoIndex",
    "RerankResult",
    "RetrievalQuery",
    "Symbol",
    "SymbolIndex",
    "SymbolIndexer",
    "bench_queries",
    "embeddings",
    "hybrid",
    "hybrid_search",
    "index_repo",
    "mrr",
    "recall_at_k",
    "rerank",
    "rerank_candidates",
    "rrf_fuse",
    "summarize_bench",
    "symbols",
]
