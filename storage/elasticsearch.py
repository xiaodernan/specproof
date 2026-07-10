"""Elasticsearch store — code and evidence retrieval for Phase 0."""

import os
from dataclasses import dataclass
from typing import Any

from elasticsearch import Elasticsearch


@dataclass
class ElasticsearchConfig:
    host: str = "http://localhost:9200"
    user: str = "elastic"
    password: str = "specproof_pass"

    @classmethod
    def from_env(cls) -> "ElasticsearchConfig":
        return cls(
            host=os.getenv("ES_HOST", "http://localhost:9200"),
            user=os.getenv("ES_USER", "elastic"),
            password=os.getenv("ES_PASSWORD", "specproof_pass"),
        )


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
                            "embedding": {
                                "type": "dense_vector",
                                "dims": 1536,
                                "index": False,
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
        self.client.index(index=self.INDEX_CODE, document=doc)

    def search_code(
        self, repo: str, query: str, commit_sha: str | None = None
    ) -> list[dict[str, Any]]:
        must = [
            {"term": {"repo": repo}},
            {"match": {"content": query}},
        ]
        if commit_sha:
            must.append({"term": {"commit_sha": commit_sha}})

        result = self.client.search(
            index=self.INDEX_CODE,
            body={"query": {"bool": {"must": must}}, "size": 20},
        )
        return [hit["_source"] for hit in result["hits"]["hits"]]

    def is_ready(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
