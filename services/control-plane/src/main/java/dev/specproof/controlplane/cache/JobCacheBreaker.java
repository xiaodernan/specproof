package dev.specproof.controlplane.cache;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

/**
 * A circuit breaker around the cache backend.
 *
 * <h2>Why the cache needs one</h2>
 * The cache's own contract is "it never throws" — a broken cache answers
 * "I have nothing" and the caller reads the database. That contract is what
 * keeps a dead Redis from becoming a dead API, but it has a cost the contract
 * hides: <b>every request still pays for the attempt</b>. The Redis command
 * timeout is 50ms by configuration, so a Redis that is down (or a connection
 * pool that is exhausted) costs every GET a timeout plus a connection attempt,
 * and the service degrades to "slow for everyone" instead of "degraded but
 * serving". The breaker turns that into the shape operators expect: after
 * {@code failureThreshold} consecutive backend failures the backend is
 * <b>not called at all</b> until the wait duration passes, and one probe
 * decides whether to close again.
 *
 * <h2>What it does not change</h2>
 * The answer the API gives. A short-circuited read is an empty answer, which
 * is exactly what a failing cache already answered — the request goes to the
 * database either way. Only the <i>cost</i> of the answer changes, and the
 * counters say so: {@code short_circuited} counts the calls that were never
 * made.
 *
 * <h2>Why consecutive failures, not a failure rate</h2>
 * The backend is a cache: either it answers or it does not. A percentage over
 * a sliding window would need traffic to compute, and a quiet service would
 * keep a dead backend "closed" forever. Consecutive failures with a count
 * window is the shape that matches the failure mode.
 */
public final class JobCacheBreaker {

    /** Open after this many consecutive backend failures. */
    public static final int DEFAULT_FAILURE_THRESHOLD = 5;

    /** How long the breaker stays open before it lets one probe through. */
    public static final Duration DEFAULT_WAIT = Duration.ofSeconds(5);

    private final CircuitBreaker breaker;
    private final Counter shortCircuited;
    private final Counter failures;
    private final Counter permitted;

    public JobCacheBreaker(MeterRegistry meters) {
        this(meters, DEFAULT_FAILURE_THRESHOLD, DEFAULT_WAIT);
    }

    public JobCacheBreaker(MeterRegistry meters, int failureThreshold, Duration wait) {
        int threshold = Math.max(1, failureThreshold);
        this.breaker = CircuitBreaker.of("job-cache", CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(threshold)
                .minimumNumberOfCalls(threshold)
                .failureRateThreshold(100.0f)
                .waitDurationInOpenState(wait)
                .permittedNumberOfCallsInHalfOpenState(1)
                .build());
        this.permitted = Counter.builder("specproof.cp.job.cache.breaker.calls")
                .description("Cache backend calls the breaker let through to the backend")
                .tag("state", "permitted")
                .register(meters);
        this.shortCircuited = Counter.builder("specproof.cp.job.cache.breaker.calls")
                .description("Cache backend calls the breaker let through to the backend")
                .tag("state", "short_circuited")
                .register(meters);
        this.failures = Counter.builder("specproof.cp.job.cache.breaker.failures")
                .description("Backend failures the breaker has seen")
                .register(meters);
        Gauge.builder("specproof.cp.job.cache.breaker.open",
                        () -> breaker.getState() == CircuitBreaker.State.OPEN ? 1 : 0)
                .description("1 while the cache backend is short-circuited, 0 otherwise")
                .register(meters);
    }

    /**
     * Whether the backend may be called right now.
     *
     * <p>{@code false} means "do not call it": the breaker is open, or it is
     * half-open and the single probe is already in flight. The caller then
     * answers from the database without touching the backend.</p>
     */
    public boolean tryAcquire() {
        boolean permitted = breaker.tryAcquirePermission();
        if (permitted) {
            this.permitted.increment();
        } else {
            this.shortCircuited.increment();
        }
        return permitted;
    }

    /** The call the breaker let through succeeded. */
    public void onSuccess() {
        breaker.onSuccess(0, TimeUnit.MILLISECONDS);
    }

    /** The call the breaker let through failed. */
    public void onFailure(Throwable error) {
        failures.increment();
        breaker.onError(0, TimeUnit.MILLISECONDS, error);
    }

    /** The breaker's state, for tests and for the debug header. */
    public CircuitBreaker.State state() {
        return breaker.getState();
    }

    /** Failures the breaker has seen since it was created. */
    public long failureCount() {
        return breaker.getMetrics().getNumberOfFailedCalls();
    }
}
