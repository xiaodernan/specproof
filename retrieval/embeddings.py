"""EmbeddingClient — OpenAI-compatible /embeddings BYOK client (RAG 2.0, 卷IV 4.1).

Configuration resolution (first hit wins):

    LLM_EMBEDDING_BASE_URL / LLM_EMBEDDING_API_KEY / LLM_EMBEDDING_MODEL
        → fallback LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
        → unconfigured: "configured" is False and "embed" returns an
          EmbeddingOutcome whose vectors are None and whose cause names
          which setting is missing.

Honesty contract (卷IV 4.3): vectors are either real gateway output or
nothing. Every failure path — unconfigured, transport error, non-2xx,
malformed payload, inconsistent dims — returns the reason, so the caller
degrades to BM25+graph retrieval. Zero vectors are never fabricated, and
reading the reply is a total function: a shape this reader cannot use is a
named degradation rather than an exception, because a caller that asked for
a vector has usually spent its keyword search already and would lose those
hits to a crash.

Why every exit carries a code as well as a sentence (#524): the design
table promises "embedding_error=原因", and the sentence keeps being that
reason — but a sentence is prose that quotes the gateway or the transport
(`/var/run/embed.sock`, a Windows path to a token file, the first characters
of a reply body), and one vector-channel sentence used to cover a timeout, a
refused connection, a protocol break and a proxy failure at once. The
channel's degradation is reported to `retrieval_note`, which is persisted
in the run summary, queried with JSON_EXTRACT and put on notifications, so
the only thing allowed to travel there is a registered code from
EMBEDDING_CAUSES. A new failure has to be named before it can be reported.

429 handling shares the one producer with providers/openai_compatible.py:
retry up to LLM_MAX_RETRIES times, honoring the gateway's Retry-After header,
otherwise capped exponential backoff (max 60s) — both the header parse and the
wait policy live in contracts/retry_after.py (#517). tenacity is the single
retry owner.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt

from contracts.retry_after import wait_retry_after_or_exponential
from retrieval._env import env_int as _env_int

_DEFAULT_BATCH_SIZE = 64
_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

#: Closed vocabulary of vector-channel failures. The last four codes belong
#: to the callers rather than to this client: ``retrieval/hybrid.py`` names
#: why it never asked for a vector (``no_embedder`` / ``not_attempted``) and
#: what the search backend did when it was asked (``vector_store_failed``),
#: and ``storage/elasticsearch.py`` names the one fact only it can see —
#: vectors that came back at the wrong width (``vectors_dims_mismatched``).
#: ``cause_missing`` is the honest name for a caller-supplied embedder that
#: reports "no vectors" without naming why — duck-typed embedders are
#: measured to disagree about the success sentinel already, so an unnamed
#: failure gets a code instead of silently becoming no failure at all.
#: ``embed_call_crashed`` is the caller's last line: ``embed()`` reads the
#: gateway's reply, and until #524 six reply shapes raised ``AttributeError``
#: out of that read — which is why the reader now refuses shapes it cannot
#: name instead of letting the shape reach ``getattr``.
EMBEDDING_CAUSES: frozenset[str] = frozenset(
    {
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
)


@dataclass(frozen=True)
class EmbeddingOutcome:
    """Real vectors, or nothing plus (code, sentence) naming what happened.

    ``cause`` is empty exactly when ``vectors`` is not None.
    """

    vectors: list[list[float]] | None
    cause: str = ""
    sentence: str = ""


def _failed(cause: str, sentence: str) -> EmbeddingOutcome:
    return EmbeddingOutcome(None, cause, sentence)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


def _classify_transport(exc: BaseException) -> tuple[str, str]:
    """Split the sentence that used to say one thing about seven failures.

    Measured on httpx 0.28.1 the two families are disjoint: ``ConnectTimeout``
    is a ``TimeoutException``, not a ``ConnectError``, so a handshake that ran
    out of time is reported as a timeout.  ``ConnectError`` is checked first
    anyway, so that a release which makes it both — the shape the old code
    assumed when it called every one of these "unreachable" — keeps reporting
    the reachability failure rather than the slowness.
    """
    if isinstance(exc, httpx.ConnectError):
        return ("endpoint_connect_failed", "connect failed")
    if isinstance(exc, httpx.TimeoutException):
        return ("endpoint_timeout", "timed out")
    return ("endpoint_transport_failed", "transport failed")


class EmbeddingClient:
    """BYOK embeddings via any OpenAI-compatible /embeddings endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        *,
        batch_size: int | None = None,
        max_retries: int | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if base_url is not None:
            self.base_url = base_url.rstrip("/")
        else:
            self.base_url = (
                os.getenv("LLM_EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL") or ""
            ).rstrip("/")
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = (
                os.getenv("LLM_EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY") or ""
            )
        if model is not None:
            self.model = model
        else:
            self.model = (
                os.getenv("LLM_EMBEDDING_MODEL") or os.getenv("LLM_MODEL") or ""
            )
        if batch_size is not None:
            self.batch_size = max(1, batch_size)
        else:
            self.batch_size = max(
                1, _env_int("LLM_EMBEDDING_BATCH_SIZE", _DEFAULT_BATCH_SIZE)
            )
        if max_retries is not None:
            self.max_retries = max(0, max_retries)
        else:
            self.max_retries = _env_int("LLM_MAX_RETRIES", default=2)
        self.timeout = timeout
        self._transport = transport
        self._config_cause, self._config_reason = self._resolve_config_failure()

    def _resolve_config_failure(self) -> tuple[str, str]:
        if not self.base_url:
            return (
                "base_url_not_set",
                "LLM_EMBEDDING_BASE_URL/LLM_BASE_URL not set — embeddings unconfigured",
            )
        if not self.api_key or self.api_key == "replace_me":
            return (
                "api_key_not_set_or_placeholder",
                "LLM_EMBEDDING_API_KEY/LLM_API_KEY not set or placeholder "
                "'replace_me' — embeddings unconfigured",
            )
        if not self.model:
            return (
                "model_not_set",
                "LLM_EMBEDDING_MODEL/LLM_MODEL not set — embeddings unconfigured",
            )
        return ("", "")

    @property
    def configured(self) -> bool:
        return not self._config_reason

    @property
    def config_reason(self) -> str:
        return self._config_reason

    @property
    def config_cause(self) -> str:
        return self._config_cause

    @classmethod
    def from_env(cls) -> EmbeddingClient:
        return cls()

    def embed(self, texts: list[str]) -> EmbeddingOutcome:
        """Embed texts in batches of at most "batch_size".

        All-or-nothing: either every text gets a real vector, or the call
        returns an outcome whose vectors are None and whose cause names
        which failure it was — partial results are never mixed in.
        """
        if not self.configured:
            return EmbeddingOutcome(None, self._config_cause, self._config_reason)
        if not texts:
            return EmbeddingOutcome([])
        batches = [
            texts[i : i + self.batch_size] for i in range(0, len(texts), self.batch_size)
        ]
        vectors: list[list[float]] = []
        dims: int | None = None
        for batch in batches:
            batch_outcome = self._embed_batch(batch)
            if batch_outcome.vectors is None:
                return batch_outcome
            for vector in batch_outcome.vectors:
                if not vector:
                    return _failed(
                        "vector_empty", "embedding endpoint returned an empty vector"
                    )
                if dims is None:
                    dims = len(vector)
                elif len(vector) != dims:
                    return _failed(
                        "vector_dims_inconsistent",
                        "inconsistent vector dims across batches",
                    )
                vectors.append(vector)
        return EmbeddingOutcome(vectors)

    def _embed_batch(self, batch: list[str]) -> EmbeddingOutcome:
        def _attempt() -> httpx.Response:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(
                    self.base_url + "/embeddings",
                    json={"model": self.model, "input": batch},
                    headers={"Authorization": "Bearer " + self.api_key},
                )
                response.raise_for_status()
                return response

        retryer = Retrying(
            retry=retry_if_exception(_is_retryable),
            wait=wait_retry_after_or_exponential,
            stop=stop_after_attempt(self.max_retries + 1),
            reraise=True,
        )
        try:
            response = retryer(_attempt)
        except httpx.HTTPStatusError as exc:
            return _failed(
                "endpoint_http_error",
                "embedding endpoint HTTP " + str(exc.response.status_code),
            )
        except Exception as exc:  # noqa: BLE001 — transport/timeout, honest reason
            cause, head = _classify_transport(exc)
            sentence = "embedding endpoint " + head + " (" + type(exc).__name__ + ")"
            detail = str(exc)
            if detail:
                sentence += ": " + detail[:160]
            return _failed(cause, sentence)
        try:
            payload = response.json()
        except ValueError:
            return _failed(
                "response_not_json", "embedding endpoint returned non-JSON"
            )
        # Measured (#524): a gateway that answers with a JSON array, string,
        # number or null used to reach payload.get() and raise AttributeError
        # out of embed() — past the caller's degradation branch and, because
        # the caller asked for a vector only after its BM25 search had
        # already returned hits, out of the whole retrieval.
        if not isinstance(payload, dict):
            return _failed(
                "response_payload_not_an_object",
                "embedding endpoint returned a JSON "
                + type(payload).__name__
                + " where an object was expected",
            )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            return _failed(
                "response_data_array_mismatched",
                "embedding endpoint returned no/mismatched data array",
            )
        for item in data:
            if not isinstance(item, dict):
                return _failed(
                    "response_data_item_not_an_object",
                    "embedding endpoint returned a data item of type "
                    + type(item).__name__,
                )
        try:
            ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
            vectors = [[float(x) for x in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            return _failed(
                "response_malformed",
                "malformed embedding response ("
                + type(exc).__name__
                + "): "
                + str(exc)[:120],
            )
        return EmbeddingOutcome(vectors)
