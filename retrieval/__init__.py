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
from . import embeddings, hybrid, rerank
from .embeddings import EmbeddingClient
from .hybrid import RRF_K, HybridOutcome, hybrid_search, rrf_fuse
from .rerank import RerankResult
from .rerank import rerank as rerank_candidates

__all__ = [
    "EmbeddingClient",
    "HybridOutcome",
    "RRF_K",
    "RerankResult",
    "embeddings",
    "hybrid",
    "hybrid_search",
    "rerank",
    "rerank_candidates",
    "rrf_fuse",
]
