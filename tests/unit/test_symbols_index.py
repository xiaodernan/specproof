"""Unit tests for the four-language symbol indexer + retrieval bench metrics.

All tests are pure / tmp_path / mock-only: no Elasticsearch, no network,
no git. Covers: four-language parsing, syntax-error tolerance, exclusions,
graph edges, expansion, lookup search, and benchmark aggregation math.
"""
from __future__ import annotations

from pathlib import Path

from retrieval.bench_queries import (
    QUERIES,
    RetrievalQuery,
    evaluate_query,
    mrr,
    recall_at_k,
    summarize_bench,
)
from retrieval.symbols import (
    Symbol,
    SymbolIndex,
    SymbolIndexer,
    index_repo,
)

PY_SAMPLE = '''\
import os
from pathlib import Path

MAX_RETRIES = 3


class UserService:
    def change_email(self, user_id: int) -> bool:
        user = load_user(user_id)
        return update_email(user)


def load_user(user_id: int) -> dict:
    return {"id": user_id}
'''

TS_SAMPLE = '''\
import { join } from 'path';

export function fetchData(url: string) {
  return httpGet(url);
}

export const handleClick = (event: any) => event;

export interface User {
  id: number;
}

export class UserRepo {
  save(user: User) {
    return persist(user);
  }
}

export { fetchData, UserRepo };
'''

JAVA_SAMPLE = '''\
package com.demo;

import java.util.List;

public class UserController {

    @PreAuthorize("isAuthenticated()")
    public Response changeEmail(ChangeEmailRequest request) {
        return userService.changeEmail(request);
    }

    public List<User> listUsers() {
        return userRepository.findAll();
    }
}
'''

GO_SAMPLE = '''\
package main

import (
	"fmt"
	"os"
)

type Config struct {
	Port int
}

func New() *Config {
	return &Config{}
}

func (s *Server) Handle(req Request) error {
	log(req)
	return nil
}
'''


# ---------------------------------------------------------------------------
# symbol data model
# ---------------------------------------------------------------------------


def test_symbol_dict_shape() -> None:
    sym = Symbol("f", "function", "a.py", 3, refs=["g"], language="python")
    data = sym.to_dict()
    assert data["name"] == "f"
    assert data["kind"] == "function"
    assert data["file"] == "a.py"
    assert data["line"] == 3
    assert data["refs"] == ["g"]
    assert data["language"] == "python"
    assert data["conservative"] is False
    assert sym.symbol_id == "a.py:3:f"


# ---------------------------------------------------------------------------
# python (ast)
# ---------------------------------------------------------------------------


def test_parse_python_kinds_lines_refs_calls() -> None:
    result = SymbolIndexer.parse_python(PY_SAMPLE, file="sample.py")
    by_name = {s.name: s for s in result.symbols}
    assert sorted(by_name) == [
        "MAX_RETRIES", "Path", "UserService", "change_email", "load_user", "os",
    ]
    assert by_name["os"].kind == "import" and by_name["os"].line == 1
    assert by_name["Path"].kind == "import" and by_name["Path"].line == 2
    assert by_name["MAX_RETRIES"].kind == "assign" and by_name["MAX_RETRIES"].line == 4
    assert by_name["UserService"].kind == "class" and by_name["UserService"].line == 7
    assert by_name["change_email"].kind == "method" and by_name["change_email"].line == 8
    assert by_name["load_user"].kind == "function" and by_name["load_user"].line == 13
    assert set(by_name["change_email"].refs) == {
        "load_user", "update_email", "user", "user_id",
    }
    assert by_name["load_user"].refs == ["user_id"]
    assert set(result.calls) == {
        ("sample.py:8:change_email", "load_user"),
        ("sample.py:8:change_email", "update_email"),
    }
    assert result.notes == []
    assert all(s.language == "python" for s in result.symbols)


def test_parse_python_syntax_error_degrades_to_empty_plus_note() -> None:
    result = SymbolIndexer.parse_python("def broken(:\n", file="bad.py")
    assert result.symbols == []
    assert len(result.notes) == 1
    assert "syntax" in result.notes[0]
    assert "bad.py" in result.notes[0]


# ---------------------------------------------------------------------------
# typescript (conservative regex)
# ---------------------------------------------------------------------------


def test_parse_typescript_conservative() -> None:
    result = SymbolIndexer.parse_typescript(TS_SAMPLE, file="app.ts")
    kinds: dict[str, list[str]] = {}
    for sym in result.symbols:
        kinds.setdefault(sym.name, []).append(sym.kind)
    assert kinds["path"] == ["import"]
    assert kinds["fetchData"] == ["function", "export"]
    assert kinds["handleClick"] == ["function"]
    assert kinds["User"] == ["interface"]
    assert kinds["UserRepo"] == ["class", "export"]
    fetch = next(s for s in result.symbols if s.name == "fetchData" and s.kind == "function")
    assert fetch.line == 3
    assert fetch.refs == ["httpGet"]
    repo = next(s for s in result.symbols if s.name == "UserRepo" and s.kind == "class")
    assert repo.line == 13
    assert repo.refs == ["persist"]
    imp = next(s for s in result.symbols if s.name == "path")
    assert imp.line == 1
    assert all(s.conservative for s in result.symbols)
    assert all(s.language == "typescript" for s in result.symbols)
    assert any("conservative" in note for note in result.notes)


# ---------------------------------------------------------------------------
# java (repo_graph style)
# ---------------------------------------------------------------------------


def test_parse_java_repo_graph_style() -> None:
    result = SymbolIndexer.parse_java(JAVA_SAMPLE, file="UserController.java")
    kinds: dict[str, list[tuple[str, int]]] = {}
    for sym in result.symbols:
        kinds.setdefault(sym.name, []).append((sym.kind, sym.line))
    assert kinds == {
        "UserController": [("class", 5)],
        "changeEmail": [("method", 7)],
        "listUsers": [("method", 10)],
        "java.util.List": [("import", 3)],
    }
    change = next(s for s in result.symbols if s.name == "changeEmail")
    assert change.refs == ["changeEmail"]
    list_users = next(s for s in result.symbols if s.name == "listUsers")
    assert list_users.refs == ["findAll"]
    assert all(s.language == "java" for s in result.symbols)
    assert all(not s.conservative for s in result.symbols)
    assert result.notes == []


# ---------------------------------------------------------------------------
# go (conservative regex)
# ---------------------------------------------------------------------------


def test_parse_go_func_type_import() -> None:
    result = SymbolIndexer.parse_go(GO_SAMPLE, file="main.go")
    kinds: dict[str, list[tuple[str, int]]] = {}
    for sym in result.symbols:
        kinds.setdefault(sym.name, []).append((sym.kind, sym.line))
    assert kinds["fmt"] == [("import", 3)]
    assert kinds["os"] == [("import", 3)]
    assert kinds["Config"] == [("type", 8)]
    assert kinds["New"] == [("function", 12)]
    assert kinds["Handle"] == [("method", 16)]
    handle = next(s for s in result.symbols if s.name == "Handle")
    assert handle.refs == ["log"]
    new = next(s for s in result.symbols if s.name == "New")
    assert new.refs == []
    assert all(s.language == "go" for s in result.symbols)
    assert any("conservative" in note for note in result.notes)


# ---------------------------------------------------------------------------
# repo indexing: exclusions / include_dirs / per-file failure isolation
# ---------------------------------------------------------------------------


def test_index_repo_exclusions_and_error_notes(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("class Beta:\n    pass\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "c.py").write_text("def hidden():\n    pass\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "d.ts").write_text(
        "export function hiddenTs() {}\n", encoding="utf-8",
    )
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "e.go").write_text(
        "package skip\n\nfunc skipped() {}\n", encoding="utf-8",
    )
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# not source\n", encoding="utf-8")

    result = index_repo(str(tmp_path), exclusions=["skip"])
    assert sorted(s.name for s in result.symbols) == ["Beta", "alpha"]
    assert result.stats.files_scanned == 3
    assert result.stats.files_failed == 0
    assert result.stats.symbol_count == 2
    assert result.stats.symbols_by_language == {"python": 2}
    assert result.stats.errors == []
    assert any("bad.py" in note for note in result.stats.notes)


def test_index_repo_include_dirs(tmp_path: Path) -> None:
    (tmp_path / "cli").mkdir()
    (tmp_path / "storage").mkdir()
    (tmp_path / "demo").mkdir()
    (tmp_path / "cli" / "a.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    (tmp_path / "storage" / "b.py").write_text("class Beta:\n    pass\n", encoding="utf-8")
    (tmp_path / "demo" / "c.java").write_text("public class C {}\n", encoding="utf-8")

    result = index_repo(str(tmp_path), include_dirs=["cli", "demo"])
    assert sorted(s.name for s in result.symbols) == ["C", "alpha"]
    assert result.stats.symbols_by_language == {"python": 1, "java": 1}
    assert result.stats.files_scanned == 2


def test_index_files_ignores_unknown_extensions() -> None:
    result = SymbolIndexer.index_files(
        {"x.md": "# hi", "y.py": "def f():\n    pass\n"}
    )
    assert {s.name for s in result.symbols} == {"f"}
    assert result.stats.files_scanned == 2
    assert result.stats.files_ok == 2
    assert result.stats.files_failed == 0


def test_index_files_collects_parse_failures_without_aborting() -> None:
    result = SymbolIndexer.index_files(
        {
            "good.py": "def ok():\n    return 1\n",
            "bad.py": "def broken(:\n",
            "empty.java": "",
        }
    )
    assert {s.name for s in result.symbols} == {"ok"}
    assert result.stats.files_scanned == 3
    assert result.stats.symbols_by_language == {"python": 1}
    assert any("bad.py" in note for note in result.stats.notes)


# ---------------------------------------------------------------------------
# graph edges / neighbors / expansion / lookup
# ---------------------------------------------------------------------------


def test_edges_neighbors_expand_and_search() -> None:
    files = {
        "m.py": "def main():\n    return helper()\n",
        "util.py": "def helper():\n    return 1\n",
    }
    result = SymbolIndexer.index_files(files)
    main = next(s for s in result.symbols if s.name == "main")
    helper = next(s for s in result.symbols if s.name == "helper")
    assert (main.symbol_id, "helper") in result.calls
    assert (main.symbol_id, "helper") in result.refs

    graph = SymbolIndex(result)
    assert graph.resolve("helper") == [helper]
    assert helper.symbol_id in graph.neighbors(main)
    assert main.symbol_id in graph.neighbors(helper)

    expanded = graph.expand_hits([{"path": "m.py", "symbol": "m.py"}])
    assert {"m.py", "util.py"} <= {hit["path"] for hit in expanded}
    graph_docs = [h for h in expanded if h.get("source") == "symbol_graph"]
    assert any(d["path"] == "util.py" and d["symbol"] == "helper" for d in graph_docs)

    docs = graph.search("helper")
    assert docs
    assert docs[0]["path"] == "util.py"
    assert docs[0]["symbol"] == "helper"
    assert docs[0]["source"] == "symbol_index"
    assert docs[0]["score"] >= 10.0


# ---------------------------------------------------------------------------
# benchmark metrics (pure functions)
# ---------------------------------------------------------------------------


def test_recall_at_k_and_mrr() -> None:
    assert recall_at_k(["a", "b", "c"], {"b"}) == 1.0
    assert recall_at_k(["a", "b"], {"z"}) == 0.0
    assert recall_at_k([], {"b"}) == 0.0
    assert recall_at_k(["a"], set()) == 1.0
    assert recall_at_k(["a", "b", "c", "d"], {"d"}, k=3) == 0.0
    assert mrr(["x", "a"], {"a"}) == 0.5
    assert mrr([], {"a"}) == 0.0
    assert mrr(["a"], {"z"}) == 0.0


def test_summarize_bench_math() -> None:
    query = RetrievalQuery("t1", "symbol", "x", "python", ("f.py",))
    r1 = evaluate_query(query, ["f.py"], 10.0)
    r2 = evaluate_query(query, ["other.py"], 30.0)
    summary = summarize_bench([r1, r2], mode="bm25", corpus_files=2, index_symbols=3)
    overall = summary["overall"]
    assert overall["queries"] == 2
    assert overall["recall_at_10"] == 0.5
    assert overall["mrr"] == 0.5
    assert overall["avg_latency_ms"] == 20.0
    assert overall["found_expected"] == 1
    assert summary["by_type"]["symbol"]["recall_at_10"] == 0.5
    assert summary["per_query"][0]["query_id"] == "t1"
    assert summary["per_query"][0]["hits"] == ["f.py"]


# ---------------------------------------------------------------------------
# golden set integrity
# ---------------------------------------------------------------------------


def test_golden_set_has_30_queries_balanced() -> None:
    assert len(QUERIES) == 30
    counts = {"symbol": 0, "requirement": 0, "error": 0}
    for query in QUERIES:
        counts[query.qtype] += 1
        assert query.query_id
        assert query.expected
    assert counts == {"symbol": 10, "requirement": 10, "error": 10}
    assert len({q.query_id for q in QUERIES}) == 30
    assert {q.language for q in QUERIES} == {"python", "java"}


def test_golden_expected_files_exist_in_repo() -> None:
    root = Path(__file__).resolve().parents[2]
    for query in QUERIES:
        for expected in query.expected:
            assert (root / expected).is_file(), f"{query.query_id}: missing {expected}"
