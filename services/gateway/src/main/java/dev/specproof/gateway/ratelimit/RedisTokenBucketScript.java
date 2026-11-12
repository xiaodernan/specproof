package dev.specproof.gateway.ratelimit;

import java.util.List;

import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

import reactor.core.publisher.Mono;

/**
 * The Redis-backed {@link TokenBucketScript}: one Lua {@code EVAL} per admission,
 * atomic across replicas. See {@code redis/ratelimit-token-bucket.lua} for the
 * bucket math (lazy O(1) refill, server-side expiry, integer return shape).
 *
 * <p>The execute call returns a reactive {@code Flux}; {@code .next()} takes the
 * single result and yields a {@code Mono}, which is all a script returns. The
 * returned list {@code {allowed, remaining, retry_after}} is parsed into a
 * {@link RateLimitResult} here, at the Redis boundary.</p>
 */
public final class RedisTokenBucketScript implements TokenBucketScript {

    private static final String SCRIPT_LOCATION = "redis/ratelimit-token-bucket.lua";

    private final ReactiveStringRedisTemplate redis;
    private final RedisScript<List> script;

    public RedisTokenBucketScript(ReactiveStringRedisTemplate redis, RedisScript<List> script) {
        this.redis = redis;
        this.script = script;
    }

    public RedisTokenBucketScript(ReactiveStringRedisTemplate redis) {
        this(redis, RedisScript.of(new ClassPathResource(SCRIPT_LOCATION), List.class));
    }

    @Override
    public Mono<RateLimitResult> run(String bucketKey, long capacity, double refillPerSecond, long ttlMs) {
        long now = System.currentTimeMillis();
        double ratePerMs = refillPerSecond / 1000.0;
        String[] args = {
                Long.toString(capacity),
                Double.toString(ratePerMs),
                Long.toString(now),
                "1",
                Long.toString(ttlMs)
        };
        return redis.execute(script, List.of(bucketKey), args)
                .next()
                .map(this::parse);
    }

    @SuppressWarnings("unchecked")
    private RateLimitResult parse(List<?> raw) {
        long allowedFlag = ((Number) raw.get(0)).longValue();
        long remaining = ((Number) raw.get(1)).longValue();
        long retryAfter = ((Number) raw.get(2)).longValue();
        return new RateLimitResult(allowedFlag == 1L, remaining, retryAfter);
    }
}
