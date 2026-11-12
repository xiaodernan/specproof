package dev.specproof.gateway.ratelimit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import reactor.core.publisher.Mono;

/**
 * The Redis-backed token bucket, measured without a broker.
 *
 * <p>What can go wrong here is the POLICY and the FAILURE CONTRACT, not the wire
 * format — so the Redis transport is mocked behind {@link TokenBucketScript} and
 * the three answers it can give are asserted at the Java boundary: allowed,
 * denied, and "I am not home" (Redis error).</p>
 */
class RedisTokenBucketRateLimiterTest {

    private final TokenBucketScript script = mock(TokenBucketScript.class);
    private final SimpleMeterRegistry meters = new SimpleMeterRegistry();

    private RedisTokenBucketRateLimiter limiter(boolean failOpen) {
        return new RedisTokenBucketRateLimiter(script, meters, "test", 100, 50.0, 5000, failOpen);
    }

    private void stubResult(RateLimitResult result) {
        when(script.run(anyString(), anyLong(), anyDouble(), anyLong()))
                .thenReturn(Mono.just(result));
    }

    private void stubError() {
        when(script.run(anyString(), anyLong(), anyDouble(), anyLong()))
                .thenReturn(Mono.error(new IllegalStateException("redis down")));
    }

    @Test
    void anAllowedResultPassesThroughWithRemainingAndRetry() {
        stubResult(new RateLimitResult(true, 99L, 0L));

        RateLimitResult r = limiter(true).tryAcquire("global").block();

        assertThat(r.isAllowed()).isTrue();
        assertThat(r.getRemaining()).isEqualTo(99L);
        assertThat(r.getRetryAfterMs()).isEqualTo(0L);
        assertThat(meters.get("specproof.gateway.distributed.rate.decision")
                .tag("limiter", "test").tag("decision", "allowed").counter().count())
                .isEqualTo(1.0);
    }

    @Test
    void aDeniedResultBlocksWithRetryAfter() {
        stubResult(new RateLimitResult(false, 0L, 20L));

        RateLimitResult r = limiter(true).tryAcquire("global").block();

        assertThat(r.isAllowed()).isFalse();
        assertThat(r.getRetryAfterMs()).isEqualTo(20L);
        assertThat(meters.get("specproof.gateway.distributed.rate.decision")
                .tag("limiter", "test").tag("decision", "denied").counter().count())
                .isEqualTo(1.0);
    }

    @Test
    void aRedisErrorFailsOpenWhenConfigured() {
        stubError();
        RateLimitResult r = limiter(true).tryAcquire("global").block();
        assertThat(r.isAllowed()).isTrue();
    }

    @Test
    void aRedisErrorFailsClosedWhenConfigured() {
        stubError();
        RateLimitResult r = limiter(false).tryAcquire("global").block();
        assertThat(r.isAllowed()).isFalse();
    }

    @Test
    void anEmptyResultIsTreatedAsAllowed() {
        when(script.run(anyString(), anyLong(), anyDouble(), anyLong()))
                .thenReturn(Mono.empty());
        RateLimitResult r = limiter(true).tryAcquire("global").block();
        assertThat(r.isAllowed()).isTrue();
    }
}
