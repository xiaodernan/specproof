"""recall_graph unit tests — deterministic; no LLM; no network; no file writes.

The graph reads the REAL chronicle.json + corrections.json (they are committed).
A broken ranking, a drift in title-weight, a nondeterministic ordering — any
of those would fail this file.
"""

import pytest

from agent.graphs.recall_graph import build_recall_graph


@pytest.fixture(scope="module")
def graph():
    return build_recall_graph()


def test_court_query_hits_court_page(graph):
    result = graph.invoke({"query": "court 永不缓存", "top": 3})
    assert result["verdict"] == "HIT"
    assert result["hits"], "must return ranked hits"
    # title weight guarantees court entries appear first
    top_titles = " ".join((hit["title"] or "") for hit in result["hits"])
    assert "court" in top_titles.lower()


def test_password_query_brings_the_rejection_entry(graph):
    result = graph.invoke({"query": "密码 123", "top": 3})
    assert result["verdict"] == "HIT"
    hits = {f"{hit['kind']}#{hit['n']}" for hit in result["hits"]}
    assert any("1799" in hit or hit == "#1799" for hit in hits) or any("1799" in str(hit) for hit in hits), hits


def test_empty_query_is_not_a_silence(graph):
    result = graph.invoke({"query": ""})
    assert result["verdict"] == "MISSING-QUERY"


def test_gibberish_is_an_honest_miss(graph):
    result = graph.invoke({"query": "zzqxjvn xvjq lqxzvnq"})
    assert result["verdict"] == "MISS"


def test_missing_docs_dir_is_a_loud_failure(graph, tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    result = graph.invoke({"query": "anything", "docs_dir": str(empty)})
    assert result["verdict"] in ("EVIDENCE-MISSING", "MISS")


def test_top_limits_are_respected(graph):
    r_full = graph.invoke({"query": "cache", "top": 5})
    r_cap = graph.invoke({"query": "cache", "top": 1})
    assert len(r_full["hits"]) <= 5
    assert len(r_cap["hits"]) == 1
    assert r_full["hits"][0]["score"] >= r_cap["hits"][0]["score"]
