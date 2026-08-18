"""Elasticsearch store — code and evidence retrieval.

P2: repository-level symbol indexing (method-level chunks), BM25
retrieval with repository isolation, and (RAG 2.0, 卷IV 4.1) the
dense-vector channel: HNSW-enabled embeddings, index_with_embeddings and
vector_search. Existing BM25 behavior is unchanged.
"""
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from elasticsearch import Elasticsearch

if TYPE_CHECKING:
    from retrieval.embeddings import EmbeddingClient


@dataclass
class ElasticsearchConfig:
    host: str = "http://localhost:9200"
    user: str = "elastic"
    password: str = "specproof_pass"
    # RAG 2.0: dense_vector dims must match the embedding model (卷IV 4.1).
    vector_dims: int = 1536

    @classmethod
    def from_env(cls) -> "ElasticsearchConfig":
        try:
            vector_dims = max(1, int(os.getenv("ES_VECTOR_DIMS", "1536")))
        except ValueError:
            vector_dims = 1536
        return cls(
            host=os.getenv("ES_HOST", "http://localhost:9200"),
            user=os.getenv("ES_USER", "elastic"),
            password=os.getenv("ES_PASSWORD", "specproof_pass"),
            vector_dims=vector_dims,
        )


def _chunk_files(
    repo: str, commit_sha: str, files: dict[str, str],
) -> list[dict[str, Any]]:
    """Split a repository snapshot into method-level symbol chunks."""
    try:
        from agent.checkers.java_source import _split_with_annotations
    except ImportError:
        _split_with_annotations = None  # type: ignore[assignment]

    docs: list[dict[str, Any]] = []
    for path, content in files.items():
        if path.endswith(".java") and _split_with_annotations is not None:
            chunks = [
                (block, name)
                for block, name in _split_with_annotations(content)
            ]
            if not chunks:
                chunks = [(content, path)]
        else:
            chunks = [(content, path)]
        for block, symbol in chunks:
            docs.append({
                "repo": repo,
                "commit_sha": commit_sha,
                "path": path,
                "symbol": symbol,
                "language": "java" if path.endswith(".java") else "text",
                "content": block[:4000],
                "start_line": 0,
                "end_line": 0,
            })
    return docs


def _bulk_operations(
    docs: list[dict[str, Any]], index: str,
) -> list[dict[str, Any]]:
    """Interleave index actions and documents for one bulk call."""
    operations: list[dict[str, Any]] = []
    for doc in docs:
        operations.append({"index": {"_index": index}})
        operations.append(doc)
    return operations


class ElasticsearchStore:
    """Code and evidence retrieval store."""

    INDEX_CODE = "specproof-code-phase0"

    def __init__(self, config: ElasticsearchConfig | None = None) -> None:
        self.config = config or ElasticsearchConfig.from_env()
        self._client: Elasticsearch | None = None

    @property
    def client(self) -> Elasticsearch:
        if self._client is None:
            self._client = Elasticsearch(
                hosts=[self.config.host],
                basic_auth=(self.config.user, self.config.password),
                request_timeout=30,
                verify_certs=False,
            )
        return self._client

    def ensure_indices(self) -> None:
        if not self.client.indices.exists(index=self.INDEX_CODE):
            self.client.indices.create(
                index=self.INDEX_CODE,
                body={
                    "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                    "mappings": {
                        "properties": {
                            "repo": {"type": "keyword"},
                            "commit_sha": {"type": "keyword"},
                            "path": {"type": "keyword"},
                            "symbol": {"type": "keyword"},
                            "language": {"type": "keyword"},
                            "content": {"type": "text"},
                            # RAG 2.0: HNSW-enabled vector channel (卷IV 4.1).
                            "embedding": {
                                "type": "dense_vector",
                                "dims": self.config.vector_dims,
                                "index": True,
                                "similarity": "cosine",
                                "index_options": {
                                    "type": "hnsw",
                                    "m": 16,
                                    "ef_construction": 100,
                                },
                            },
                            "start_line": {"type": "integer"},
                            "end_line": {"type": "integer"},
                        }
                    },
                },
            )

    def index_code_block(
        self,
        repo: str,
        commit_sha: str,
        path: str,
        symbol: str,
        content: str,
        start_line: int = 0,
        end_line: int = 0,
        embedding: list[float] | None = None,
    ) -> None:
        doc = {
            "repo": repo,
            "commit_sha": commit_sha,
            "path": path,
            "symbol": symbol,
            "language": "java",
            "content": content,
            "start_line": start_line,
            "end_line": end_line,
        }
        if embedding is not None:
            doc["embedding"] = embedding
        # refresh=True makes the document immediately searchable; without it
        # a search right after indexing returns nothing (near-real-time).
        self.client.index(index=self.INDEX_CODE, document=doc, refresh=True)

    def search_code(
        self,
        repo: str,
        query: str,
        commit_sha: str | None = None,
        size: int = 20,
    ) -> list[dict[str, Any]]:
        must = [
            {"term": {"repo": repo}},
            {
                "bool": {
                    "should": [
                        {"match": {"content": query}},
                        {"match": {"symbol": query}},
                    ],
                    "minimum_should_match": 1,
                }
            },
        ]
        if commit_sha:
            must.append({"term": {"commit_sha": commit_sha}})

        result = self.client.search(
            index=self.INDEX_CODE,
            body={"query": {"bool": {"must": must}}, "size": size},
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def index_repository(
        self, repo: str, commit_sha: str, files: dict[str, str],
    ) -> int:
        """Index one repository snapshot as symbol-level chunks.

        files maps posix relative paths to source content. Java files are
        split into method blocks (AST-free symbol chunking) so retrieval
        returns the relevant symbol, not an arbitrary 500-char window.
        Returns the number of indexed chunks.
        """
        self.ensure_indices()
        self.delete_repo(repo)  # idempotent re-index

        docs = _chunk_files(repo, commit_sha, files)

        # Bulk + ONE refresh: per-document refresh=True costs a disk sync
        # per chunk (30+ chunks took minutes and blew past every timeout).
        if docs:
            self.client.bulk(
                operations=_bulk_operations(docs, self.INDEX_CODE), refresh=True
            )
        return len(docs)

    def index_with_embeddings(
        self,
        repo: str,
        commit_sha: str,
        files: dict[str, str],
        embedder: "EmbeddingClient",
    ) -> dict[str, Any]:
        """Index chunks with vectors from an EmbeddingClient (RAG 2.0).

        Every chunk is indexed regardless of vector availability (BM25
        stays usable — 卷IV 4.3). Chunks whose vector is missing or
        dims-mismatched are indexed without the embedding field. Returns
        honest counts: indexed / embedded / vectors_skipped / notes.
        """
        self.ensure_indices()
        self.delete_repo(repo)  # idempotent re-index
        docs = _chunk_files(repo, commit_sha, files)
        embedded = 0
        skipped = 0
        notes: list[str] = []
        if docs:
            vectors, reason = embedder.embed([d["content"] for d in docs])
            if vectors is None:
                notes.append("embeddings unavailable: " + reason)
            else:
                for doc, vector in zip(docs, vectors, strict=False):
                    if len(vector) == self.config.vector_dims:
                        doc["embedding"] = vector
                        embedded += 1
                    else:
                        skipped += 1
                if skipped:
                    notes.append(
                        str(skipped) + " vectors dims-mismatched ("
                        + str(self.config.vector_dims)
                        + " expected) — indexed without embedding"
                    )
            self.client.bulk(
                operations=_bulk_operations(docs, self.INDEX_CODE), refresh=True
            )
        return {
            "indexed": len(docs),
            "embedded": embedded,
            "vectors_skipped": skipped,
            "embedding_notes": notes,
        }

    def vector_search(
        self,
        repo: str,
        query_vector: list[float],
        k: int = 10,
        commit_sha: str | None = None,
    ) -> list[dict[str, Any]]:
        """kNN over the embedding field, repository-isolated (RAG 2.0).

        Documents without a vector are skipped by ES; an empty result
        means "no vector data" and callers fall back to BM25 (卷IV 4.3).
        Hits carry their similarity as "vector_score".
        """
        repo_filter: dict[str, Any] = {"term": {"repo": repo}}
        if commit_sha:
            repo_filter = {
                "bool": {
                    "must": [repo_filter, {"term": {"commit_sha": commit_sha}}]
                }
            }
        body = {
            "knn": {
                "field": "embedding",
                "query_vector": query_vector,
                "k": k,
                "num_candidates": min(200, max(10, k * 5)),
                "filter": repo_filter,
            },
            "size": k,
        }
        result = self.client.search(index=self.INDEX_CODE, body=body)
        return [
            {**hit["_source"], "vector_score": float(hit.get("_score", 0.0))}
            for hit in result["hits"]["hits"]
        ]

    def delete_repo(self, repo: str) -> None:
        """Remove all documents of one repository (re-index idempotency).

        Implemented as delete-index + recreate: elasticsearch-py 8.19.x
        hard-crashes on Windows inside delete_by_query (native fault in the
        transport layer), while the plain DELETE index request is stable.
        """
        self.client.indices.delete(
            index=self.INDEX_CODE, ignore_unavailable=True
        )
        self.ensure_indices()

    def count_repo_docs(self, repo: str) -> int:
        """Number of indexed chunks for a repository (0 when absent)."""
        if not self.client.indices.exists(index=self.INDEX_CODE):
            return 0
        result = self.client.count(
            index=self.INDEX_CODE,
            body={"query": {"term": {"repo": repo}}},
        )
        return int(result.get("count", 0))

    def is_ready(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
