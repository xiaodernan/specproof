"""The embedding client opens ONE connection for its whole life (#1620).

HTTP client hygiene, measured: a client per request means a fresh TCP (and
TLS) handshake per request -- the keep-alive the connection pool exists for
is thrown away. The embedder used to build a client per BATCH and per
RETRY; it now builds one and reuses it.

These legs count the CONSTRUCTIONS (not the wall clock): the number of
clients built is the property, and it does not wobble with the machine's
mood.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

import retrieval.embeddings as embeddings_module
from retrieval.embeddings import EmbeddingClient


class _Counter:
    """Counts the clients the module builds, and the requests they serve."""

    def __init__(self) -> None:
        self.built = 0
        self.requests = 0


def _handler(
    counter: _Counter, *, fail_first: int = 0
) -> Any:
    """A transport handler that answers with one vector per input text.

    The module checks that the returned data array has exactly one item per
    text in the batch, so the fake has to size its answer from the request
    body rather than from a constant.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        counter.requests += 1
        if counter.requests <= fail_first:
            raise httpx.ConnectError("boom", request=request)
        body = request.content.decode("utf-8")
        texts = json.loads(body).get("input", [])
        response = httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in texts]},
        )
        # raise_for_status() needs the request on the response
        response.request = request
        return response

    return handle


def _fake_factory(counter: _Counter, handler: Any) -> Any:
    def fake_outbound_client(**kwargs: Any) -> httpx.Client:
        counter.built += 1
        # the module passes a "transport" of its own; the fake installs the
        # mock one instead (httpx.Client would see the keyword twice).
        kwargs.pop("transport", None)
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=kwargs.get("timeout", 60.0),
        )

    return fake_outbound_client


def test_many_batches_share_one_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = _Counter()
    monkeypatch.setattr(
        embeddings_module, "outbound_client", _fake_factory(counter, _handler(counter))
    )

    client = EmbeddingClient(
        base_url="https://embed.invalid/v1",
        api_key="k",
        model="m",
        batch_size=2,
    )
    outcome = client.embed(["a", "b", "c", "d", "e"])
    try:
        assert outcome.vectors is not None, "the embed failed"
        assert counter.requests == 3, (
            f"{counter.requests} requests for 5 texts in batches of 2 -- the "
            "batching itself changed"
        )
        assert counter.built == 1, (
            f"{counter.built} clients were built for one embed() call -- the "
            "handshake is paid per batch again"
        )
    finally:
        client.close()


def test_a_retry_reuses_the_same_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry must not open a second client: that is exactly the storm the
    reuse removes."""
    counter = _Counter()
    monkeypatch.setattr(
        embeddings_module,
        "outbound_client",
        _fake_factory(counter, _handler(counter, fail_first=1)),
    )

    client = EmbeddingClient(
        base_url="https://embed.invalid/v1",
        api_key="k",
        model="m",
        batch_size=5,
        max_retries=2,
    )
    outcome = client.embed(["a"])
    try:
        assert outcome.vectors is not None, "the retry did not recover"
        assert counter.requests == 2, (
            f"{counter.requests} attempts, expected 2 (one failure, one success)"
        )
        assert counter.built == 1, (
            f"{counter.built} clients were built across a retry -- the retry "
            "reopened the connection instead of reusing it"
        )
    finally:
        client.close()


def test_close_releases_the_client(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = _Counter()
    closed: list[bool] = []

    def fake_outbound_client(**kwargs: Any) -> httpx.Client:
        counter.built += 1
        kwargs.pop("transport", None)
        real = httpx.Client(
            transport=httpx.MockTransport(_handler(counter)),
            timeout=kwargs.get("timeout", 60.0),
        )
        original_close = real.close

        def close() -> None:
            closed.append(True)
            original_close()

        real.close = close  # type: ignore[method-assign]
        return real

    monkeypatch.setattr(embeddings_module, "outbound_client", fake_outbound_client)

    client = EmbeddingClient(
        base_url="https://embed.invalid/v1", api_key="k", model="m"
    )
    client.embed(["a"])
    assert counter.built == 1
    client.close()
    assert closed, "close() did not close the client"
    # a second close is safe (the holder forgets the client)
    client.close()
