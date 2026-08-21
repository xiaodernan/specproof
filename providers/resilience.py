"""Provider resilience — circuit breaker, retry classification, retry policy.

M9 follow-up and grand-plan §6.1 ("Provider 与模型治理"): a flaky gateway
must degrade loudly, retry only what is safe to retry, and never hang a job.
This module provides the three cooperating pieces:

- :class:`CircuitBreaker` — closed → open after N consecutive failures, then
  a half-open probe after a cooldown; every transition is counted.
- :func:`classify_retry` — maps one failed attempt (HTTP status and/or
  exception) to a `{retryable, backoff_seconds}` decision.
- :class:`RetryPolicy` — an executor that wraps an injected callable (sync or
  async) and retries it per :func:`classify_retry`, capped at max attempts.

Retry classification matrix (the contract):

    hard no-retry     400 / 401 / 403 / 422     always wins
    hard retry        429 / 500 / 502 / 503     always wins
    other status      fail closed unless the exception is transient
    timeout           retry  (TimeoutError, openai APITimeoutError)
    connection        retry  (ConnectionError, openai APIConnectionError)
    SDK wrappers      retry  (RateLimitError, InternalServerError)
    no signal         NO retry (fail closed)

Backoff is exponential with uniform jitter and a cap::

    min(max_backoff, base_backoff * 2**(attempt - 1)) * (1 +/- jitter)

The attempt cap lives in :class:`RetryPolicy` (max_attempts); classification
only computes the per-attempt delay.

Nothing on the existing call path imports this module, so an unconfigured
deployment is byte-identical to today. Wiring is opt-in, e.g.::

    policy = RetryPolicy(max_attempts=3, breaker=CircuitBreaker())
    result = policy.execute(lambda: call_gateway())
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

T = TypeVar("T")

LOGGER = logging.getLogger("providers.resilience")

#: HTTP statuses that must NEVER be retried — the request itself is wrong and
#: no amount of retrying can fix it. These dominate even transient exceptions.
NO_RETRY_STATUSES: frozenset[int] = frozenset({400, 401, 403, 422})

#: HTTP statuses that are retryable — rate limit + gateway transient errors.
#: These dominate even non-transient exceptions (the gateway told us to retry).
RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503})

DEFAULT_BASE_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 60.0
DEFAULT_JITTER = 0.1
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_RECOVERY_TIMEOUT = 60.0


class CircuitOpenError(Exception):
    """A call was rejected because the circuit breaker is not closed."""

    def __init__(
        self, state: Literal["open", "half_open"], retry_after: float = 0.0
    ) -> None:
        self.state = state
        self.retry_after = retry_after
        if state == "half_open":
            message = "circuit breaker is half-open: a probe is already in flight"
        else:
            message = (
                f"circuit breaker is open: retry after {retry_after:.1f}s"
            )
        super().__init__(message)


@dataclass(frozen=True)
class RetryDecision:
    """Outcome of classify_retry: {retryable, backoff_seconds} + diagnostics."""

    retryable: bool
    backoff_seconds: float
    reason: str
    status: int | None = None


def _extract_status(exc: BaseException) -> int | None:
    """Best-effort HTTP status from an exception (SDK attrs or its response)."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def _backoff_seconds(
    attempt: int, base_backoff: float, max_backoff: float, jitter: float
) -> float:
    """Exponential backoff with uniform jitter, floored at zero."""
    exponential = min(max_backoff, base_backoff * (2.0 ** (attempt - 1)))
    jittered = exponential * (1.0 + random.uniform(-jitter, jitter))
    return max(0.0, jittered)


def classify_retry(
    status: int | None,
    exc: BaseException | None,
    attempt: int = 1,
    *,
    base_backoff: float = DEFAULT_BASE_BACKOFF,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
    jitter: float = DEFAULT_JITTER,
) -> RetryDecision:
    """Map one failed attempt to a retry decision.

    The hard no-retry list (400/401/403/422) always wins — even when the
    exception looks transient. The hard retry list (429/500/502/503) always
    wins too. Any other status (or no status at all) falls through to the
    exception classifier; with no signal at all the decision fails closed.

    attempt is 1-based (the attempt that just failed) and drives the
    exponential backoff; jitter is uniform in (+/- jitter) so tests can pin
    exact values with jitter=0.0.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    if status is not None and status in NO_RETRY_STATUSES:
        return RetryDecision(
            retryable=False,
            backoff_seconds=0.0,
            reason=f"http_{status}_no_retry",
            status=status,
        )
    if status is not None and status in RETRYABLE_STATUSES:
        return RetryDecision(
            retryable=True,
            backoff_seconds=_backoff_seconds(attempt, base_backoff, max_backoff, jitter),
            reason=f"http_{status}_retry",
            status=status,
        )

    if exc is None:
        reason = f"http_{status}_no_retry" if status is not None else "no_signal"
        return RetryDecision(retryable=False, backoff_seconds=0.0, reason=reason, status=status)

    if isinstance(exc, (TimeoutError, APITimeoutError)):
        return RetryDecision(
            retryable=True,
            backoff_seconds=_backoff_seconds(attempt, base_backoff, max_backoff, jitter),
            reason="timeout",
            status=status,
        )
    if isinstance(exc, (ConnectionError, APIConnectionError)):
        return RetryDecision(
            retryable=True,
            backoff_seconds=_backoff_seconds(attempt, base_backoff, max_backoff, jitter),
            reason="connection",
            status=status,
        )
    if isinstance(exc, RateLimitError):
        return RetryDecision(
            retryable=True,
            backoff_seconds=_backoff_seconds(attempt, base_backoff, max_backoff, jitter),
            reason="sdk_rate_limit",
            status=status,
        )
    if isinstance(exc, InternalServerError):
        return RetryDecision(
            retryable=True,
            backoff_seconds=_backoff_seconds(attempt, base_backoff, max_backoff, jitter),
            reason="sdk_server_error",
            status=status,
        )
    reason = f"http_{status}_no_retry" if status is not None else "unclassified"
    return RetryDecision(retryable=False, backoff_seconds=0.0, reason=reason, status=status)


class CircuitBreaker:
    """Closed → open on N consecutive failures → half-open probe after cooldown.

    State machine:

    - closed:    calls pass through; consecutive failures are counted.
    - open:      calls are rejected (CircuitOpenError) until the cooldown
                 (recovery_timeout) has elapsed.
    - half_open: exactly one probe call is admitted; success closes the
                 breaker, failure re-opens it with a fresh cooldown.

    The clock is injectable (defaults to time.monotonic) so tests never sleep.
    """

    def __init__(
        self,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: float = DEFAULT_RECOVERY_TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self._state: Literal["closed", "open", "half_open"] = "closed"
        self._opened_at = 0.0
        # Counters.
        self.failure_count = 0  # consecutive failures (resets on success)
        self.success_count = 0
        self.total_failures = 0
        self.trip_count = 0  # closed → open transitions
        self.rejected_count = 0  # calls rejected while open / half-open busy
        self.probe_count = 0  # half-open probes admitted

    @property
    def state(self) -> Literal["closed", "open", "half_open"]:
        return self._state

    @property
    def opened_at(self) -> float:
        """Monotonic timestamp of the last open transition (0.0 when never)."""
        return self._opened_at

    def before_call(self) -> None:
        """Gate one request attempt; raise CircuitOpenError when blocked.

        closed → admit. open with elapsed cooldown → transition to half_open
        and admit exactly one probe. open with pending cooldown or half_open
        busy → reject.
        """
        if self._state == "closed":
            return
        if self._state == "open" and self._clock() - self._opened_at >= self.recovery_timeout:
            self._state = "half_open"
            self.probe_count += 1
            LOGGER.info("circuit breaker half-open: admitting one probe")
            return
        self.rejected_count += 1
        if self._state == "half_open":
            raise CircuitOpenError(state="half_open", retry_after=0.0)
        raise CircuitOpenError(state="open", retry_after=self.retry_after())

    def retry_after(self) -> float:
        """Seconds until the next probe is admitted (0.0 unless open)."""
        if self._state != "open":
            return 0.0
        remaining = self.recovery_timeout - (self._clock() - self._opened_at)
        return max(0.0, remaining)

    def record_success(self) -> None:
        """Count one successful attempt; close the breaker after a good probe."""
        self.success_count += 1
        if self._state == "half_open":
            self._state = "closed"
            self.failure_count = 0
            LOGGER.info("circuit breaker closed after a successful half-open probe")
        elif self._state == "closed":
            self.failure_count = 0

    def record_failure(self) -> None:
        """Count one failed attempt; trip open when the streak crosses threshold."""
        if self._state == "half_open":
            self.failure_count = 1  # the failed probe starts a fresh streak
        else:
            self.failure_count += 1
        self.total_failures += 1
        if (self._state == "closed" and self.failure_count >= self.failure_threshold) or (
            self._state == "half_open"
        ):
            self._open()

    def _open(self) -> None:
        self._state = "open"
        self._opened_at = self._clock()
        self.trip_count += 1
        LOGGER.warning(
            "circuit breaker tripped open after %d consecutive failures (trip #%d)",
            self.failure_count,
            self.trip_count,
        )

    def metrics(self) -> dict[str, Any]:
        """Serializable snapshot (mirrors ModelRouter.metrics / TokenBudget.to_report)."""
        return {
            "state": self._state,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_failures": self.total_failures,
            "trip_count": self.trip_count,
            "rejected_count": self.rejected_count,
            "probe_count": self.probe_count,
        }


class RetryPolicy:
    """Executor: wrap an injected callable and retry per classify_retry.

    Sync callables via execute(); async callables via execute_async(). Sleep
    functions are injectable (defaults time.sleep / asyncio.sleep) so tests
    run in zero wall-clock time. When a CircuitBreaker is provided, each
    attempt is gated by breaker.before_call() and its outcome is reported to
    the breaker, so retried attempts still feed the failure streak and a
    tripped breaker fails the whole call fast.
    """

    def __init__(
        self,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        *,
        base_backoff: float = DEFAULT_BASE_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        jitter: float = DEFAULT_JITTER,
        breaker: CircuitBreaker | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        async_sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if base_backoff < 0 or max_backoff < base_backoff:
            raise ValueError("backoff must satisfy 0 <= base_backoff <= max_backoff")
        if jitter < 0:
            raise ValueError("jitter must be >= 0")
        self.max_attempts = max_attempts
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.jitter = jitter
        self.breaker = breaker
        self._sleep_fn: Callable[[float], None] = (
            sleep_fn if sleep_fn is not None else time.sleep
        )
        self._async_sleep_fn: Callable[[float], Awaitable[None]] = (
            async_sleep_fn if async_sleep_fn is not None else asyncio.sleep
        )
        self.attempts = 0
        self.retries = 0

    def _gate(self) -> None:
        if self.breaker is not None:
            self.breaker.before_call()

    def _classify(self, exc: BaseException, attempt: int) -> RetryDecision:
        return classify_retry(
            _extract_status(exc),
            exc,
            attempt,
            base_backoff=self.base_backoff,
            max_backoff=self.max_backoff,
            jitter=self.jitter,
        )

    def execute(self, call: Callable[[], T]) -> T:
        """Run the injected callable under the retry policy (sync)."""
        for attempt in range(1, self.max_attempts + 1):
            self._gate()
            self.attempts += 1
            try:
                result = call()
            except Exception as exc:
                if self.breaker is not None:
                    self.breaker.record_failure()
                decision = self._classify(exc, attempt)
                if not decision.retryable or attempt >= self.max_attempts:
                    raise
                self._sleep_fn(decision.backoff_seconds)
                self.retries += 1
            else:
                if self.breaker is not None:
                    self.breaker.record_success()
                return self._ensure_not_awaitable(result)
        raise AssertionError("unreachable: the retry loop always raises or returns")

    async def execute_async(self, call: Callable[[], Awaitable[T]]) -> T:
        """Run the injected callable under the retry policy (async)."""
        for attempt in range(1, self.max_attempts + 1):
            self._gate()
            self.attempts += 1
            try:
                result = await call()
            except Exception as exc:
                if self.breaker is not None:
                    self.breaker.record_failure()
                decision = self._classify(exc, attempt)
                if not decision.retryable or attempt >= self.max_attempts:
                    raise
                await self._async_sleep_fn(decision.backoff_seconds)
                self.retries += 1
            else:
                if self.breaker is not None:
                    self.breaker.record_success()
                return result
        raise AssertionError("unreachable: the retry loop always raises or returns")

    @staticmethod
    def _ensure_not_awaitable(result: T) -> T:
        """Guard against the coroutine-leak trap: a sync call that returns an
        awaitable was probably an async callable that never got awaited."""
        if hasattr(result, "__await__"):
            raise TypeError(
                "callable returned an awaitable from execute(); "
                "use execute_async() for async callables"
            )
        return result
