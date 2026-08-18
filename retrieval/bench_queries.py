"""30-query golden set + metric helpers for the retrieval benchmark.

SpecCraft 计划书 §22-5 / M2 (docs/architecture/AGENT_PLAN_GAP_AUDIT.md 任务5).
Corpus: python = cli/ + agent/ + craft/; java = demo/spring-backend.
Expected-file sets are ground-truthed against the corpus (grep-verified on
2026-08-18): a file is expected when it defines or directly evidences the
queried behavior — the sets are NOT tuned to any retrieval system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EVAL_K = 10  # recall cutoff; MRR ranks the full returned list

DEMO_MAIN = "demo/spring-backend/src/main/java/com/specproof/demo"
DEMO_TEST = "demo/spring-backend/src/test/java/com/specproof/demo"

CTRL_USER = f"{DEMO_MAIN}/controller/UserController.java"
SRV_USER = f"{DEMO_MAIN}/service/UserService.java"
TEST_USER = f"{DEMO_TEST}/UserControllerTest.java"
CFG_SEC = f"{DEMO_MAIN}/config/SecurityConfig.java"
ENTITY_USER = f"{DEMO_MAIN}/entity/User.java"
REPO_USER = f"{DEMO_MAIN}/repository/UserRepository.java"
CTRL_ORDER = f"{DEMO_MAIN}/controller/OrderController.java"
SRV_ORDER = f"{DEMO_MAIN}/service/OrderService.java"
TEST_ORDER = f"{DEMO_TEST}/OrderControllerTest.java"
EVENT_ORDER = f"{DEMO_MAIN}/event/OrderCreatedEvent.java"
EVENT_EMAIL = f"{DEMO_MAIN}/event/EmailChangedEvent.java"


@dataclass(frozen=True)
class RetrievalQuery:
    """One golden query: id, type, text, language, expected files."""

    query_id: str
    qtype: str  # symbol | requirement | error
    text: str
    language: str  # python | java
    expected: tuple[str, ...]


QUERIES: list[RetrievalQuery] = [
    # --- 10 symbol-name queries -------------------------------------------
    RetrievalQuery("s01", "symbol", "RepoGraph", "python", ("agent/repo_graph.py",)),
    RetrievalQuery("s02", "symbol", "MongoDBSaver", "python", ("agent/mongo_saver.py",)),
    RetrievalQuery("s03", "symbol", "CraftLoop", "python", ("craft/loop.py",)),
    RetrievalQuery("s04", "symbol", "compile_plan", "python", ("craft/planner.py",)),
    RetrievalQuery(
        "s05", "symbol", "deterministic_baseline", "python",
        ("cli/specproof/commands/baseline.py",),
    ),
    RetrievalQuery(
        "s06", "symbol", "contract_results_for", "python",
        ("agent/checkers/java_source.py",),
    ),
    RetrievalQuery(
        "s07", "symbol", "changeEmail", "java",
        (CTRL_USER, SRV_USER, TEST_USER),
    ),
    RetrievalQuery(
        "s08", "symbol", "placeOrder", "java",
        (CTRL_ORDER, SRV_ORDER, TEST_ORDER),
    ),
    RetrievalQuery(
        "s09", "symbol", "EmailChangedEvent", "java",
        (SRV_USER, EVENT_EMAIL),
    ),
    RetrievalQuery("s10", "symbol", "invalidateOldTokens", "java", (SRV_USER,)),

    # --- 10 requirement-sentence queries -------------------------------------
    RetrievalQuery(
        "r01", "requirement",
        "用户修改邮箱必须先认证(@PreAuthorize)并作废旧令牌(invalidateOldTokens)",
        "java", (CTRL_USER, SRV_USER, CFG_SEC),
    ),
    RetrievalQuery(
        "r02", "requirement",
        "下单前校验库存(stock)下单后发布订单创建事件(OrderCreatedEvent)",
        "java", (CTRL_ORDER, SRV_ORDER, EVENT_ORDER),
    ),
    RetrievalQuery(
        "r03", "requirement", "用户邮箱必须唯一(unique, existsByEmail)",
        "java", (ENTITY_USER, SRV_USER, REPO_USER),
    ),
    RetrievalQuery(
        "r04", "requirement", "构建 Phase0 状态图并发布报告(publish_report)",
        "python", ("agent/graph.py", "agent/nodes/publish_report.py"),
    ),
    RetrievalQuery(
        "r05", "requirement", "合并契约结果 FAIL 优先 PASS 次之 UNVERIFIED",
        "python",
        (
            "agent/contract_results.py",
            "agent/nodes/run_static_checks.py",
            "agent/nodes/run_differential.py",
        ),
    ),
    RetrievalQuery(
        "r06", "requirement", "执行器命令白名单(allowlist)并提取 pytest 失败测试",
        "python", ("craft/executor.py",),
    ),
    RetrievalQuery(
        "r07", "requirement", "编辑器原子写入(atomic write)备份与审计日志(audit)",
        "python", ("craft/editor.py",),
    ),
    RetrievalQuery(
        "r08", "requirement", "LLM 不可用时降级到确定性计划(deterministic fallback)",
        "python", ("craft/planner.py", "craft/llm.py"),
    ),
    RetrievalQuery(
        "r09", "requirement", "安全扫描 canary 与密钥泄漏(secret leak)",
        "python", ("agent/security_scanner.py",),
    ),
    RetrievalQuery(
        "r10", "requirement", "预检 JDK(JAVA_HOME) Maven Wrapper(mvnw) 与 Docker",
        "python", ("agent/preflight.py",),
    ),

    # --- 10 error-message queries ---------------------------------------------
    RetrievalQuery(
        "e01", "error", "CommandNotAllowedError", "python",
        ("craft/executor.py", "craft/__init__.py"),
    ),
    RetrievalQuery("e02", "error", "STUCK", "python", ("craft/loop.py",)),
    RetrievalQuery(
        "e03", "error", "EditError", "python",
        ("craft/editor.py", "craft/__init__.py"),
    ),
    RetrievalQuery(
        "e04", "error", "PlanTooComplexError", "python",
        ("craft/planner.py", "craft/__init__.py"),
    ),
    RetrievalQuery(
        "e05", "error", "LLMUnavailableError", "python",
        ("craft/llm.py", "craft/__init__.py"),
    ),
    RetrievalQuery(
        "e06", "error", "BudgetError", "python",
        ("craft/budget.py", "craft/__init__.py"),
    ),
    RetrievalQuery(
        "e07", "error", "Expected status 401 changeEmail unauthorized",
        "java", (TEST_USER, CTRL_USER),
    ),
    RetrievalQuery(
        "e08", "error", "changeEmail duplicate email already registered",
        "java", (TEST_USER, SRV_USER),
    ),
    RetrievalQuery(
        "e09", "error", "缺少 JAVA_HOME 或 Maven Wrapper(mvnw) 检查失败",
        "python", ("agent/preflight.py",),
    ),
    RetrievalQuery(
        "e10", "error", "库存不足(stock insufficient)时下单失败",
        "java", (SRV_ORDER, TEST_ORDER),
    ),
]


def recall_at_k(hits: list[str], expected: set[str], k: int = EVAL_K) -> float:
    """Fraction of expected files present in the top-k hit paths."""
    if not expected:
        return 1.0
    return len(set(hits[:k]) & expected) / len(expected)


def mrr(hits: list[str], expected: set[str]) -> float:
    """Reciprocal rank of the first expected file (0.0 when never found)."""
    for rank, path in enumerate(hits, start=1):
        if path in expected:
            return 1.0 / rank
    return 0.0


@dataclass
class BenchQueryResult:
    """Evaluated result of one query against one ranked hit list."""

    query_id: str
    qtype: str
    language: str
    text: str
    expected: tuple[str, ...]
    hits: list[str]
    recall_at_10: float
    mrr: float
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_id": self.query_id,
            "qtype": self.qtype,
            "language": self.language,
            "text": self.text,
            "expected": list(self.expected),
            "hits": list(self.hits),
            "recall_at_10": self.recall_at_10,
            "mrr": self.mrr,
            "latency_ms": self.latency_ms,
        }


def evaluate_query(
    query: RetrievalQuery, hits: list[str], latency_ms: float,
) -> BenchQueryResult:
    """Score one ranked hit list against the query's expected files."""
    expected = set(query.expected)
    return BenchQueryResult(
        query_id=query.query_id,
        qtype=query.qtype,
        language=query.language,
        text=query.text,
        expected=query.expected,
        hits=list(hits),
        recall_at_10=recall_at_k(hits, expected),
        mrr=mrr(hits, expected),
        latency_ms=latency_ms,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize_bench(
    results: list[BenchQueryResult],
    *,
    corpus_files: int = 0,
    index_symbols: int = 0,
    mode: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate per-query results into overall + per-qtype summaries."""
    def group(items: list[BenchQueryResult]) -> dict[str, Any]:
        return {
            "queries": len(items),
            "recall_at_10": _mean([r.recall_at_10 for r in items]),
            "mrr": _mean([r.mrr for r in items]),
            "avg_latency_ms": _mean([r.latency_ms for r in items]),
            "found_expected": sum(1 for r in items if r.recall_at_10 >= 1.0),
        }

    by_type: dict[str, dict[str, Any]] = {}
    for qtype in ("symbol", "requirement", "error"):
        subset = [r for r in results if r.qtype == qtype]
        if subset:
            by_type[qtype] = group(subset)
    summary: dict[str, Any] = {
        "mode": mode,
        "corpus_files": corpus_files,
        "index_symbols": index_symbols,
        "overall": group(results),
        "by_type": by_type,
        "per_query": [r.to_dict() for r in results],
    }
    if extra:
        summary["extra"] = dict(extra)
    return summary


__all__ = [
    "EVAL_K",
    "QUERIES",
    "BenchQueryResult",
    "RetrievalQuery",
    "evaluate_query",
    "mrr",
    "recall_at_k",
    "summarize_bench",
]
