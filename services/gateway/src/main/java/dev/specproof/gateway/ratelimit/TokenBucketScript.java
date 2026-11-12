package dev.specproof.gateway.ratelimit;

import reactor.core.publisher.Mono;

/**
 * The Redis/Lua transport for one token-bucket admission decision, isolated
 * behind an interface so the admission policy ({@link RedisTokenBucketRateLimiter})
 * can be tested without a broker and without mocking a concrete reactive template.
 *
 * <p>The production implementation ({@link RedisTokenBucketScript}) owns the Lua
 * {@code EVAL} and the result parsing; everything above this line is policy.</p>
 */
public interface TokenBucketScript {

    /**
     * Run the bucket decision for {@code bucketKey}.
     *
     * @return a Mono emitting exactly one {@link RateLimitResult}; errors surface
     *         as an error signal (the limiter decides fail-open vs fail-closed)
     */
    Mono<RateLimitResult> run(String bucketKey, long capacity, double refillPerSecond, long ttlMs);
}
