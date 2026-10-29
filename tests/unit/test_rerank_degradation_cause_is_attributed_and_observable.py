"""#523 — a degraded rerank names what stopped it, and that name reaches the operator.

WHY THIS EXISTS.  ``retrieval/rerank.py`` advertised "three honest tiers" and
tier 3 as "honestly annotated (mode=off + reason)".  The annotation was not
honest, and it was not readable.  Measured on the tree before this gate was
written:

  * ``_llm_order`` had **four** ways to fail and returned ``None`` for all of
    them: no bracketed span, a span that is not JSON, a JSON value that is not
    the requested permutation of indices, and — the one that mattered —
    ``except Exception`` around the whole call.  The caller appended **one**
    sentence for all four: ``"LLM rerank failed (invalid or missing ranking
    output)"``.  So a gateway that returned 429 until the retry budget ran out,
    a gateway that refused the connection, and a gateway that answered
    ``"I cannot help with that"`` all produced the same claim, and the claim was
    about the *reply*.  Tier 1 in the same module did the opposite
    (``"cross-encoder failed: " + str(exc)[:120]``), so the module described one
    class of event two ways and called only one of them honest.
  * the reason went nowhere.  ``hybrid.py`` writes it into
    ``meta["rerank_reason"]``; the only product reader of ``outcome.meta`` is
    ``agent/nodes/retrieve_repository_context.py``, which forwards
    ``embedding_error`` into ``retrieval_note`` and never reads
    ``rerank_reason``.  ``retrieval_note`` is the field that is persisted in the
    run summary (``worker.py`` builds it from state), **queried** by
    ``storage/mysql.py`` through ``JSON_EXTRACT(summary, '$.retrieval_note')``
    and put on notifications (``integrations/notify/templates.py``).  So the
    operator could see ``rerank=off`` and could not see why — while the design
    table (卷IV 4.3) promises "rerank_mode=off + reason".
  * the wait was not a bound.  ``_run_async`` gave up on the answer after a
    fixed budget, but the call it waits for runs the provider's own retry
    policy (``providers/openai_compatible.py``: ``AsyncRetrying(...,
    reraise=True)`` over 429/409/5xx/timeout/connection, ``LLM_MAX_RETRIES``
    default 2 — so the policy's own worst case, attempts times the per-request
    timeout plus the waits, runs past the wait).  A gateway
    that accepts the connection and stays silent therefore exceeds the wait for
    real, and the resulting ``TimeoutError`` landed in the same
    ``except Exception`` as a malformed reply.  Worse, the wait only exists when
    an event loop is already running: from a plain thread — the node's shape —
    ``_run_async`` falls through to ``asyncio.run`` and waits forever.
  * **no** rerank tier test in ``tests/unit/test_retrieval_hybrid.py`` made the
    provider raise; the fake always returned.  The folded path had no coverage
    at all.

WHAT THIS GATE PINS.  Two halves, because they need different machinery:

  A  attribution — every way tier 2 fails gets its own code and its own
     sentence, and a sentence about the gateway may not read like a sentence
     about the reply.  ``RERANK_CAUSES`` is a closed set: adding a degradation
     means registering it here, which is the point.
  B  observability — the code, and only the code, travels into
     ``retrieval_note``.  Free text does not: a reason quotes the exception that
     quoted the request, and the request carried repository source.  ``tests/
     security/test_retrieval_injection.py`` already forbids repository payload
     in this same note, so B is stated as that file states it — payload in,
     marker out — with the marker riding an exception message instead of a hit.

The 90s wait is pinned as what it is: a bound on what gets *reported*, not on
what gets cancelled (``ThreadPoolExecutor.__exit__`` joins the worker, so the
wall clock can run past it).  A test that asserted a hard wall-clock cap would
be asserting a property the code does not have.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from retrieval.embeddings import EmbeddingOutcome
from retrieval.hybrid import hybrid_search
from retrieval.rerank import (
    RERANK_CAUSES,
    RerankResult,
    _llm_provider,
    rerank,
)

ROOT = Path(__file__).resolve().parents[2]

CANDIDATES = [
    {"path": "a/Svc.java", "symbol": "send", "content": "void send() {}"},
    {"path": "b/Mail.java", "symbol": "mail", "content": "void mail() {}"},
    {"path": "c/Repo.java", "symbol": "save", "content": "void save() {}"},
]

#: Words that describe the *reply*.  They may not appear in a sentence about a
#: gateway that raised or a wait that expired: that is the exact fold this
#: number removes.
REPLY_WORDS = ("array", "json", "list", "permutation", "reply", "output")


class _Reply:
    """A provider that answers with a fixed string."""

    def __init__(self, content: str) -> None:
        self._content = content

    async def chat(self, messages: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(content=self._content)


class _Raises:
    """A provider whose call fails with a gateway-shaped error."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def chat(self, messages: Any, **kwargs: Any) -> Any:
        raise self._exc


class _Sleeps:
    def __init__(self, seconds: float) -> None:
        self._seconds = seconds

    async def chat(self, messages: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(self._seconds)
        return SimpleNamespace(content="[2, 0, 1]")


def _off(provider: Any, **kwargs: Any) -> RerankResult:
    return rerank("email change", CANDIDATES, provider=provider, **kwargs)


@pytest.fixture(autouse=True)
def _no_local_rerank_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 1 must stay out of these cases unless the case puts it in.

    ``RERANK_MODEL`` is a deployment knob; a machine that exports it would else
    watch tier 1 answer before tier 2 and every code below would be a
    cross-encoder code.
    """
    monkeypatch.delenv("RERANK_MODEL", raising=False)


# ── A. attribution: one code per way of failing ────────────────────────────


@pytest.mark.parametrize(
    ("content", "cause"),
    [
        ("here is my answer: none", "llm_output_no_json_array"),
        ('{"order": "second, first, third"}', "llm_output_no_json_array"),
        ("[0, 2,", "llm_output_no_json_array"),
        ("[0, oops, 2]", "llm_output_malformed_json"),
        ('["a", "b", "c"]', "llm_output_not_an_index_list"),
        ("[[0], [1], [2]]", "llm_output_not_an_index_list"),
        ("[0, 1]", "llm_output_not_a_permutation"),
        ("[0, 1, 1]", "llm_output_not_a_permutation"),
    ],
)
def test_each_malformed_reply_reports_which_rule_it_broke(content: str, cause: str) -> None:
    result = _off(_Reply(content))
    assert result.mode == "off"
    assert result.order == [0, 1, 2], "a folded tier must keep the original order"
    assert result.causes == (cause,)
    assert cause in RERANK_CAUSES


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("gateway exploded"),
        ValueError("no JSON in the response body"),
        TimeoutError("read timed out"),
        ConnectionResetError("peer closed"),
    ],
)
def test_a_gateway_that_raised_is_not_reported_as_a_bad_reply(exc: BaseException) -> None:
    result = _off(_Raises(exc))
    assert result.causes == ("llm_provider_error",)
    reason = result.reason or ""
    assert type(exc).__name__ in reason, "the sentence must name the error that happened"
    for word in REPLY_WORDS:
        assert word not in reason.lower(), f"a raised gateway is not about the reply ({word})"


def test_the_reason_keeps_the_exception_message_out_of_the_note_field() -> None:
    """The type name is in the reason; the message may be payload, so it stays there."""
    result = _off(_Raises(RuntimeError("secret-ish body text")))
    assert "secret-ish body text" not in "".join(result.causes)
    assert result.causes == ("llm_provider_error",)


def test_an_expired_wait_is_separate_from_a_gateway_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_run_async only waits when a loop is already running — the node's shape."""
    monkeypatch.setattr("retrieval.rerank._LLM_WAIT_SECONDS", 0.2)

    async def _inside_a_running_loop() -> RerankResult:
        return _off(_Sleeps(1.5))

    result = asyncio.run(_inside_a_running_loop())
    assert result.causes == ("llm_wait_timeout",)
    assert "0.2s" in (result.reason or ""), "the wait the code actually used is the wait named"
    assert result.order == [0, 1, 2]


def test_no_key_and_unimportable_stack_are_two_different_absences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    without_key = rerank("q", CANDIDATES)
    assert without_key.causes == ("llm_not_configured",)

    monkeypatch.setenv("LLM_API_KEY", "sk-not-a-real-key-1234567890")
    monkeypatch.setitem(
        __import__("sys").modules, "providers.openai_compatible", None
    )  # importing None raises: the stack is gone, the config is not
    provider, absence = _llm_provider()
    assert provider is None
    assert absence == "llm_provider_stack_unavailable"
    result = rerank("q", CANDIDATES)
    assert result.causes == ("llm_provider_stack_unavailable",)
    assert "not configured" not in (result.reason or "")


def test_two_tiers_degrading_report_both_codes_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("retrieval.rerank._load_cross_encoder", lambda name: None)
    result = _off(_Raises(RuntimeError("x")), cross_encoder_model="bge-reranker-base")
    assert result.causes == ("cross_encoder_unavailable", "llm_provider_error")
    assert result.order == [0, 1, 2]
    sentences = (result.reason or "").split("; ")
    assert len(sentences) == len(result.causes)


def test_every_code_this_layer_emits_is_registered() -> None:
    """One sweep over every degradation reachable without a network."""
    emitted: set[str] = set()
    cases: list[tuple[Any, dict[str, Any]]] = [
        (_Reply("[0, 1]"), {}),
        (_Reply("nope"), {}),
        (_Reply("[1, 1]"), {}),
        (_Reply('["a"]'), {}),
        (_Reply('{"a": 1}'), {}),
        (_Raises(RuntimeError("x")), {}),
        (None, {"use_llm": False}),
    ]
    for provider, kwargs in cases:
        result = rerank("q", CANDIDATES, provider=provider, **kwargs)
        emitted.update(result.causes)
    assert emitted, "the sweep found no degradation at all, which means it tested nothing"
    assert emitted <= RERANK_CAUSES, f"unregistered codes: {sorted(emitted - RERANK_CAUSES)}"


def test_the_vocabulary_is_exactly_the_causes_this_number_registered() -> None:
    """A new code must be added here on purpose — that friction is the design."""
    registered = {
        "single_candidate",
        "not_configured",
        "cross_encoder_unavailable",
        "cross_encoder_failed",
        "llm_not_configured",
        "llm_provider_stack_unavailable",
        "llm_output_no_json_array",
        "llm_output_malformed_json",
        "llm_output_not_an_index_list",
        "llm_output_not_a_permutation",
        "llm_provider_error",
        "llm_wait_timeout",
        "bm25_only",
        "rerank_crashed",
        "empty_query",
    }
    assert registered == RERANK_CAUSES


def test_a_single_candidate_is_off_and_says_so() -> None:
    result = rerank("q", CANDIDATES[:1])
    assert result.mode == "off"
    assert result.causes == ("single_candidate",)


def test_a_ranking_that_arrived_carries_no_cause() -> None:
    result = _off(_Reply("[2, 0, 1]"))
    assert result.mode == "llm"
    assert result.causes == ()
    assert result.reason is None


# ── B. the annotation sites in the product cannot forget the code ───────────


def _rerank_result_construction_sites(repo: Path) -> list[tuple[str, int, bool]]:
    """Every ``RerankResult(mode="off", ...)`` the product builds, + does it name causes.

    Only the off sites are checked: a site that returns a ranking has nothing to
    account for.  The mode is read as a literal because every off site in this
    product writes it as one — a computed mode would land on the `assert sites`
    floor below, where the scan admits it is not seeing the code.
    """
    sites: list[tuple[str, int, bool]] = []
    for rel in ("retrieval/rerank.py", "retrieval/hybrid.py"):
        tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "RerankResult":
                continue
            keywords = {k.arg: k.value for k in node.keywords}
            mode = keywords.get("mode")
            if not isinstance(mode, ast.Constant) or mode.value != "off":
                continue
            sites.append((rel, node.lineno, "causes" in keywords))
    return sites


def test_every_off_verdict_the_product_builds_announces_its_causes() -> None:
    sites = _rerank_result_construction_sites(ROOT)
    assert len(sites) >= 4, f"the scan found {len(sites)} off-sites; it is not seeing the code"
    missing = [f"{rel}:{line}" for rel, line, has in sites if not has]
    assert not missing, f"mode=off built without causes at {missing}"


def _annotated_meta_dicts(repo: Path) -> list[tuple[str, int, bool]]:
    """Every dict literal that annotates ``rerank_mode``, with whether it also has codes."""
    out: list[tuple[str, int, bool]] = []
    for rel in ("retrieval/hybrid.py",):
        tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if "rerank_mode" in keys:
                out.append((rel, node.lineno, "rerank_causes" in keys))
    return out


def test_a_meta_dict_that_announces_a_rerank_mode_announces_its_causes() -> None:
    dicts = _annotated_meta_dicts(ROOT)
    assert len(dicts) >= 2, f"the scan found {len(dicts)}; it is not seeing the code"
    missing = [f"{rel}:{line}" for rel, line, has in dicts if not has]
    assert not missing, f"meta annotates rerank_mode without rerank_causes at {missing}"


# ── C. observability: the code travels, the sentence does not ──────────────


class _Store:
    """ES stand-in with the two channels hybrid_search uses."""

    def __init__(self, *, vector_hits: list[dict[str, Any]] | None = None) -> None:
        self._vector_hits = vector_hits if vector_hits is not None else list(CANDIDATES)

    def search_code(self, repo: str, query: str, size: int = 20) -> list[dict[str, Any]]:
        return [dict(h) for h in CANDIDATES]

    def vector_search(
        self, repo: str, vector: list[float], k: int = 20, commit_sha: str | None = None
    ) -> list[dict[str, Any]]:
        return [dict(h) for h in self._vector_hits]


class _Embedder:
    configured = True
    model = "test-embed-model"
    config_cause = ""

    def embed(self, texts: list[str]) -> EmbeddingOutcome:
        return EmbeddingOutcome([[0.1, 0.2] for _ in texts])


def test_hybrid_meta_carries_the_code_when_the_gateway_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "retrieval.rerank._llm_provider", lambda: (_Raises(RuntimeError("429 exhausted")), None)
    )
    outcome = hybrid_search(
        es=_Store(), query="email change", repo="r", k=3, embedder=_Embedder()
    )
    assert outcome.meta["rerank_mode"] == "off"
    assert outcome.meta["rerank_causes"] == "llm_provider_error"
    assert "RuntimeError" in (outcome.meta["rerank_reason"] or "")


def test_hybrid_meta_has_no_causes_when_the_rerank_ran(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("retrieval.rerank._llm_provider", lambda: (_Reply("[2, 0, 1]"), None))
    outcome = hybrid_search(
        es=_Store(), query="email change", repo="r", k=3, embedder=_Embedder()
    )
    assert outcome.meta["rerank_mode"] == "llm"
    assert outcome.meta["rerank_causes"] is None


def test_bm25_only_run_announces_that_rerank_was_never_asked_for() -> None:
    outcome = hybrid_search(
        es=_Store(vector_hits=[]), query="email change", repo="r", k=3, embedder=_Embedder()
    )
    assert outcome.meta["rerank_causes"] == "bm25_only"
    assert outcome.meta["rerank_mode"] == "off"


def test_an_empty_query_announces_its_cause_too() -> None:
    outcome = hybrid_search(
        es=_Store(), query="   ", repo="r", k=3, embedder=_Embedder()
    )
    assert outcome.meta["rerank_causes"] == "empty_query"


class _NodeHarness:
    """Run the retrieval node with the real hybrid_search and the real rerank layer.

    Only the process boundaries are stubbed: the store, the graph, the embedder
    and ``git rev-parse``.  The degradation under test must be produced by the
    product, not pasted into a fake meta, or this file would pin nothing about
    what an operator sees.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path

    def run(self, *, hits: list[dict[str, Any]]) -> str:
        import agent.nodes.retrieve_repository_context as node_module
        from agent.nodes.retrieve_repository_context import retrieve_repository_context_node

        workspace = self.tmp_path / "ws" / "src" / "main" / "java"
        workspace.mkdir(parents=True)
        (workspace / "Svc.java").write_text("class Svc {}", encoding="utf-8")

        store = SimpleNamespace(
            is_ready=lambda: True,
            index_with_embeddings=lambda repo, sha, files, embedder, **kw: {
                "indexed": len(files),
                "embedded": len(files),
            },
            search_code=lambda repo, query, size=20: [dict(h) for h in hits],
            vector_search=lambda repo, vector, k=20, commit_sha=None: [dict(h) for h in hits],
        )
        self.monkeypatch.setattr(
            "storage.elasticsearch.ElasticsearchStore", lambda: store
        )
        self.monkeypatch.setattr(
            "agent.repo_graph.RepoGraph",
            lambda files: SimpleNamespace(expand_hits=lambda hs, hops=1: hs),
        )
        self.monkeypatch.setattr(
            "retrieval.embeddings.EmbeddingClient",
            SimpleNamespace(from_env=lambda: _Embedder()),
        )
        self.monkeypatch.setattr(
            node_module,
            "subprocess",
            SimpleNamespace(
                run=lambda *a, **k: SimpleNamespace(
                    returncode=0, stdout="deadbeef\n", stderr=""
                )
            ),
        )
        state: Any = {
            "head_workspace": str(self.tmp_path / "ws"),
            "repo_path": "demo-repo",
            "requirement_text": "email change",
            "use_llm": True,
            "job_id": "j-523",
        }
        return retrieve_repository_context_node(state)["retrieval_note"]


def test_the_note_carries_the_code_and_not_the_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The payload path this number closes: reason text may quote the request.

    ``rerank()`` builds the LLM prompt out of candidate ``content``; if a tier
    raises, its reason quotes the exception.  ``retrieval_note`` is persisted in
    the run summary and put on notifications, so a marker planted in a candidate
    must be able to reach ``meta["rerank_reason"]`` and must not reach the note.
    """
    marker = "IGNORE-ALL-RULES-523"
    hits = [
        {"path": "a/Svc.java", "symbol": "send", "content": "// " + marker},
        {"path": "b/Mail.java", "symbol": "mail", "content": "void mail() {}"},
        {"path": "c/Repo.java", "symbol": "save", "content": "void save() {}"},
    ]

    class _PredictRaises:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            raise RuntimeError("encoder died over " + marker)

    monkeypatch.setenv("RERANK_MODEL", "bge-reranker-base")
    monkeypatch.setattr("retrieval.rerank._load_cross_encoder", lambda name: _PredictRaises())

    note = _NodeHarness(monkeypatch, tmp_path).run(hits=hits)
    assert "rerank_causes=cross_encoder_failed" in note, note
    assert marker not in note, "repository payload reached the persisted note"


def test_the_note_says_nothing_when_nothing_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    hits = [
        {"path": "a/Svc.java", "symbol": "send", "content": "void send() {}"},
        {"path": "b/Mail.java", "symbol": "mail", "content": "void mail() {}"},
    ]
    monkeypatch.delenv("RERANK_MODEL", raising=False)
    monkeypatch.setattr("retrieval.rerank._llm_provider", lambda: (_Reply("[1, 0]"), None))
    note = _NodeHarness(monkeypatch, tmp_path).run(hits=hits)
    assert "rerank_causes=" not in note
    assert "rerank=llm" in note
