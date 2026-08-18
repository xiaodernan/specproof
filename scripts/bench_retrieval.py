"""Run the 30-query retrieval benchmark (SpecCraft 计划书 §22-5 / M2).

Baseline systems measured per query:
  1. BM25          — ElasticsearchStore.search_code (real ES) or an
                     in-memory BM25 mock (--offline, CI smoke only)
  2. BM25+graph    — top-8 BM25 hits expanded 1 hop through the
                     four-language SymbolIndex (repo_graph-equivalent)
  3. symbol-index  — deterministic name/ref lookup (bonus column)

Metrics: recall@10, MRR, per-query latency. The report is written to
docs/eval/retrieval-bench.md (overwritten on every run).

Usage:
    python scripts/bench_retrieval.py                 # real ES
    python scripts/bench_retrieval.py --offline       # mock BM25
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from retrieval.bench_queries import (  # noqa: E402
    QUERIES,
    RetrievalQuery,
    evaluate_query,
    summarize_bench,
)
from retrieval.symbols import RepoIndex, SymbolIndex, SymbolIndexer  # noqa: E402

REPO_NAME = "specproof-retrieval-bench"
COMMIT_SHA = "bench-m2"
BM25_SIZE = 20
EXPAND_TOP = 8
HOPS = 1
TOP_K = 10
CORPUS_DIRS = ("cli", "agent", "craft", "demo")
PY_SUFFIXES = (".py",)
JAVA_SUFFIXES = (".java",)
SKIP_PARTS = {"__pycache__", ".git"}


def collect_corpus() -> dict[str, str]:
    """Read the benchmark corpus: cli/agent/craft (*.py) + demo (*.java)."""
    files: dict[str, str] = {}
    for dir_name in CORPUS_DIRS:
        base = REPO_ROOT / dir_name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if SKIP_PARTS.intersection(path.parts):
                continue
            if dir_name == "demo":
                if path.suffix.lower() not in JAVA_SUFFIXES:
                    continue
            elif path.suffix.lower() not in PY_SUFFIXES:
                continue
            try:
                files[path.relative_to(REPO_ROOT).as_posix()] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                continue
    return files


class MockBM25Store:
    """In-memory BM25 (--offline): word-token tf/idf over path+content.

    CI smoke runs only — offline numbers are marked as such in the report
    and are NOT the measured baseline (that one uses Elasticsearch).
    """

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self._tf: list[dict[str, int]] = []
        self._df: dict[str, int] = {}
        self._n = 0

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9_$]+", text.lower())

    def index_repository(
        self, repo: str, commit_sha: str, files: dict[str, str],
    ) -> int:
        del repo, commit_sha
        self.docs = []
        self._tf = []
        self._df = {}
        for path, content in files.items():
            tokens = self._tokens(f"{path} {path} {content}")
            tf: dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            self.docs.append({
                "repo": REPO_NAME,
                "commit_sha": COMMIT_SHA,
                "path": path,
                "symbol": path,
                "language": "java" if path.endswith(".java") else "text",
                "content": content[:4000],
            })
            self._tf.append(tf)
            for token in tf:
                self._df[token] = self._df.get(token, 0) + 1
        self._n = len(self.docs)
        return self._n

    def search_code(
        self, repo: str, query: str, commit_sha: str | None = None, size: int = 20,
    ) -> list[dict[str, Any]]:
        del repo, commit_sha
        k1, b = 1.2, 0.75
        scored: list[tuple[float, dict[str, Any]]] = []
        for tf, doc in zip(self._tf, self.docs, strict=True):
            score = 0.0
            for token in self._tokens(query):
                freq = tf.get(token, 0)
                if not freq:
                    continue
                df = self._df.get(token, 0)
                idf = math.log(1.0 + (self._n - df + 0.5) / (df + 0.5))
                score += idf * (freq * (k1 + 1.0)) / (freq + k1 * (1.0 - b + b))
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda item: (-item[0], item[1]["path"]))
        return [dict(doc) for _, doc in scored[:size]]


def _unique_paths(hits: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for hit in hits:
        path = str(hit.get("path", ""))
        if path and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def run_bench(
    store: Any,
    symbol_index: SymbolIndex,
    *,
    expand: bool,
) -> dict[str, Any]:
    """Run all 30 queries through the three systems; return raw rows."""
    rows: list[dict[str, Any]] = []
    for query in QUERIES:
        t0 = time.perf_counter()
        raw_hits = store.search_code(REPO_NAME, query.text, size=BM25_SIZE)
        t1 = time.perf_counter()
        bm25_paths = _unique_paths(raw_hits)

        t2 = time.perf_counter()
        expanded_hits = (
            symbol_index.expand_hits(raw_hits[:EXPAND_TOP], hops=HOPS)
            if expand
            else list(raw_hits)
        )
        t3 = time.perf_counter()
        graph_paths = _unique_paths(expanded_hits)

        t4 = time.perf_counter()
        symbol_hits = symbol_index.search(query.text, top_k=TOP_K)
        t5 = time.perf_counter()
        symbol_paths = _unique_paths(symbol_hits)

        rows.append({
            "query": query,
            "bm25": evaluate_query(query, bm25_paths, (t1 - t0) * 1000.0),
            "bm25_graph": evaluate_query(
                query, graph_paths, (t1 - t0) * 1000.0 + (t3 - t2) * 1000.0
            ),
            "symbol_index": evaluate_query(query, symbol_paths, (t5 - t4) * 1000.0),
        })
    return {
        "bm25": summarize_bench([r["bm25"] for r in rows], mode="bm25"),
        "bm25_graph": summarize_bench([r["bm25_graph"] for r in rows], mode="bm25+graph"),
        "symbol_index": summarize_bench([r["symbol_index"] for r in rows], mode="symbol-index"),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# report rendering (docs/eval/retrieval-bench.md)
# ---------------------------------------------------------------------------


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _ms(value: float) -> str:
    return f"{value:.1f}"


def _hits_md(paths: list[str], expected: set[str], limit: int = 10) -> str:
    if not paths:
        return "(无命中)"
    parts: list[str] = []
    for rank, path in enumerate(paths[:limit], start=1):
        mark = "✔" if path in expected else "·"
        parts.append(f"{rank}. {mark} {path}")
    if len(paths) > limit:
        parts.append(f"… 共 {len(paths)} 条")
    return "; ".join(parts)


def _summary_row(title: str, summary: dict[str, Any]) -> str:
    overall = summary["overall"]
    return (
        f"| {title} | {_pct(overall['recall_at_10'])} | {overall['mrr']:.3f} | "
        f"{_ms(overall['avg_latency_ms'])} ms | "
        f"{overall['found_expected']}/{overall['queries']} |"
    )


def _by_type_table(summary: dict[str, Any]) -> list[str]:
    lines = ["| 类型 | n | recall@10 | MRR | 平均延迟 |", "|---|---:|---:|---:|---:|"]
    for qtype in ("symbol", "requirement", "error"):
        group = summary["by_type"].get(qtype)
        if not group:
            continue
        lines.append(
            f"| {qtype} | {group['queries']} | {_pct(group['recall_at_10'])} | "
            f"{group['mrr']:.3f} | {_ms(group['avg_latency_ms'])} ms |"
        )
    return lines


def render_report(
    bench: dict[str, Any],
    index: RepoIndex,
    *,
    offline: bool,
    expand: bool,
) -> str:
    """Render docs/eval/retrieval-bench.md from measured results."""
    stats = index.stats
    lang_rows = ", ".join(
        f"{lang}={count}" for lang, count in sorted(stats.symbols_by_language.items())
    )
    kind_rows = ", ".join(
        f"{kind}={count}" for kind, count in sorted(stats.symbols_by_kind.items())
    )
    if offline:
        backend = "内存 mock BM25, --offline (仅 CI 冒烟)"
    else:
        backend = "真实 Elasticsearch localhost:9200 · index specproof-code-phase0"
    expand_desc = f"开, top-{EXPAND_TOP}×{HOPS} 跳" if expand else "关"

    lines: list[str] = []
    add = lines.append
    add("# 检索基准实测报告 — 30 查询黄金集 (M2 / §22-5)")
    add("")
    add(f"- 生成时间: {_now_iso()}")
    add(f"- 基线: BM25 ({backend}) + 图谱扩展 ({expand_desc})")
    add(
        f"- 语料: cli/ + agent/ + craft/ (Python) + demo/spring-backend (Java) · "
        f"repo={REPO_NAME} · commit_sha={COMMIT_SHA}"
    )
    add("")
    add("## 方法")
    add("")
    add(
        "- 30 条黄金查询 (10 符号名 / 10 需求句 / 10 错误信息), 每条固定期望文件集; "
        "期望集以「定义或直接佐证该查询行为」为准, 2026-08-18 按语料 grep 核验, "
        "未按任何检索系统调参。"
    )
    add(
        "- 指标: recall@10 (期望文件在前 10 条去重路径中的占比) / MRR "
        "(首个期望文件排名倒数) / 平均延迟 (search+expand 墙钟, 30 查询平均)。"
    )
    add(
        "- 对比系统: BM25 (storage.elasticsearch.search_code, 现有实现只读复用) → "
        "BM25+图谱 (retrieval.symbols.SymbolIndex.expand_hits, 与 agent.repo_graph "
        "同风格) → symbol-index (符号名/引用确定性查表, 附加列)。"
    )
    add("")
    add("## 索引统计")
    add("")
    add(
        f"- 文件: scanned={stats.files_scanned} · ok={stats.files_ok} · "
        f"failed={stats.files_failed}"
    )
    add(f"- 符号: {stats.symbol_count} · 按语言: {lang_rows}")
    add(f"- 符号按 kind: {kind_rows}")
    add(f"- 边: calls={len(index.calls)} · refs={len(index.refs)}")
    if stats.errors:
        add("- parse/read errors:")
        for error in stats.errors[:20]:
            add(f"  - {error}")
    if stats.notes:
        add(f"- notes (保守模式标注等, {len(stats.notes)} 条, 样例):")
        for note in stats.notes[:5]:
            add(f"  - {note}")
    add("")
    add("## 汇总 (n=30)")
    add("")
    add("| 系统 | recall@10 | MRR | 平均延迟 | 全命中查询数 |")
    add("|---|---:|---:|---:|---:|")
    add(_summary_row("BM25", bench["bm25"]))
    add(_summary_row("BM25+graph", bench["bm25_graph"]))
    add(_summary_row("symbol-index", bench["symbol_index"]))
    add("")
    add("### 按查询类型 (BM25+graph)")
    add("")
    add("\n".join(_by_type_table(bench["bm25_graph"])))
    add("")
    add("## 每查询明细")
    add("")
    for row in bench["rows"]:
        query: RetrievalQuery = row["query"]
        bm25_res = row["bm25"]
        graph_res = row["bm25_graph"]
        sym_res = row["symbol_index"]
        expected = set(query.expected)
        add(f"### {query.query_id} · {query.qtype} · {query.language}")
        add("")
        add(f"- 查询: {query.text}")
        add(
            f"- 期望文件 ({len(query.expected)}): "
            + ", ".join(query.expected)
        )
        add(
            f"- BM25         : recall@10={_pct(bm25_res.recall_at_10)}  "
            f"MRR={bm25_res.mrr:.3f}  延迟={_ms(bm25_res.latency_ms)} ms"
        )
        add(
            f"- BM25+graph   : recall@10={_pct(graph_res.recall_at_10)}  "
            f"MRR={graph_res.mrr:.3f}  延迟={_ms(graph_res.latency_ms)} ms"
        )
        add(
            f"- symbol-index : recall@10={_pct(sym_res.recall_at_10)}  "
            f"MRR={sym_res.mrr:.3f}  延迟={_ms(sym_res.latency_ms)} ms"
        )
        add(f"- BM25 top-10: {_hits_md(bm25_res.hits, expected)}")
        if expand:
            add(f"- +graph top-10: {_hits_md(graph_res.hits, expected)}")
        add("")
    add("## 诚实性说明")
    add("")
    add(
        "1. 本基线的数字只覆盖 BM25 与图谱扩展; 向量/RRF 融合/重排 (卷IV 4.2, "
        "retrieval/hybrid.py 已实现) 留作后续消融, 不并入本次汇总。"
    )
    add(
        "2. ES standard 分析器不做中文分词: 中文需求/错误查询依赖内嵌技术 token "
        "(符号名/错误串) 命中; 纯中文检索不在本基线范围。"
    )
    add(
        "3. Python 文件在 ES 中按整文件成块 (symbol=path, "
        "storage.elasticsearch._chunk_files 现有行为, 未改动); Java 按方法分块。"
    )
    add(
        "3a. 已知截断: _chunk_files 把块内容截到 4000 字符, 大文件后半部分的符号 "
        "不进 ES (实测 s05 deterministic_baseline / s03 CraftLoop 因此 BM25 零命中, "
        "symbol-index 列 100% 找回 — 这正是符号索引的用途)。"
    )
    add(
        "3b. specproof-code-phase0 是共享索引, 并行的其他车道会重索引各自的 repo "
        "快照; 本基准 repo 名 (specproof-retrieval-bench) 与其他车道隔离, 每次运行 "
        "开头幂等重建自己的文档。"
    )
    add(
        "4. Java 图谱扩展使用 retrieval/symbols.py 的等价切分 (与 agent/repo_graph.py "
        "同风格); TS/Go 为保守正则, 符号标 conservative; 本基准语料不含 TS/Go 文件 "
        "(解析器由单测覆盖)。"
    )
    add("5. --offline 数字仅供 CI 冒烟, 不代表真实 ES 基线。")
    add("6. 延迟为本机 Docker ES 单次测量 (30 查询平均), 未做多轮取均值。")
    add("")
    add("## 复现")
    add("")
    add("    python scripts/bench_retrieval.py  # 真实 ES, 写 docs/eval/retrieval-bench.md")
    add("    python scripts/bench_retrieval.py --offline  # mock BM25 (CI)")
    add("    python -m pytest tests/unit/test_symbols_index.py -v")
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="30-query retrieval benchmark (M2 §22-5)")
    parser.add_argument("--out", default="docs/eval/retrieval-bench.md")
    parser.add_argument("--offline", action="store_true", help="in-memory BM25 mock")
    parser.add_argument("--no-expand", action="store_true", help="disable graph expansion")
    parser.add_argument("--size", type=int, default=BM25_SIZE, help="BM25 candidate size")
    args = parser.parse_args()

    files = collect_corpus()
    if not files:
        print("corpus empty — run from the repo checkout", file=sys.stderr)
        return 2
    index = SymbolIndexer.index_files(files)
    print(
        f"corpus={len(files)} files · symbols={index.stats.symbol_count} · "
        f"failed={index.stats.files_failed}"
    )

    if args.offline:
        store: Any = MockBM25Store()
    else:
        try:
            from storage.elasticsearch import ElasticsearchStore

            es = ElasticsearchStore()
            es.ensure_indices()
            store = es
        except Exception as exc:  # noqa: BLE001 — degrade with a clear message
            print(
                f"Elasticsearch unavailable: {exc}\nUse --offline for a mock run.",
                file=sys.stderr,
            )
            return 1

    stored = store.index_repository(REPO_NAME, COMMIT_SHA, files)
    print(f"indexed {stored} docs into repo {REPO_NAME!r}")

    bench = run_bench(store, SymbolIndex(index), expand=not args.no_expand)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = render_report(
        bench, index, offline=args.offline, expand=not args.no_expand
    )
    out_path.write_text(report, encoding="utf-8")
    print(f"report -> {out_path}")

    for mode in ("bm25", "bm25_graph", "symbol_index"):
        summary = bench[mode]["overall"]
        print(
            f"{mode:12s} recall@10={summary['recall_at_10'] * 100:.1f}%  "
            f"MRR={summary['mrr']:.3f}  avg_latency={summary['avg_latency_ms']:.1f} ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
