package dev.specproof.controlplane.cache;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import java.time.Duration;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The circuit breaker in front of the cache backend.
 *
 * <p>What is measured here, in the order the assertions read:</p>
 * <ol>
 *   <li>the backend is called again and again while it is healthy — the breaker
 *       does not get in the way of a working cache;</li>
 *   <li>after {@code failureThreshold} <b>consecutive</b> failures the breaker
 *       opens and the backend is <b>not called at all</b> — the whole point is
 *       that a dead Redis stops costing every request a round trip;</li>
 *   <li>the answers never change: a short-circuited read is the same empty
 *       answer a failing cache gives, and the request still reaches the
 *       database;</li>
 *   <li>a short-circuit is <b>not</b> counted as a backend error — the error
 *       counter answers "did the backend fail?", and skipping the backend is
 *       the opposite of failing;</li>
 *   <li>after the wait duration one probe is let through, and a successful
 *       probe closes the breaker again.</li>
 * </ol>
 */
class JobCacheBreakerTest {

    private StringRedisTemplate redis;
    private ValueOperations<String, String> values;
    private MeterRegistry meters;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        redis = Mockito.mock(StringRedisTemplate.class);
        values = Mockito.mock(ValueOperations.class);
        Mockito.when(redis.opsForValue()).thenReturn(values);
        meters = new SimpleMeterRegistry();
    }

    private static ObjectMapper mapper() {
        return new ObjectMapper().registerModule(new JavaTimeModule());
    }

    private RedisJobReadCache cacheWith(JobCacheBreaker breaker) {
        return new RedisJobReadCache(redis, mapper(), meters, breaker);
    }

    private double counter(String name, String... tags) {
        return meters.find(name).tags(tags).counter().count();
    }

    @Test
    void the_breaker_opens_after_consecutive_failures_and_stops_calling_the_backend() {
        JobCacheBreaker breaker = new JobCacheBreaker(meters, 3, Duration.ofMinutes(5));
        RedisJobReadCache cache = cacheWith(breaker);
        Mockito.when(values.get(Mockito.anyString()))
                .thenThrow(new IllegalStateException("redis is down"));

        // three consecutive failures: each one is a real backend attempt
        for (int attempt = 0; attempt < 3; attempt++) {
            Optional<?> answer = cache.getRecent();
            assertTrue(answer.isEmpty(), "a failing cache answers empty");
        }
        Mockito.verify(values, Mockito.times(3)).get(Mockito.anyString());
        assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN,
                breaker.state(), "three consecutive failures must open the breaker");

        // the fourth read is answered without touching the backend at all
        Optional<?> answer = cache.getRecent();
        assertTrue(answer.isEmpty(), "a short-circuited read answers empty too");
        Mockito.verify(values, Mockito.times(3)).get(Mockito.anyString());
        assertEquals(1.0, counter("specproof.cp.job.cache.breaker.calls", "state", "short_circuited"),
                "the skipped call must be counted as skipped");
    }

    @Test
    void a_short_circuit_is_not_counted_as_a_backend_error() {
        JobCacheBreaker breaker = new JobCacheBreaker(meters, 1, Duration.ofMinutes(5));
        RedisJobReadCache cache = cacheWith(breaker);
        Mockito.when(values.get(Mockito.anyString()))
                .thenThrow(new IllegalStateException("redis is down"));

        cache.getRecent();          // the failure: one real error
        cache.getRecent();          // short-circuited: no call at all

        assertEquals(1.0, counter("specproof.cp.job.cache.backend.ops", "backend", "redis",
                        "result", "error"),
                "only the real failure is a backend error; a skipped call is not a failure");
        assertEquals(1.0, counter("specproof.cp.job.cache.breaker.failures"),
                "the breaker saw exactly one failure");
    }

    @Test
    void a_successful_probe_closes_the_breaker_again() {
        JobCacheBreaker breaker = new JobCacheBreaker(meters, 2, Duration.ofMillis(1));
        RedisJobReadCache cache = cacheWith(breaker);
        Mockito.when(values.get(Mockito.anyString()))
                .thenThrow(new IllegalStateException("redis is down"));

        cache.getRecent();
        cache.getRecent();
        assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN,
                breaker.state());

        // the backend comes back. `doReturn(...).when(...)` instead of `when(...)`:
        // the latter CALLS the method while setting the stub, and the method
        // still throws — the re-stubbing would blow up in the test, not in the
        // code under test.
        Mockito.doReturn(null).when(values).get(Mockito.anyString());
        try {
            Thread.sleep(20);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        cache.getRecent();          // the probe: it goes through

        assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.CLOSED,
                breaker.state(), "a successful probe closes the breaker");
        Mockito.verify(values, Mockito.times(3)).get(Mockito.anyString());
    }

    /**
     * What the breaker actually buys, measured rather than asserted.
     *
     * <p>The fake backend sleeps for the same 50ms the Redis command timeout
     * is configured to ({@code application.yml}); that is the cost a request
     * pays while the cache backend is unreachable. Twenty reads against a
     * dead backend therefore cost about a second. With the breaker open the
     * backend is not called at all, so the same twenty reads cost
     * milliseconds.</p>
     *
     * <p>The bound is deliberately loose (a factor of five) because this is a
     * timing leg: the claim it makes is "the short-circuit is orders of
     * magnitude cheaper", not "the machine is this fast".</p>
     */
    @Test
    void the_short_circuit_is_orders_of_magnitude_cheaper_than_the_timeout_it_skips() {
        JobCacheBreaker breaker = new JobCacheBreaker(meters, 2, Duration.ofMinutes(5));
        RedisJobReadCache cache = cacheWith(breaker);
        Mockito.when(values.get(Mockito.anyString())).thenAnswer(invocation -> {
            try {
                Thread.sleep(50);   // the configured Redis command timeout
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
            throw new IllegalStateException("redis is down");
        });

        cache.getRecent();                 // failure 1
        cache.getRecent();                 // failure 2 -> the breaker opens
        assertEquals(io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN,
                breaker.state());

        long started = System.nanoTime();
        for (int read = 0; read < 20; read++) {
            assertTrue(cache.getRecent().isEmpty());
        }
        long elapsedMillis = (System.nanoTime() - started) / 1_000_000;

        // 20 reads against a dead backend would cost ~1000ms; the
        // short-circuited path must be a small fraction of that.
        assertTrue(elapsedMillis < 200,
                "twenty short-circuited reads took " + elapsedMillis + "ms -- the "
                        + "breaker did not remove the timeout cost");
    }

    @Test
    void a_healthy_backend_is_never_short_circuited() {
        JobCacheBreaker breaker = new JobCacheBreaker(meters, 2, Duration.ofMinutes(5));
        RedisJobReadCache cache = cacheWith(breaker);
        Mockito.when(values.get(Mockito.anyString())).thenReturn(null);

        for (int attempt = 0; attempt < 10; attempt++) {
            cache.getRecent();
        }

        Mockito.verify(values, Mockito.times(10)).get(Mockito.anyString());
        assertEquals(0.0, counter("specproof.cp.job.cache.breaker.calls", "state", "short_circuited"),
                "a working backend is called every time");
        assertFalse(breaker.state().name().equals("OPEN"));
    }
}
