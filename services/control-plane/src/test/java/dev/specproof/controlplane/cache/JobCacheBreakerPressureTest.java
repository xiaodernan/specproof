package dev.specproof.controlplane.cache;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The breaker's THRESHOLDS, measured rather than asserted.
 *
 * <p>{@link JobCacheBreaker} ships {@code failureThreshold = 5} and
 * {@code wait = 5s}. Those two numbers are a trade-off, and a trade-off
 * somebody typed is not a decision anybody measured. This file measures it:</p>
 *
 * <ol>
 *   <li><b>The exposure of a dead backend.</b> The threshold is the number of
 *       consecutive failures a dead backend is allowed to cost. With the
 *       deployment's {@code 50ms} command timeout, that is
 *       {@code threshold x 50ms} of latency spread over the first requests of
 *       a burst — and <b>zero</b> for every request after it. Measured here
 *       with a backend that really sleeps the timeout.</li>
 *   <li><b>What the breaker saves.</b> A thousand requests against a dead
 *       backend: the backend is called exactly {@code threshold} times, and
 *       the rest never reach it.</li>
 *   <li><b>What the threshold buys.</b> A transient blip — two failures, then
 *       health — must NOT open the breaker at threshold 5: a cache that stops
 *       asking a <i>healthy</i> backend is worse than a cache that asks a
 *       dead one twice. The same blip DOES open a breaker at threshold 2,
 *       which is the cost the higher threshold buys its protection from.</li>
 *   <li><b>Recovery.</b> After the wait, exactly one probe is let through; a
 *       successful probe closes the breaker and the traffic flows again. The
 *       measured recovery time is the wait plus the probe.</li>
 *   <li><b>The breaker's own cost.</b> On the happy path it must be
 *       negligible next to the round trip it guards: the measurement is
 *       nanoseconds per call, and the bound is one thousandth of the
 *       backend timeout.</li>
 * </ol>
 *
 * <p>The numbers are asserted as MEASUREMENTS (counts, and time bounds that
 * are orders of magnitude away from the machine's mood), never as a copy of
 * the constants under test.</p>
 */
class JobCacheBreakerPressureTest {

    /** The backend's command timeout, as the deployment now declares it. */
    private static final Duration BACKEND_TIMEOUT = Duration.ofMillis(50);

    /** The threshold the deployment ships. */
    private static final int THRESHOLD = JobCacheBreaker.DEFAULT_FAILURE_THRESHOLD;

    /** A backend whose health is a script: it fails while it is told to. */
    private static final class ScriptedBackend {
        private final AtomicInteger calls = new AtomicInteger();
        private final AtomicInteger failuresLeft = new AtomicInteger();
        private volatile long addedLatencyNanos;

        ScriptedBackend(int failures) {
            this.failuresLeft.set(failures);
        }

        /** One backend call. A failure costs the timeout, like a real one. */
        void call() throws Exception {
            calls.incrementAndGet();
            if (failuresLeft.getAndDecrement() > 0) {
                long start = System.nanoTime();
                try {
                    Thread.sleep(BACKEND_TIMEOUT.toMillis());
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                addedLatencyNanos += System.nanoTime() - start;
                throw new IllegalStateException("the backend is down");
            }
        }

        int calls() {
            return calls.get();
        }

        long addedLatencyNanos() {
            return addedLatencyNanos;
        }
    }

    /** Drive one request through the breaker, exactly as the cache does. */
    private static void request(JobCacheBreaker breaker, ScriptedBackend backend) {
        if (!breaker.tryAcquire()) {
            return; // short-circuited: the caller reads the database
        }
        try {
            backend.call();
            breaker.onSuccess();
        } catch (Exception e) {
            breaker.onFailure(e);
        }
    }

    private static MeterRegistry meters() {
        return new SimpleMeterRegistry();
    }

    @Test
    void a_dead_backend_is_called_exactly_the_threshold_number_of_times() {
        ScriptedBackend backend = new ScriptedBackend(Integer.MAX_VALUE);
        JobCacheBreaker breaker = new JobCacheBreaker(
                meters(), THRESHOLD, Duration.ofSeconds(5));

        int requests = 1000;
        for (int i = 0; i < requests; i++) {
            request(breaker, backend);
        }

        assertEquals(THRESHOLD, backend.calls(),
                "a dead backend must be called at most the threshold's worth of times");
        assertEquals(
                io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN,
                breaker.state(),
                "the breaker must be open while the backend is dead");
    }

    @Test
    void the_exposure_of_a_dead_backend_is_the_threshold_times_the_timeout() {
        ScriptedBackend backend = new ScriptedBackend(Integer.MAX_VALUE);
        JobCacheBreaker breaker = new JobCacheBreaker(
                meters(), THRESHOLD, Duration.ofSeconds(5));

        for (int i = 0; i < 50; i++) {
            request(breaker, backend);
        }

        long expected = THRESHOLD * BACKEND_TIMEOUT.toNanos();
        long measured = backend.addedLatencyNanos();
        assertTrue(measured >= expected * 0.9,
                "the burst must really have paid the timeout " + THRESHOLD
                        + " times (measured " + measured + "ns, expected about "
                        + expected + "ns)");
        assertTrue(measured < expected * 3,
                "the burst paid the timeout far more often than the threshold "
                        + "allows (measured " + measured + "ns)");
    }

    @Test
    void the_rest_of_the_burst_never_reaches_the_backend() {
        ScriptedBackend backend = new ScriptedBackend(Integer.MAX_VALUE);
        MeterRegistry registry = meters();
        JobCacheBreaker breaker = new JobCacheBreaker(
                registry, THRESHOLD, Duration.ofSeconds(5));

        int requests = 1000;
        for (int i = 0; i < requests; i++) {
            request(breaker, backend);
        }

        double shortCircuited = registry.get("specproof.cp.job.cache.breaker.calls")
                .tag("state", "short_circuited").counter().count();
        double permitted = registry.get("specproof.cp.job.cache.breaker.calls")
                .tag("state", "permitted").counter().count();
        assertEquals(requests - THRESHOLD, shortCircuited, 0.5,
                "every request after the threshold must have been short-circuited");
        assertEquals(THRESHOLD, permitted, 0.5,
                "exactly the threshold's worth of requests may reach the backend");
    }

    @Test
    void a_two_failure_blip_does_not_open_the_breaker() {
        ScriptedBackend backend = new ScriptedBackend(2);
        JobCacheBreaker breaker = new JobCacheBreaker(
                meters(), THRESHOLD, Duration.ofSeconds(5));

        for (int i = 0; i < 20; i++) {
            request(breaker, backend);
        }

        assertEquals(
                io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED,
                breaker.state(),
                "a transient blip must not stop a healthy backend from being asked");
        assertEquals(20, backend.calls(),
                "every request must still have reached the backend");
    }

    @Test
    void the_same_blip_would_open_a_breaker_at_threshold_two() {
        // The cost the threshold of 5 buys: at 2 the SAME transient blip opens
        // the breaker, and the cache stops asking a healthy backend for the
        // whole wait. This is the measurement behind the shipped number.
        ScriptedBackend backend = new ScriptedBackend(2);
        JobCacheBreaker breaker = new JobCacheBreaker(
                meters(), 2, Duration.ofSeconds(5));

        for (int i = 0; i < 20; i++) {
            request(breaker, backend);
        }

        assertEquals(
                io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN,
                breaker.state(),
                "at threshold 2 the blip opens the breaker — which is why the "
                        + "shipped threshold is 5");
        assertTrue(backend.calls() < 20,
                "a low threshold stops the cache from asking a HEALTHY backend");
    }

    @Test
    void one_probe_after_the_wait_reopens_the_way() throws Exception {
        ScriptedBackend backend = new ScriptedBackend(3);
        Duration wait = Duration.ofMillis(200);
        JobCacheBreaker breaker = new JobCacheBreaker(meters(), 3, wait);

        for (int i = 0; i < 3; i++) {
            request(breaker, backend);
        }
        assertFalse(breaker.tryAcquire(), "the breaker must be open right after the failures");

        long start = System.nanoTime();
        Thread.sleep(wait.toMillis() + 50);
        long waitedNanos = System.nanoTime() - start;

        assertTrue(breaker.tryAcquire(),
                "one probe must be let through after the wait");
        breaker.onSuccess();

        assertEquals(
                io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED,
                breaker.state(),
                "a successful probe must close the breaker again");
        assertTrue(waitedNanos >= wait.toNanos(),
                "the probe must not have come before the wait was over");
    }

    @Test
    void the_breaker_costs_almost_nothing_when_the_backend_is_healthy() {
        JobCacheBreaker breaker = new JobCacheBreaker(
                meters(), THRESHOLD, Duration.ofSeconds(5));

        int calls = 200_000;
        long start = System.nanoTime();
        for (int i = 0; i < calls; i++) {
            assertTrue(breaker.tryAcquire());
            breaker.onSuccess();
        }
        long elapsed = System.nanoTime() - start;

        double perCallNanos = (double) elapsed / calls;
        double budgetNanos = BACKEND_TIMEOUT.toNanos() / 1000.0;
        assertTrue(perCallNanos < budgetNanos,
                "the breaker's own cost (" + perCallNanos + "ns per call) must "
                        + "stay far below the round trip it guards (" + budgetNanos
                        + "ns is a thousandth of the backend timeout)");
    }
}
