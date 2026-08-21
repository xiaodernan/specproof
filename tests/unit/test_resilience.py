"""Unit tests for providers.resilience — no network, no Docker, no real sleep.

The breaker clock and the policy sleep functions are injected, so the whole
suite runs in zero wall-clock time.
"""

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from providers.resilience import (
    NO_RETRY_STATUSES,
    RETRYABLE_STATUSES,
    CircuitBreaker,
    CircuitOpenError,
    RetryPolicy,
    _extract_status,
    classify_retry,
)


class FakeClock:
    """Injectable monotonic clock: only moves when advance() is called."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeCall:
    """Sync callable that fails `failures` times (with exc) then returns value."""

    def __init__(self, failures: int, exc: BaseException, value: str = "ok") -> None:
        self.failures = failures
        self.exc = exc
        self.value = value
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return self.value


class AsyncFakeCall:
    """Async callable that fails `failures` times (with exc) then returns value."""

    def __init__(self, failures: int, exc: BaseException, value: str = "ok") -> None:
        self.failures = failures
        self.exc = exc
        self.value = value
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return self.value


class RecordingSleeper:
    """Sync sleeper fake that records every requested delay."""

    def __init__(self) -> None:
        self.slept: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


class AsyncRecordingSleeper:
    """Async sleeper fake that records every requested delay."""

    def __init__(self) -> None:
        self.slept: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def _bare(cls: type[BaseException]) -> BaseException:
    """Instantiate an SDK exception without running its constructor (which
    requires httpx request/response objects that vary across SDK versions)."""
    return cls.__new__(cls)


class TestCircuitBreakerTripsAndRecovers:
    def test_starts_closed_and_admits_calls(self) -> None:
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.state == "closed"
        breaker.before_call()
        assert breaker.rejected_count == 0

    def test_opens_after_n_consecutive_failures(self) -> None:
        breaker = CircuitBreaker(failure_threshold=3)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "closed"
        breaker.record_failure()
        assert breaker.state == "open"
        assert breaker.trip_count == 1
        assert breaker.total_failures == 3
        assert breaker.failure_count == 3

    def test_success_resets_consecutive_failure_streak(self) -> None:
        breaker = CircuitBreaker(failure_threshold=3)
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        assert breaker.state == "closed"
        assert breaker.failure_count == 1
        assert breaker.success_count == 1

    def test_rejects_calls_while_open_before_cooldown(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0, clock=clock)
        breaker.record_failure()
        breaker.record_failure()
        clock.advance(9.9)
        with pytest.raises(CircuitOpenError) as excinfo:
            breaker.before_call()
        assert excinfo.value.state == "open"
        assert excinfo.value.retry_after == pytest.approx(0.1)
        assert breaker.rejected_count == 1

    def test_half_open_probe_admitted_after_cooldown(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0, clock=clock)
        breaker.record_failure()
        breaker.record_failure()
        clock.advance(10.0)
        breaker.before_call()
        assert breaker.state == "half_open"
        assert breaker.probe_count == 1

    def test_half_open_admits_single_probe_only(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        breaker.record_failure()
        clock.advance(5.0)
        breaker.before_call()
        with pytest.raises(CircuitOpenError) as excinfo:
            breaker.before_call()
        assert excinfo.value.state == "half_open"
        assert excinfo.value.retry_after == 0.0
        assert breaker.rejected_count == 1

    def test_probe_success_closes_breaker(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        breaker.record_failure()
        clock.advance(5.0)
        breaker.before_call()
        breaker.record_success()
        assert breaker.state == "closed"
        assert breaker.failure_count == 0
        breaker.before_call()  # flows freely again

    def test_probe_failure_reopens_with_fresh_cooldown(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=5.0, clock=clock)
        breaker.record_failure()
        clock.advance(5.0)
        breaker.before_call()
        breaker.record_failure()
        assert breaker.state == "open"
        assert breaker.trip_count == 2
        clock.advance(4.9)
        with pytest.raises(CircuitOpenError):
            breaker.before_call()
        clock.advance(0.1)
        breaker.before_call()  # fresh cooldown elapsed since the second trip
        assert breaker.state == "half_open"

    def test_metrics_report_state_and_counters(self) -> None:
        breaker = CircuitBreaker(failure_threshold=2)
        breaker.record_failure()
        breaker.record_success()
        metrics = breaker.metrics()
        assert metrics == {
            "state": "closed",
            "failure_threshold": 2,
            "recovery_timeout": 60.0,
            "failure_count": 0,
            "success_count": 1,
            "total_failures": 1,
            "trip_count": 0,
            "rejected_count": 0,
            "probe_count": 0,
        }

    def test_invalid_config_rejected(self) -> None:
        with pytest.raises(ValueError):
            CircuitBreaker(failure_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreaker(recovery_timeout=0.0)


class TestClassifyRetryMatrix:
    @pytest.mark.parametrize("status", [400, 401, 403, 422])
    def test_client_errors_never_retry(self, status: int) -> None:
        decision = classify_retry(status, None)
        assert decision.retryable is False
        assert decision.backoff_seconds == 0.0
        assert decision.status == status
        assert decision.reason == f"http_{status}_no_retry"

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_transient_statuses_retry(self, status: int) -> None:
        decision = classify_retry(status, None, attempt=1, jitter=0.0)
        assert decision.retryable is True
        assert decision.backoff_seconds == 1.0  # base * 2**0
        assert decision.status == status
        assert decision.reason == f"http_{status}_retry"

    def test_hard_no_retry_status_dominates_transient_exception(self) -> None:
        decision = classify_retry(400, TimeoutError("slow"))
        assert decision.retryable is False
        assert decision.backoff_seconds == 0.0

    def test_hard_retry_status_dominates_non_transient_exception(self) -> None:
        decision = classify_retry(503, ValueError("boom"))
        assert decision.retryable is True

    @pytest.mark.parametrize("status", [404, 409, 418, 499])
    def test_other_4xx_fail_closed(self, status: int) -> None:
        decision = classify_retry(status, None)
        assert decision.retryable is False
        assert decision.backoff_seconds == 0.0

    def test_unlisted_status_falls_back_to_transient_exception(self) -> None:
        decision = classify_retry(408, TimeoutError("gateway timeout"))
        assert decision.retryable is True
        assert "timeout" in decision.reason

    def test_stdlib_timeout_exception_retries(self) -> None:
        decision = classify_retry(None, TimeoutError("slow"), jitter=0.0)
        assert decision.retryable is True
        assert decision.reason == "timeout"
        assert decision.backoff_seconds == 1.0

    @pytest.mark.parametrize(
        "exc", [ConnectionError("refused"), ConnectionRefusedError("refused")]
    )
    def test_connection_exceptions_retry(self, exc: BaseException) -> None:
        decision = classify_retry(None, exc, jitter=0.0)
        assert decision.retryable is True
        assert decision.reason == "connection"

    def test_openai_timeout_exception_retries(self) -> None:
        decision = classify_retry(None, _bare(APITimeoutError))
        assert decision.retryable is True
        assert "timeout" in decision.reason

    def test_openai_connection_exception_retries(self) -> None:
        decision = classify_retry(None, _bare(APIConnectionError))
        assert decision.retryable is True
        assert "connection" in decision.reason

    def test_openai_rate_limit_and_server_exceptions_retry(self) -> None:
        assert classify_retry(None, _bare(RateLimitError)).retryable is True
        assert classify_retry(None, _bare(InternalServerError)).retryable is True

    def test_no_signal_fails_closed(self) -> None:
        decision = classify_retry(None, None)
        assert decision.retryable is False
        assert decision.backoff_seconds == 0.0
        assert decision.reason == "no_signal"

    def test_unknown_exception_fails_closed(self) -> None:
        decision = classify_retry(None, ValueError("boom"))
        assert decision.retryable is False
        assert decision.reason == "unclassified"

    def test_attempt_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            classify_retry(500, None, attempt=0)

    def test_matrix_constants_match_contract(self) -> None:
        assert frozenset({400, 401, 403, 422}) == NO_RETRY_STATUSES
        assert frozenset({429, 500, 502, 503}) == RETRYABLE_STATUSES


class TestBackoffSchedule:
    def test_exponential_growth(self) -> None:
        decisions = [
            classify_retry(500, None, attempt=a, base_backoff=1.0, max_backoff=60.0, jitter=0.0)
            for a in (1, 2, 3, 4)
        ]
        assert [d.backoff_seconds for d in decisions] == [1.0, 2.0, 4.0, 8.0]

    def test_max_backoff_caps_growth(self) -> None:
        decision = classify_retry(
            503, None, attempt=10, base_backoff=1.0, max_backoff=10.0, jitter=0.0
        )
        assert decision.backoff_seconds == 10.0

    def test_jitter_stays_within_bounds(self) -> None:
        for _ in range(50):
            decision = classify_retry(
                429, None, attempt=3, base_backoff=2.0, max_backoff=60.0, jitter=0.5
            )
            assert 4.0 <= decision.backoff_seconds <= 12.0  # 2*2**2 * (1 +/- 0.5)

    def test_jitter_never_goes_negative(self) -> None:
        for _ in range(50):
            decision = classify_retry(
                500, None, attempt=1, base_backoff=0.0, max_backoff=1.0, jitter=1.0
            )
            assert decision.backoff_seconds >= 0.0


class TestRetryPolicyExecutor:
    def test_success_first_attempt_no_sleep(self) -> None:
        sleeper = RecordingSleeper()
        policy = RetryPolicy(max_attempts=3, jitter=0.0, sleep_fn=sleeper)
        call = FakeCall(failures=0, exc=TimeoutError())
        assert policy.execute(call) == "ok"
        assert call.calls == 1
        assert sleeper.slept == []
        assert policy.attempts == 1
        assert policy.retries == 0

    def test_retries_transient_failures_then_succeeds(self) -> None:
        sleeper = RecordingSleeper()
        policy = RetryPolicy(
            max_attempts=3, base_backoff=2.0, jitter=0.0, sleep_fn=sleeper
        )
        call = FakeCall(failures=2, exc=TimeoutError("gateway timeout"))
        assert policy.execute(call) == "ok"
        assert call.calls == 3
        assert sleeper.slept == [2.0, 4.0]
        assert policy.attempts == 3
        assert policy.retries == 2

    def test_non_retryable_failure_raises_immediately(self) -> None:
        sleeper = RecordingSleeper()
        policy = RetryPolicy(max_attempts=5, jitter=0.0, sleep_fn=sleeper)
        call = FakeCall(failures=3, exc=ValueError("bad request shape"))
        with pytest.raises(ValueError, match="bad request shape"):
            policy.execute(call)
        assert call.calls == 1
        assert sleeper.slept == []

    def test_max_attempts_caps_retries_and_reraises(self) -> None:
        sleeper = RecordingSleeper()
        policy = RetryPolicy(max_attempts=3, jitter=0.0, sleep_fn=sleeper)
        call = FakeCall(failures=99, exc=TimeoutError())
        with pytest.raises(TimeoutError):
            policy.execute(call)
        assert call.calls == 3
        assert sleeper.slept == [1.0, 2.0]
        assert policy.attempts == 3
        assert policy.retries == 2

    def test_status_code_exception_is_classified(self) -> None:
        class HttpError(Exception):
            def __init__(self, status_code: int) -> None:
                super().__init__(f"HTTP {status_code}")
                self.status_code = status_code

        sleeper = RecordingSleeper()
        retryable = RetryPolicy(max_attempts=3, jitter=0.0, sleep_fn=sleeper)
        flaky = FakeCall(failures=1, exc=HttpError(429))
        assert retryable.execute(flaky) == "ok"
        assert flaky.calls == 2

        hard_fail = RetryPolicy(max_attempts=3, jitter=0.0, sleep_fn=sleeper)
        bad = FakeCall(failures=2, exc=HttpError(401))
        with pytest.raises(HttpError):
            hard_fail.execute(bad)
        assert bad.calls == 1

    def test_execute_rejects_awaitable_returning_callable(self) -> None:
        class AwaitableBox:
            def __await__(self):
                raise AssertionError("must not be awaited")
                yield

        policy = RetryPolicy(max_attempts=1)
        with pytest.raises(TypeError, match="execute_async"):
            policy.execute(lambda: AwaitableBox())

    def test_invalid_config_rejected(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=0)
        with pytest.raises(ValueError):
            RetryPolicy(base_backoff=5.0, max_backoff=1.0)
        with pytest.raises(ValueError):
            RetryPolicy(jitter=-0.1)

    async def test_execute_async_retries_and_recovers(self) -> None:
        sleeper = AsyncRecordingSleeper()
        policy = RetryPolicy(
            max_attempts=3, base_backoff=2.0, jitter=0.0, async_sleep_fn=sleeper
        )
        call = AsyncFakeCall(failures=2, exc=TimeoutError("gateway timeout"))
        result = await policy.execute_async(call)
        assert result == "ok"
        assert call.calls == 3
        assert sleeper.slept == [2.0, 4.0]
        assert policy.retries == 2

    async def test_execute_async_raises_non_retryable_immediately(self) -> None:
        sleeper = AsyncRecordingSleeper()
        policy = RetryPolicy(max_attempts=5, jitter=0.0, async_sleep_fn=sleeper)
        call = AsyncFakeCall(failures=3, exc=ValueError("bad"))
        with pytest.raises(ValueError, match="bad"):
            await policy.execute_async(call)
        assert call.calls == 1
        assert sleeper.slept == []

    async def test_execute_async_max_attempts_cap(self) -> None:
        sleeper = AsyncRecordingSleeper()
        policy = RetryPolicy(max_attempts=3, jitter=0.0, async_sleep_fn=sleeper)
        call = AsyncFakeCall(failures=99, exc=ConnectionError("refused"))
        with pytest.raises(ConnectionError):
            await policy.execute_async(call)
        assert call.calls == 3
        assert sleeper.slept == [1.0, 2.0]


class TestRetryPolicyWithBreaker:
    def test_open_breaker_fails_fast_without_calling(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0, clock=clock)
        breaker.record_failure()
        policy = RetryPolicy(max_attempts=3, breaker=breaker, sleep_fn=RecordingSleeper())
        call = FakeCall(failures=0, exc=TimeoutError())
        with pytest.raises(CircuitOpenError):
            policy.execute(call)
        assert call.calls == 0
        assert breaker.rejected_count == 1

    def test_retry_attempts_feed_breaker_and_stop_after_trip(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=30.0, clock=clock)
        policy = RetryPolicy(
            max_attempts=3, jitter=0.0, breaker=breaker, sleep_fn=RecordingSleeper()
        )
        call = FakeCall(failures=99, exc=TimeoutError())
        with pytest.raises(CircuitOpenError):
            policy.execute(call)
        # attempt 1 fails (streak 1), attempt 2 fails (streak 2 -> trip open),
        # attempt 3 is rejected by the open breaker.
        assert call.calls == 2
        assert breaker.state == "open"
        assert breaker.trip_count == 1

    def test_successful_attempt_reports_to_breaker(self) -> None:
        breaker = CircuitBreaker(failure_threshold=2)
        policy = RetryPolicy(
            max_attempts=2, jitter=0.0, breaker=breaker, sleep_fn=RecordingSleeper()
        )
        call = FakeCall(failures=1, exc=TimeoutError())
        assert policy.execute(call) == "ok"
        assert breaker.failure_count == 0
        assert breaker.success_count == 1

    def test_half_open_probe_through_policy_closes_breaker(self) -> None:
        clock = FakeClock()
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0, clock=clock)
        breaker.record_failure()
        clock.advance(10.0)
        policy = RetryPolicy(max_attempts=1, breaker=breaker)
        assert policy.execute(FakeCall(failures=0, exc=TimeoutError())) == "ok"
        assert breaker.state == "closed"


class TestExtractStatus:
    def test_status_code_attribute(self) -> None:
        class StatusCodeError(Exception):
            status_code = 503

        assert _extract_status(StatusCodeError()) == 503

    def test_response_status_code_attribute(self) -> None:
        class Response:
            status_code = 429

        class ResponseError(Exception):
            def __init__(self) -> None:
                super().__init__("boom")
                self.response = Response()

        assert _extract_status(ResponseError()) == 429

    def test_no_status_returns_none(self) -> None:
        assert _extract_status(ValueError("boom")) is None
