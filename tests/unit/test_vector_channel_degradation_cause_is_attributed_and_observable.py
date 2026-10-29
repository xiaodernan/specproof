"""#524 — every way the vector channel degrades is named, and only the name travels.

WHY THIS EXISTS.  ``retrieval/embeddings.py`` promised an honesty contract
("vectors are real gateway output or nothing") and ``retrieval/hybrid.py``
promised 卷IV 4.3's "embedding_error=原因".  Both promises were kept, in a
sense — and both were unreadable and one of them was unsafe.  Measured on the
tree before this gate was written:

  * **one sentence, four facts.** ``"embedding endpoint unreachable: " +
    str(exc)[:160]`` was the sentence for a refused connection, a DNS failure,
    a proxy break, a TLS break, a protocol break and every timeout.  Seven
    httpx shapes produced the same claim about the endpoint.  And when the
    exception's message was empty — ``httpx.WriteTimeout("")`` is the shape
    that made this visible — the whole report was 32 characters ending in a
    colon: no type, no fact, nothing.
  * **the sentence was on the wire.** ``embedding_error`` was forwarded into
    ``retrieval_note``, which is persisted in the run summary, *queried* by
    ``storage/mysql.py`` with ``JSON_EXTRACT(summary, '$.retrieval_note')`` and
    put on notifications.  The vector channel's own sentences quote the gateway
    (`/var/run/embed.sock`, ``C:\\Users\\…\\token.json``, the first characters
    of a reply body), and one of them quotes Elasticsearch rejecting a chunk of
    the repository's source — the 120-char cap did not stop it, because an
    indexed chunk can be one line of Java.  #523 closed that door for rerank;
    this file closes it for the vector channel.
  * **a malformed reply could cost the whole retrieval.** ``hybrid_search``
    asked for the query vector *after* its BM25 search had already returned
    hits, and six gateway reply shapes (a JSON array / string / number / null
    instead of an object; a ``data`` item that is not an object) reached
    ``payload.get`` / ``item.get`` and raised ``AttributeError`` straight out of
    ``embed()``.  ``AttributeError`` is not an ``Exception`` the vector channel
    catches, so it escaped ``hybrid_search`` and landed in the node's catch-all:
    ``repo_context`` empty, outcome ``retrieval_failed``.  "Degradations are
    annotated, never raised" was the contract; a search that worked was
    discarded by an optional add-on.
  * **the counts were unreadable without the reason.** ``index_with_embeddings``
    reports ``indexed`` / ``embedded`` / ``vectors_skipped``; with every vector
    arriving at the wrong width the note read ``indexed=42 embedded=0 ...
    embedding=<model>`` — "the model was used" next to "no vector was stored",
    with the why sitting in ``embedding_notes``, a key with zero product
    readers.

WHAT THIS GATE PINS.  Three layers, because the defect has three shapes:

  A  attribution — each way the endpoint or its reply fails has its own code in
     the closed set ``EMBEDDING_CAUSES`` and its own sentence for the log.  A
     new failure has to be registered to be reportable at all.
  B  structure — the (code, sentence) pair is bound where the failure is
     constructed (``EmbeddingOutcome``), and the annotation sites cannot forget
     it: an AST census over the product, not a prose rule.
  C  observability — codes reach ``retrieval_note``; sentences do not; and a
     repository marker planted in the payload the error message quotes must be
     provably unable to arrive.  ``tests/security/test_retrieval_injection.py``
     already forbids payload in this same note, so C is stated the way that file
     states it: payload in, marker out.

The never-raise half is pinned as behaviour, not as a comment: a reply shape
that this reader cannot use degrades with a named code *and keeps the hits*
(``response_payload_not_an_object`` is worth more than an empty context).

One leg here was written *after* the battery ran.  Arm B16 appended
``return EmbeddingOutcome(None)`` to the client and the gate stayed green: the
census walked ``_failed(...)`` calls, so bypassing the helper bypassed the check —
the same anonymous failure this file exists to prevent, wearing a different door.
Leg B's ``test_a_failure_built_without_the_helper_still_names_a_registered_code``
is the answer, and the arm is now part of the battery's expected reds.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from retrieval.embeddings import EMBEDDING_CAUSES, EmbeddingClient, EmbeddingOutcome
from retrieval.hybrid import hybrid_search
from storage.elasticsearch import ElasticsearchConfig, ElasticsearchStore
from tests.unit.test_es_projection_cleanup import FakeESProjection

ROOT = Path(__file__).resolve().parents[2]

CANDIDATES = [
    {"path": "a/Svc.java", "symbol": "send", "content": "void send() {}"},
    {"path": "b/Mail.java", "symbol": "mail", "content": "void mail() {}"},
    {"path": "c/Repo.java", "symbol": "save", "content": "void save() {}"},
]

#: Codes that describe this client's own failure to produce vectors.  The rest
#: of ``EMBEDDING_CAUSES`` belongs to the callers (why they never asked, what
#: the search backend did, what the store saw about vector width), so a sweep
#: over ``embed()`` alone can never reach them — and must not pretend to.
CLIENT_SIDE_CODES = EMBEDDING_CAUSES - {
    "no_embedder",
    "not_attempted",
    "vector_store_failed",
    "vectors_dims_mismatched",
    "embed_call_crashed",
    "cause_missing",
}


# ── machinery ─────────────────────────────────────────────────────────────


def _reply(body: bytes) -> httpx.MockTransport:
    """A gateway that answers every request with exactly these bytes.

    ``content=`` and not ``json=``: ``httpx.Response(json=None)`` is the
    *absence* of a body, so a probe that means "the gateway answered null" has
    to send ``b"null"``.  Measured while writing this gate, and the difference
    is the whole point of pinning shapes as bytes.
    """
    return httpx.MockTransport(lambda request: httpx.Response(200, content=body))


def _response(response: httpx.Response) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: response)


def _raises(exc: BaseException) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def _client(transport: httpx.MockTransport, **kwargs: Any) -> EmbeddingClient:
    """A configured client with no retry budget: one attempt, one verdict."""
    return EmbeddingClient(
        base_url="http://emb",
        api_key="k",
        model="test-embed-model",
        max_retries=0,
        transport=transport,
        **kwargs,
    )


def _varying_dims(request: httpx.Request) -> httpx.Response:
    """A gateway that embeds the same model at two different widths."""
    batch = json.loads(request.content)["input"]
    dims = 3 if len(batch) == 2 else 4
    return httpx.Response(
        200,
        json={
            "data": [
                {"index": i, "embedding": [0.1] * dims} for i in range(len(batch))
            ]
        },
    )


# ── A. attribution: one code per way of failing ────────────────────────────


@pytest.mark.parametrize(
    ("body", "texts", "cause"),
    [
        (b"[1, 2, 3]", ["a"], "response_payload_not_an_object"),
        (b'"hello"', ["a"], "response_payload_not_an_object"),
        (b"7", ["a"], "response_payload_not_an_object"),
        (b"null", ["a"], "response_payload_not_an_object"),
        (b"<html>502</html>", ["a"], "response_not_json"),
        (b"", ["a"], "response_not_json"),
        (b"{}", ["a"], "response_data_array_mismatched"),
        (b'{"data": []}', ["a"], "response_data_array_mismatched"),
        (b'{"data": [{"index": 0, "embedding": [0.1]}]}', ["a", "b"],
         "response_data_array_mismatched"),
        (b'{"data": [1, 2]}', ["a", "b"], "response_data_item_not_an_object"),
        (b'{"data": [[0.1], [0.2]]}', ["a", "b"], "response_data_item_not_an_object"),
        (b'{"data": [{"index": 0, "embedding": []}]}', ["a"], "vector_empty"),
        (b'{"data": [{"index": 0, "embedding": ["a"]}]}', ["a"], "response_malformed"),
        (b'{"data": [{"index": 0, "embedding": 1.5}]}', ["a"], "response_malformed"),
        (b'{"data": [{"index": 0}]}', ["a"], "response_malformed"),
    ],
)
def test_each_reply_shape_reports_which_part_of_the_contract_it_broke(
    body: bytes, texts: list[str], cause: str
) -> None:
    outcome = _client(_reply(body)).embed(texts)
    assert outcome.vectors is None
    assert outcome.cause == cause
    assert cause in EMBEDDING_CAUSES
    assert outcome.sentence, "a code without a sentence leaves the log line empty"


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503])
def test_a_rejected_request_names_the_status_not_a_generic_failure(
    status: int,
) -> None:
    outcome = _client(_response(httpx.Response(status, json={"error": "no"}))).embed(["x"])
    assert outcome.cause == "endpoint_http_error"
    assert str(status) in outcome.sentence


@pytest.mark.parametrize(
    ("exc", "cause"),
    [
        (httpx.ConnectError("[Errno 111] refused /var/run/embed.sock"),
         "endpoint_connect_failed"),
        (httpx.ConnectTimeout("timed out connecting"), "endpoint_timeout"),
        (httpx.ReadTimeout("read timed out"), "endpoint_timeout"),
        (httpx.WriteTimeout("body not flushed"), "endpoint_timeout"),
        (httpx.PoolTimeout("pool exhausted"), "endpoint_timeout"),
        (httpx.NetworkError("[WinError 10054] connection reset"),
         "endpoint_transport_failed"),
        (httpx.RemoteProtocolError("Server disconnected without sending a response"),
         "endpoint_transport_failed"),
        (httpx.ProxyError("proxy refused the connection"), "endpoint_transport_failed"),
        (OSError("unhandled socket failure"), "endpoint_transport_failed"),
    ],
)
def test_each_transport_shape_names_which_kind_of_failure_it_was(
    exc: BaseException, cause: str
) -> None:
    outcome = _client(_raises(exc)).embed(["x"])
    assert outcome.vectors is None
    assert outcome.cause == cause
    assert type(exc).__name__ in outcome.sentence


def test_the_seven_transport_shapes_no_longer_share_one_claim() -> None:
    """The fold this number removes: six-plus facts, one sentence.

    Before, every row above produced ``"embedding endpoint unreachable: …"`` —
    so "the endpoint is down", "the endpoint is slow", "a proxy broke the
    connection" and "our own socket failed" were the same operator-visible
    claim.  The codes must be three, and the folded word must be gone.
    """
    shapes = [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.PoolTimeout("no connection available"),
        httpx.NetworkError("reset"),
        httpx.RemoteProtocolError("disconnected"),
        httpx.ProxyError("proxy"),
        OSError("socket"),
    ]
    outcomes = [_client(_raises(exc)).embed(["x"]) for exc in shapes]
    assert {outcome.cause for outcome in outcomes} == {
        "endpoint_connect_failed",
        "endpoint_timeout",
        "endpoint_transport_failed",
    }
    for outcome in outcomes:
        assert "unreachable" not in outcome.sentence
    source = (ROOT / "retrieval" / "embeddings.py").read_text(encoding="utf-8")
    assert '"embedding endpoint unreachable' not in source, "the folded sentence came back"


def test_connect_timeout_is_a_timeout_on_the_httpx_this_project_pins() -> None:
    """The classification order is a dependency assumption, so it is measured.

    ``_classify_transport`` checks ``ConnectError`` before ``TimeoutException``
    on the theory that a handshake that ran out of time is a reachability
    failure.  On the pinned httpx that theory does not decide anything, because
    the two families are disjoint there — this test says which one wins and
    reddens if a release changes it under us.
    """
    assert issubclass(httpx.ConnectTimeout, httpx.TimeoutException)
    assert not issubclass(httpx.ConnectTimeout, httpx.ConnectError)
    outcome = _client(_raises(httpx.ConnectTimeout("timed out connecting"))).embed(["x"])
    assert outcome.cause == "endpoint_timeout"
    assert "ConnectTimeout" in outcome.sentence


def test_an_exception_with_no_message_still_names_its_type() -> None:
    """Measured: ``httpx.WriteTimeout("")`` used to report 32 chars ending in ':'.

    Empty-message transport errors are real (httpx builds them internally on
    some paths), and the old sentence interpolated only the message, so the
    report carried neither the fact nor its type.
    """
    outcome = _client(_raises(httpx.WriteTimeout(""))).embed(["x"])
    assert outcome.cause == "endpoint_timeout"
    assert "WriteTimeout" in outcome.sentence
    assert not outcome.sentence.rstrip().endswith(":"), outcome.sentence


def test_a_retryable_status_is_named_after_the_retry_budget_ran_out() -> None:
    """The code describes the verdict, not the first attempt."""
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(429, headers={"retry-after": "0"})

    client = EmbeddingClient(
        base_url="http://emb",
        api_key="k",
        model="test-embed-model",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )
    outcome = client.embed(["x"])
    assert attempts["n"] == 2
    assert outcome.cause == "endpoint_http_error"
    assert "429" in outcome.sentence


def test_vectors_that_arrive_are_not_a_degradation() -> None:
    outcome = _client(
        _reply(b'{"data": [{"index": 0, "embedding": [0.5, 0.25]}]}')
    ).embed(["x"])
    assert outcome.vectors == [[0.5, 0.25]]
    assert outcome.cause == ""
    assert outcome.sentence == ""


def test_inconsistent_dims_across_batches_is_its_own_fact() -> None:
    client = EmbeddingClient(
        base_url="http://emb",
        api_key="k",
        model="m",
        max_retries=0,
        batch_size=2,
        transport=httpx.MockTransport(_varying_dims),
    )
    outcome = client.embed(["a", "b", "c"])
    assert outcome.vectors is None
    assert outcome.cause == "vector_dims_inconsistent"


@pytest.mark.parametrize(
    ("kwargs", "cause"),
    [
        (
            {"base_url": "", "api_key": "k", "model": "m"},
            "base_url_not_set",
        ),
        ({"base_url": "http://emb", "api_key": "", "model": "m"},
         "api_key_not_set_or_placeholder"),
        ({"base_url": "http://emb", "api_key": "replace_me", "model": "m"},
         "api_key_not_set_or_placeholder"),
        ({"base_url": "http://emb", "api_key": "k", "model": ""},
         "model_not_set"),
    ],
)
def test_each_missing_setting_names_itself_in_both_channels(
    kwargs: dict[str, str], cause: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The config verdict is a code too, and ``embed()`` repeats it faithfully.

    ``configured`` is the switch the node branches on, so a run that never
    reaches the endpoint still has to say which setting stopped it.
    """
    for name in ("LLM_EMBEDDING_BASE_URL", "LLM_EMBEDDING_API_KEY", "LLM_EMBEDDING_MODEL",
                 "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    client = EmbeddingClient(max_retries=0, **kwargs)
    assert client.configured is False
    assert client.config_cause == cause
    outcome = client.embed(["x"])
    assert outcome.cause == cause, "embed() and config_cause disagree"
    assert outcome.vectors is None


def test_the_cause_and_the_sentence_are_bound_where_the_failure_is_built() -> None:
    """The declared outcome shape, not a tuple two callers read differently.

    Measured before this number: the real client used ``reason=""`` for success
    while two test doubles used ``None``, and both stayed green because every
    caller only tested the vectors.  ``cause`` is empty exactly when there are
    vectors — no third state for a duck-typed embedder to invent.
    """
    ok = EmbeddingOutcome([[0.1]])
    assert ok.vectors is not None and ok.cause == "" and ok.sentence == ""
    failed = EmbeddingOutcome(None, "vector_empty", "embedding endpoint returned an empty vector")
    assert failed.vectors is None and failed.cause in EMBEDDING_CAUSES


def test_every_code_this_client_can_emit_is_registered_and_reachable() -> None:
    """One sweep over every failure reachable without a network.

    Two directions are pinned at once: nothing unregistered escapes, and the
    vocabulary is not padded with codes no path produces.  Only the client's
    own half — the caller-side codes are named by ``hybrid.py`` and
    ``storage/elasticsearch.py`` and have their own tests below.
    """
    emitted: set[str] = set()
    bodies = [
        b"[1]", b"null", b"<html>", b"", b"{}", b'{"data": []}', b'{"data": [1]}',
        b'{"data": [{"index": 0, "embedding": []}]}',
        b'{"data": [{"index": 0}]}',
    ]
    for body in bodies:
        emitted.add(_client(_reply(body)).embed(["a"]).cause)
    for status in (401, 429):
        emitted.add(_client(_response(httpx.Response(status))).embed(["a"]).cause)
    for exc in (
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.ProxyError("proxy"),
    ):
        emitted.add(_client(_raises(exc)).embed(["a"]).cause)
    for kwargs in (
        {"base_url": ""},
        {"api_key": ""},
        {"model": ""},
    ):
        settings: dict[str, str] = {
            "base_url": "http://emb",
            "api_key": "k",
            "model": "m",
        }
        settings.update(kwargs)
        emitted.add(EmbeddingClient(max_retries=0, **settings).embed(["a"]).cause)
    # The one failure that only exists across a batch boundary.
    emitted.add(
        EmbeddingClient(
            base_url="http://emb",
            api_key="k",
            model="m",
            max_retries=0,
            batch_size=2,
            transport=httpx.MockTransport(_varying_dims),
        )
        .embed(["a", "b", "c"])
        .cause
    )
    emitted.discard("")
    assert emitted, "the sweep found no failure at all, which means it tested nothing"
    assert emitted <= EMBEDDING_CAUSES, f"unregistered codes: {sorted(emitted - EMBEDDING_CAUSES)}"
    assert emitted == CLIENT_SIDE_CODES, (
        f"codes with no reachable exit: {sorted(CLIENT_SIDE_CODES - emitted)}; "
        f"extras: {sorted(emitted - CLIENT_SIDE_CODES)}"
    )


def test_the_vocabulary_is_exactly_the_causes_this_number_registered() -> None:
    """A new code has to be added here on purpose — that friction is the design."""
    registered = {
        "base_url_not_set",
        "api_key_not_set_or_placeholder",
        "model_not_set",
        "endpoint_http_error",
        "endpoint_timeout",
        "endpoint_connect_failed",
        "endpoint_transport_failed",
        "response_not_json",
        "response_payload_not_an_object",
        "response_data_array_mismatched",
        "response_data_item_not_an_object",
        "response_malformed",
        "vector_empty",
        "vector_dims_inconsistent",
        "embed_call_crashed",
        "no_embedder",
        "not_attempted",
        "vector_store_failed",
        "vectors_dims_mismatched",
        "cause_missing",
    }
    assert registered == EMBEDDING_CAUSES


# ── B. the annotation sites in the product cannot forget the code ───────────


def _failed_call_sites(repo: Path) -> list[tuple[int, str | None, str | None]]:
    """Every ``_failed(...)`` the client builds: (line, literal code, code name).

    One site hands in a variable rather than a literal — the transport
    classifier's answer — and the test below pins that classifier separately,
    so a site may not quietly become a second one.
    """
    tree = ast.parse((repo / "retrieval" / "embeddings.py").read_text(encoding="utf-8"))
    sites: list[tuple[int, str | None, str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "_failed":
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            sites.append((node.lineno, first.value, None))
        elif isinstance(first, ast.Name):
            sites.append((node.lineno, None, first.id))
        else:
            sites.append((node.lineno, None, "<not a name>"))
    return sites


def test_a_caller_that_builds_a_failed_outcome_names_the_code_literally() -> None:
    """``hybrid.py`` builds one failure itself — the guard for a raising embedder.

    Same rule as the client's: an outcome whose vectors are None must carry a
    registered code at its construction site, wherever in the product it is.
    """
    tree = ast.parse((ROOT / "retrieval" / "hybrid.py").read_text(encoding="utf-8"))
    sites: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "EmbeddingOutcome":
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.Constant) and first.value is None:
            second = node.args[1] if len(node.args) > 1 else None
            code = (
                second.value
                if isinstance(second, ast.Constant) and isinstance(second.value, str)
                else None
            )
            sites.append((node.lineno, code))
    assert sites, "hybrid.py no longer builds a failed outcome; this census needs rewriting"
    for line, code in sites:
        assert code in EMBEDDING_CAUSES, f"retrieval/hybrid.py:{line} builds {code!r}"


def _tuple_return_codes(repo: Path, rel: str, func_name: str) -> list[str]:
    """The literal first elements of the ``(code, sentence)`` tuples a function returns.

    Walked rather than read off the module body: ``_resolve_config_failure`` is a
    method, and a census that only sees top-level functions reports "gone" for code
    that is sitting right there.
    """
    tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            codes: list[str] = []
            for ret in ast.walk(node):
                if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Tuple):
                    head = ret.value.elts[0]
                    if isinstance(head, ast.Constant) and isinstance(head.value, str):
                        codes.append(head.value)
            return codes
    raise AssertionError(f"{rel} no longer defines {func_name}; the census needs rewriting")


def _classifier_return_codes(repo: Path) -> list[str]:
    """The literal codes ``_classify_transport`` can hand to ``_failed``."""
    return _tuple_return_codes(repo, "retrieval/embeddings.py", "_classify_transport")


def test_every_failure_the_client_builds_carries_a_registered_literal_code() -> None:
    sites = _failed_call_sites(ROOT)
    assert len(sites) >= 9, (
        f"the scan found {len(sites)} _failed sites; it is not seeing the code"
    )
    literal = [(line, code) for line, code, name in sites if code is not None]
    for line, code in literal:
        assert code in EMBEDDING_CAUSES, (
            f"retrieval/embeddings.py:{line} emits unregistered {code!r}"
        )
    by_variable = [(line, name) for line, code, name in sites if code is None]
    assert [name for _, name in by_variable] == ["cause"] * len(by_variable), (
        f"failures built from something other than the classifier: {by_variable}"
    )
    classifier_codes = _classifier_return_codes(ROOT)
    assert classifier_codes, "the classifier returns no literal code any more"
    for code in classifier_codes:
        assert code in EMBEDDING_CAUSES, f"_classify_transport emits unregistered {code!r}"


def test_the_untyped_tuple_exit_that_allowed_an_anonymous_failure_is_gone() -> None:
    """``return (None, "some prose")`` is the shape that had no place for a code."""
    source = (ROOT / "retrieval" / "embeddings.py").read_text(encoding="utf-8")
    assert not re.search(r"return \(None,", source), (
        "a tuple-shaped failure came back; it cannot carry a registered code"
    )


def _none_shaped_outcome_sites(repo: Path) -> list[tuple[int, str | None, str]]:
    """Every ``EmbeddingOutcome(None, ...)`` the client builds itself.

    Arm B16 measured the hole this leg closes: the census above walks ``_failed(...)``
    calls, so a failure built by naming the dataclass directly —
    ``return EmbeddingOutcome(None)`` — carried no code and stayed green.  The helper
    exists to make an anonymous build visible even where ``_failed`` is bypassed.
    """
    tree = ast.parse((repo / "retrieval" / "embeddings.py").read_text(encoding="utf-8"))
    sites: list[tuple[int, str | None, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", None) != "EmbeddingOutcome":
            continue
        first = node.args[0] if node.args else None
        if not (isinstance(first, ast.Constant) and first.value is None):
            continue
        second = node.args[1] if len(node.args) > 1 else None
        if isinstance(second, ast.Constant) and isinstance(second.value, str):
            sites.append((node.lineno, second.value, "literal"))
        elif isinstance(second, ast.Attribute) and second.attr == "_config_cause":
            sites.append((node.lineno, None, "config_cause"))
        elif isinstance(second, ast.Name) and second.id == "cause":
            # ``_failed`` itself: the one place a code arrives as a parameter, and its
            # callers are censused by ``_failed_call_sites`` above.
            sites.append((node.lineno, None, "via_failed"))
        else:
            sites.append((node.lineno, None, "anonymous"))
    return sites


def test_a_failure_built_without_the_helper_still_names_a_registered_code() -> None:
    """``_failed`` is a convenience, not the only door — so it is not the only census.

    The two sites that hand in an expression rather than a literal are ``_failed``
    itself, whose arguments are pinned by the census above, and the unconfigured client,
    whose code comes out of ``_resolve_config_failure`` — that function's own literals
    are censused here, the same way the transport classifier's already are.
    """
    sites = _none_shaped_outcome_sites(ROOT)
    assert len(sites) >= 2, (
        f"the scan found {len(sites)} failed outcomes; it is not seeing the code"
    )
    for line, code, form in sites:
        if form == "literal":
            assert code in EMBEDDING_CAUSES, (
                f"retrieval/embeddings.py:{line} emits unregistered {code!r}"
            )
        assert form != "anonymous", (
            f"retrieval/embeddings.py:{line} builds a failed outcome with no code at all"
        )
    assert [form for _, _, form in sites].count("via_failed") <= 1, (
        "a second site takes its code from _failed's parameter — the census above "
        "walks _failed's own call sites and would have to grow"
    )
    config_codes = [
        code
        for code in _tuple_return_codes(
            ROOT, "retrieval/embeddings.py", "_resolve_config_failure"
        )
        if code
    ]
    assert config_codes, "_resolve_config_failure returns no literal code any more"
    for code in config_codes:
        assert code in EMBEDDING_CAUSES, f"_resolve_config_failure emits {code!r}"


def _annotated_dicts(repo: Path, rel: str, named: str, companion: str) -> list[tuple[int, bool]]:
    """Every dict literal that writes ``named``, with whether it also writes ``companion``."""
    tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
    out: list[tuple[int, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            k.value
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if named in keys:
            out.append((node.lineno, companion in keys))
    return out


def test_a_meta_dict_that_announces_an_embedding_error_announces_its_causes() -> None:
    dicts = _annotated_dicts(ROOT, "retrieval/hybrid.py", "embedding_error", "embedding_causes")
    assert len(dicts) >= 2, f"the scan found {len(dicts)}; it is not seeing the code"
    missing = [f"retrieval/hybrid.py:{line}" for line, has in dicts if not has]
    assert not missing, f"meta writes embedding_error without embedding_causes at {missing}"


def test_a_report_that_counts_skipped_vectors_says_why_they_were_skipped() -> None:
    dicts = _annotated_dicts(
        ROOT, "storage/elasticsearch.py", "vectors_skipped", "embedding_causes"
    )
    assert dicts, "the scan found no report dict at all; it is not seeing the code"
    missing = [f"storage/elasticsearch.py:{line}" for line, has in dicts if not has]
    assert not missing, f"report counts skipped vectors without naming the cause at {missing}"


# ── C. the callers: the code reaches meta, the crash does not reach the run ──


class _Store:
    """ES stand-in with the two channels ``hybrid_search`` uses."""

    def __init__(
        self,
        *,
        bm25: list[dict[str, Any]] | None = None,
        vectors: list[dict[str, Any]] | None = None,
        vector_error: BaseException | None = None,
    ) -> None:
        self._bm25 = CANDIDATES if bm25 is None else bm25
        self._vectors = CANDIDATES if vectors is None else vectors
        self._vector_error = vector_error

    def search_code(self, repo: str, query: str, size: int = 20) -> list[dict[str, Any]]:
        return [dict(h) for h in self._bm25]

    def vector_search(
        self, repo: str, query_vector: list[float], k: int = 10, commit_sha: str | None = None
    ) -> list[dict[str, Any]]:
        if self._vector_error is not None:
            raise self._vector_error
        return [dict(h) for h in self._vectors]


class _Embedder:
    """Duck-typed embedder: the shape hybrid.py actually receives."""

    configured = True
    model = "test-embed-model"
    config_cause = ""

    def __init__(self, outcome: EmbeddingOutcome | None = None, *, raises: bool = False) -> None:
        self._outcome = outcome
        self._raises = raises

    def embed(self, texts: list[str]) -> EmbeddingOutcome:
        if self._raises:
            raise AttributeError("'list' object has no attribute 'get'")
        if self._outcome is not None:
            return self._outcome
        return EmbeddingOutcome([[0.1, 0.2] for _ in texts])


def _hybrid(store: _Store, embedder: Any) -> dict[str, Any]:
    return hybrid_search(es=store, query="email change", repo="r", k=3, embedder=embedder).meta


def test_an_endpoint_failure_puts_its_code_and_its_sentence_in_meta() -> None:
    meta = _hybrid(
        _Store(vectors=[]),
        _Embedder(
            EmbeddingOutcome(None, "endpoint_http_error", "embedding endpoint HTTP 503")
        ),
    )
    assert meta["embedding_causes"] == "endpoint_http_error"
    assert meta["embedding_error"] == "embedding endpoint HTTP 503"
    assert meta["mode"] == "bm25", "the keyword channel still answers"


def test_a_store_that_rejects_the_knn_request_is_attributed_to_the_store() -> None:
    """The payload-safety half, measured at the source.

    Elasticsearch quotes the document it rejected, and that document is a chunk
    of the repository's own source.  The sentence is where it belongs (meta,
    then the log); the code is what may travel.
    """
    marker = "REPO-BODY-MARKER-524"
    meta = _hybrid(
        _Store(vectors=[], vector_error=RuntimeError("index [code] rejected source " + marker)),
        _Embedder(),
    )
    assert meta["embedding_causes"] == "vector_store_failed"
    assert marker in str(meta["embedding_error"]), "the sentence must keep what ES said, in the log"
    assert meta["mode"] == "bm25"


def test_an_escaping_embedder_does_not_cost_the_hits_that_already_arrived() -> None:
    """The regression #524 was written for: a crash in the optional add-on.

    Before the isinstance guards and this guard, six reply shapes raised
    ``AttributeError`` past ``hybrid_search`` into the node's catch-all, and a
    retrieval holding three usable BM25 hits ended as an empty context.
    """
    store = _Store(vectors=[])
    outcome = hybrid_search(
        es=store, query="email change", repo="r", k=3, embedder=_Embedder(raises=True)
    )
    assert outcome.meta["embedding_causes"] == "embed_call_crashed"
    assert outcome.meta["mode"] == "bm25"
    assert len(outcome.results) == 3, "the keyword hits must survive the vector channel"


@pytest.mark.parametrize(
    ("body", "cause"),
    [
        (b"[1, 2, 3]", "response_payload_not_an_object"),
        (b'{"data": [1]}', "response_data_item_not_an_object"),
    ],
)
def test_a_malformed_reply_degrades_by_name_and_keeps_the_results(
    body: bytes, cause: str
) -> None:
    outcome = hybrid_search(
        es=_Store(vectors=[]),
        query="email change",
        repo="r",
        k=3,
        embedder=_client(_reply(body)),
    )
    assert outcome.meta["embedding_causes"] == cause
    assert len(outcome.results) == 3


def test_no_embedder_is_a_fact_about_the_run_not_silence() -> None:
    meta = _hybrid(_Store(vectors=[]), None)
    assert meta["embedding_causes"] == "no_embedder"
    assert meta["embedding_used"] is None


def test_an_unconfigured_embedder_reports_which_setting_is_missing() -> None:
    client = EmbeddingClient(
        base_url="http://emb", api_key="k", model="", max_retries=0
    )
    meta = _hybrid(_Store(vectors=[]), client)
    assert meta["embedding_causes"] == "model_not_set"


def test_a_duck_typed_embedder_that_names_nothing_gets_a_code_anyway() -> None:
    """An unnamed failure must not read as "nothing happened"."""
    meta = _hybrid(_Store(vectors=[]), _Embedder(EmbeddingOutcome(None, "", "no reason given")))
    assert meta["embedding_causes"] == "cause_missing"
    assert meta["embedding_error"] == "no reason given"


def test_a_run_that_never_asked_for_a_vector_says_so() -> None:
    outcome = hybrid_search(es=_Store(), query="   ", repo="r", k=3, embedder=_Embedder())
    assert outcome.meta["embedding_causes"] == "not_attempted"
    assert outcome.meta["embedding_error"] is None


def test_a_hybrid_run_that_worked_carries_no_cause() -> None:
    meta = _hybrid(_Store(), _Embedder())
    assert meta["mode"] == "hybrid"
    assert meta["embedding_causes"] is None


# ── D. the index projection: the count and the reason arrive together ───────


class _Projection(FakeESProjection):
    """Fake ES server: answers a match query with the projection, kNN only with vectors.

    ``created`` starts False and ``ensure_indices`` flips it, exactly like the
    cleanup suite's fake, so the real ``index_with_embeddings`` runs end to end.
    ``knn_error`` is how the server rejects the vector request — which is what
    a real Elasticsearch does when it chokes on a document, quoting it while
    doing so.  ``bulk_error`` is the server refusing the write.
    """

    def __init__(
        self,
        *,
        knn_error: BaseException | None = None,
        bulk_error: BaseException | None = None,
    ) -> None:
        super().__init__()
        self.knn_error = knn_error
        self.bulk_error = bulk_error

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def bulk(self, operations: list[Any], refresh: bool = False) -> dict[str, Any]:
        if self.bulk_error is not None:
            raise self.bulk_error
        return super().bulk(operations, refresh=refresh)

    def search(
        self, index: str, body: dict[str, Any], ignore_unavailable: bool = False
    ) -> dict[str, Any]:
        if "knn" in body:
            if self.knn_error is not None:
                raise self.knn_error
            stored = [d for d in self.docs if d["_source"].get("embedding")]
            return {
                "hits": {
                    "hits": [
                        {"_id": d["_id"], "_source": d["_source"], "_score": 1.0}
                        for d in stored[: body.get("size", 10)]
                    ]
                }
            }
        return {
            "hits": {
                "hits": [
                    {"_id": d["_id"], "_source": d["_source"]}
                    for d in self.docs[: body.get("size", 10)]
                ]
            }
        }


def _store(
    *,
    vector_dims: int = 4,
    knn_error: BaseException | None = None,
    bulk_error: BaseException | None = None,
) -> tuple[ElasticsearchStore, _Projection]:
    projection = _Projection(knn_error=knn_error, bulk_error=bulk_error)
    store = ElasticsearchStore(config=ElasticsearchConfig(vector_dims=vector_dims))
    store._client = projection  # type: ignore[assignment]  # test double
    return store, projection


class _StubEmbedder:
    configured = True
    model = "test-embed-model"
    config_cause = ""

    def __init__(self, outcome: EmbeddingOutcome | None = None, *, raises: bool = False) -> None:
        self._outcome = outcome
        self._raises = raises

    def embed(self, texts: list[str]) -> EmbeddingOutcome:
        if self._raises:
            raise AttributeError("'list' object has no attribute 'get'")
        if self._outcome is not None:
            return self._outcome
        return EmbeddingOutcome([[0.1] * 4 for _ in texts])


def _index(store: ElasticsearchStore, embedder: Any) -> dict[str, Any]:
    return store.index_with_embeddings(
        "repo:524", "s1", {"a.java": "class A { public void m() {} }"}, embedder
    )


def test_an_endpoint_failure_still_indexes_every_chunk_and_says_why() -> None:
    store, projection = _store()
    report = _index(
        store,
        _StubEmbedder(EmbeddingOutcome(None, "endpoint_connect_failed", "connect failed")),
    )
    assert report["indexed"] >= 1 and report["embedded"] == 0
    assert report["embedding_causes"] == "endpoint_connect_failed"
    assert projection.docs, "BM25 must stay usable when only the vectors failed"
    assert any("connect failed" in note for note in report["embedding_notes"])


def test_vectors_at_the_wrong_width_are_named_not_only_counted() -> None:
    """``indexed=42 embedded=0`` reads the same for a dead endpoint and a 3-wide model."""
    store, projection = _store()
    report = _index(store, _StubEmbedder(EmbeddingOutcome([[0.1, 0.2] for _ in range(42)])))
    assert report["embedding_causes"] == "vectors_dims_mismatched"
    assert report["vectors_skipped"] == report["indexed"] >= 1
    assert report["embedded"] == 0
    assert all("embedding" not in d["_source"] for d in projection.docs)


def test_an_escaping_embedder_still_leaves_a_keyword_usable_projection() -> None:
    store, projection = _store()
    report = _index(store, _StubEmbedder(raises=True))
    assert report["embedding_causes"] == "embed_call_crashed"
    assert projection.docs, "this method's own promise is 'indexed regardless'"
    assert report["embedded"] == 0


def test_an_unnamed_duck_typed_failure_gets_a_code_in_the_report() -> None:
    store, _ = _store()
    report = _index(store, _StubEmbedder(EmbeddingOutcome(None, "", "no reason given")))
    assert report["embedding_causes"] == "cause_missing"


def test_a_projection_built_with_vectors_reports_no_cause() -> None:
    store, _ = _store()
    report = _index(store, _StubEmbedder())
    assert report["embedding_causes"] is None
    assert report["embedded"] == report["indexed"] >= 1


# ── E. the note: what an operator and a SQL predicate actually see ──────────


class _NodeHarness:
    """Run the retrieval node against the real store and the real hybrid pipeline.

    Only the process boundaries are stubbed — the ES server's answers, the
    symbol graph, ``git rev-parse``, the embedder.  The degradation under test
    is produced by the product: the note must not be assembled from a pasted
    report, or this file pins nothing about what an operator sees.
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path

    def run(self, *, store: Any, embedder: Any) -> dict[str, Any]:
        import agent.nodes.retrieve_repository_context as node_module
        from agent.nodes.retrieve_repository_context import (
            retrieve_repository_context_node,
        )

        workspace = self.tmp_path / "ws" / "src" / "main" / "java"
        workspace.mkdir(parents=True)
        (workspace / "Svc.java").write_text(
            "class Svc { void send(String t) {} }", encoding="utf-8"
        )

        self.monkeypatch.setattr("storage.elasticsearch.ElasticsearchStore", lambda: store)
        self.monkeypatch.setattr(
            "agent.repo_graph.RepoGraph",
            lambda files: SimpleNamespace(expand_hits=lambda hits, hops=1: list(hits)),
        )
        self.monkeypatch.setattr(
            "retrieval.embeddings.EmbeddingClient",
            SimpleNamespace(from_env=lambda: embedder),
        )
        self.monkeypatch.setattr(
            node_module,
            "subprocess",
            SimpleNamespace(
                run=lambda *args, **kwargs: SimpleNamespace(
                    returncode=0, stdout="deadbeef\n", stderr=""
                )
            ),
        )
        state: Any = {
            "head_workspace": str(self.tmp_path / "ws"),
            "repo_path": "demo-repo",
            "requirement_text": "email change",
            "use_llm": False,
            "job_id": "j-524",
        }
        return retrieve_repository_context_node(state)


@pytest.fixture(autouse=True)
def _no_optional_rerank_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rerank must stay out of these cases unless the case puts it in."""
    monkeypatch.delenv("RERANK_MODEL", raising=False)


def test_the_note_carries_the_vector_code_and_not_the_rejected_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = "REPO-BODY-MARKER-524"
    store, _ = _store(
        knn_error=RuntimeError(
            "index [code] rejected source public class Svc { /* " + marker + " */ }"
        )
    )
    result = _NodeHarness(monkeypatch, tmp_path).run(store=store, embedder=_StubEmbedder())
    note = result["retrieval_note"]
    assert "embedding_causes=vector_store_failed" in note, note
    assert marker not in note, "repository payload reached the persisted note"
    assert "embedding_error" not in note


def test_the_note_makes_the_dims_failure_readable_alongside_the_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = _store()
    note = _NodeHarness(monkeypatch, tmp_path).run(
        store=store, embedder=_StubEmbedder(EmbeddingOutcome([[0.1, 0.2] for _ in range(30)]))
    )["retrieval_note"]
    assert "vectors_dims_mismatched" in note, note
    assert " skipped=" in note and "skipped=0" not in note
    assert "embedded=0" in note


def test_a_gateway_sentence_with_a_local_path_never_reaches_the_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = _store()
    secret = "C:\\Users\\svc\\secrets\\token.json"
    note = _NodeHarness(monkeypatch, tmp_path).run(
        store=store,
        embedder=_StubEmbedder(
            EmbeddingOutcome(
                None,
                "endpoint_connect_failed",
                "embedding endpoint connect failed (ConnectError): " + secret,
            )
        ),
    )["retrieval_note"]
    assert "embedding_causes=endpoint_connect_failed" in note, note
    assert note.count("endpoint_connect_failed") == 1, (
        "both layers saw this one fact; the note must name it once: " + note
    )
    assert "token.json" not in note
    assert "ConnectError" not in note


def test_the_note_says_nothing_about_the_vector_channel_when_nothing_degraded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, _ = _store()
    note = _NodeHarness(monkeypatch, tmp_path).run(store=store, embedder=_StubEmbedder())[
        "retrieval_note"
    ]
    assert "embedding_causes=" not in note, note
    assert "skipped=" not in note
    assert "mode=hybrid" in note


def test_a_crash_in_the_index_write_names_its_type_and_loses_its_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The note's own free-text leg: this handler wraps a bulk write of the source.

    It used to append ``str(exc)[:200]``; a bulk error quotes the documents it
    rejected, and two hundred characters of Java is a complete sentence.
    """
    marker = "REPO-BODY-MARKER-524"
    store, _ = _store(bulk_error=RuntimeError("bulk rejected [" + marker + "]"))
    result = _NodeHarness(monkeypatch, tmp_path).run(store=store, embedder=_StubEmbedder())
    assert result["retrieval_note"] == "Repository retrieval failed: RuntimeError"
    assert marker not in str(result)
    assert result["repo_context"] == []


def test_every_addition_stays_behind_the_words_storage_reads_as_the_demo_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``storage/mysql.py`` matches ``seeded demo`` at position 1 of this field.

    So a code may be appended and never prepended: an appended word is an
    annotation, a prepended one silently re-flags every retrieval as a
    demonstration run.
    """
    store, _ = _store(knn_error=RuntimeError("nope"))
    note = _NodeHarness(monkeypatch, tmp_path).run(store=store, embedder=_StubEmbedder())[
        "retrieval_note"
    ]
    assert note.startswith("hybrid_rrf mode="), note
    assert not note.startswith("seeded demo")
