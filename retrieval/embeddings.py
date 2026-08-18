"""EmbeddingClient — OpenAI-compatible /embeddings BYOK client (RAG 2.0, 卷IV 4.1).

Configuration resolution (first hit wins):

    LLM_EMBEDDING_BASE_URL / LLM_EMBEDDING_API_KEY / LLM_EMBEDDING_MODEL
        → fallback LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
        → unconfigured: "configured" is False and "embed" returns
          "(None, reason)".

Honesty contract (卷IV 4.3): vectors are either real gateway output or
nothing. Every failure path — unconfigured, transport error, non-2xx,
malformed payload, inconsistent dims — returns "(None, reason)" so the
caller degrades to BM25+graph retrieval. Zero vectors are never
fabricated.

429 handling mirrors providers/openai_compatible.py: retry up to
LLM_MAX_RETRIES times, honoring the gateway's Retry-After header,
otherwise capped exponential backoff (max 60s). tenacity is the single
retry owner.
"""
from __future__ import annotations

import os

import httpx
from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_attempt

_DEFAULT_BATCH_SIZE = 64
_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Retry-After header (seconds form only); None when absent/HTTP-date."""
    response = getattr(exc, "response", None)
    raw = response.headers.get("retry-after") if response is not None else None
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _wait_retry_after_or_exponential(retry_state: RetryCallState) -> float:
    """429 → honor Retry-After when present; otherwise capped exponential."""
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    retry_after = _retry_after_seconds(exception) if exception is not None else None
    if retry_after is not None:
        return retry_after
    return min(60.0, float(2 ** max(0, retry_state.attempt_number - 1)))


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


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
        self._config_reason = self._resolve_config_reason()

    def _resolve_config_reason(self) -> str:
        if not self.base_url:
            return "LLM_EMBEDDING_BASE_URL/LLM_BASE_URL not set — embeddings unconfigured"
        if not self.api_key or self.api_key == "replace_me":
            return (
                "LLM_EMBEDDING_API_KEY/LLM_API_KEY not set or placeholder "
                "'replace_me' — embeddings unconfigured"
            )
        if not self.model:
            return "LLM_EMBEDDING_MODEL/LLM_MODEL not set — embeddings unconfigured"
        return ""

    @property
    def configured(self) -> bool:
        return not self._config_reason

    @property
    def config_reason(self) -> str:
        return self._config_reason

    @classmethod
    def from_env(cls) -> EmbeddingClient:
        return cls()

    def embed(self, texts: list[str]) -> tuple[list[list[float]] | None, str]:
        """Embed texts in batches of at most "batch_size".

        All-or-nothing: either every text gets a real vector, or the call
        returns "(None, reason)" — partial results are never mixed in.
        """
        if not self.configured:
            return (None, self._config_reason)
        if not texts:
            return ([], "")
        batches = [
            texts[i : i + self.batch_size] for i in range(0, len(texts), self.batch_size)
        ]
        vectors: list[list[float]] = []
        dims: int | None = None
        for batch in batches:
            batch_vectors, reason = self._embed_batch(batch)
            if batch_vectors is None:
                return (None, reason)
            for vector in batch_vectors:
                if not vector:
                    return (None, "embedding endpoint returned an empty vector")
                if dims is None:
                    dims = len(vector)
                elif len(vector) != dims:
                    return (None, "inconsistent vector dims across batches")
                vectors.append(vector)
        return (vectors, "")

    def _embed_batch(self, batch: list[str]) -> tuple[list[list[float]] | None, str]:
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
            wait=_wait_retry_after_or_exponential,
            stop=stop_after_attempt(self.max_retries + 1),
            reraise=True,
        )
        try:
            response = retryer(_attempt)
        except httpx.HTTPStatusError as exc:
            return (None, "embedding endpoint HTTP " + str(exc.response.status_code))
        except Exception as exc:  # noqa: BLE001 — transport/timeout, honest reason
            return (None, "embedding endpoint unreachable: " + str(exc)[:160])
        try:
            payload = response.json()
        except ValueError:
            return (None, "embedding endpoint returned non-JSON")
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(batch):
            return (None, "embedding endpoint returned no/mismatched data array")
        try:
            ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
            vectors = [[float(x) for x in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            return (None, "malformed embedding response: " + str(exc)[:120])
        return (vectors, "")
