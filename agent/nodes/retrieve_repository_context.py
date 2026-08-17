"""retrieve_repository_context node — Elasticsearch repository retrieval (P2).

Indexes the HEAD workspace's Java sources into ES as symbol-level chunks,
then retrieves the most relevant symbols for the requirement text. The
result feeds the contract compiler so it works with repository evidence
instead of the spec text alone.

Honesty contract: when Elasticsearch is unavailable the node records a
retrieval_note and continues with an empty context — it never fabricates
retrieved content and never blocks the pipeline on optional infra.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from agent.state import Phase0State

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
        proc = subprocess.run(
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
        indexed = store.index_repository("repo:" + state.get("repo_path", ""), head_sha, files)
        hits = store.search_code(
            "repo:" + state.get("repo_path", ""), _query_terms(requirement_text)
        )

        # Symbol-graph augmentation (deterministic RAG): expand keyword hits
        # into their call neighborhood (callees/callers/siblings) so the
        # contract compiler sees the surrounding verification context.
        from agent.repo_graph import RepoGraph

        graph = RepoGraph(files)
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
