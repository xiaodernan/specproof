package dev.specproof.gateway.ratelimit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import reactor.core.publisher.Mono;

/**
 * Distributed token-bucket admission backed by Redis — the edge's multi-replica
 * coordination point.
 *
 * <p>Why Redis, why a bucket: the existing {@code EdgeRateLimiter} keeps an
 * in-memory bucket per gateway instance, so N replicas admit N times the intended
 * rate — correct only for a single edge. A shared bucket in Redis makes the limit
 * hold across the whole fleet: every replica decrements the SAME counter, so
 * "50 req/s at the edge" means 50 across all of them, not 50 each.</p>
 *
 * <p>The bucket lives in one Redis hash per key and the whole decision is one Lua
 * {@code EVAL} — atomic, so two replicas racing on the same key cannot both
 * believe a token was free (the classic lost-update a read-then-write would
 * suffer). The refill is LAZY (O(1) regardless of idle time) and Redis owns the
 * wall clock via {@code PEXPIRE}, so an idle key simply expires instead of being
 * kept warm by a fleet that forgot it.</p>
 *
 * <p>Fail semantics are the OS-level contract: this limiter NEVER blocks the
 * event loop. Every path is a non-blocking reactive Mono, and when Redis itself is
 * unreachable the limiter resolves to a configured fallback (fail-open = let the
 * request through, fail-closed = 429) — the edge degrades to "admit everything"
 * or "admit nothing", never to "hang".</p>
 */
public final class RedisTokenBucketRateLimiter {

    private final TokenBucketScript script;
    private final MeterRegistry meterRegistry;
    private final String name;
    private final long capacity;
    private final double refillPerSecond;
    private final long ttlMs;
    private final boolean failOpen;

    private final Counter allowedCounter;
    private final Counter deniedCounter;

    public RedisTokenBucketRateLimiter(TokenBucketScript script,
                                       MeterRegistry meterRegistry,
                                       String name,
                                       int capacity,
                                       double refillPerSecond,
                                       long ttlMs,
                                       boolean failOpen) {
        this.script = script;
        this.meterRegistry = meterRegistry;
        this.name = name;
        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.ttlMs = ttlMs;
        this.failOpen = failOpen;
        this.allowedCounter = Counter.builder("specproof.gateway.distributed.rate.decision")
                .tag("limiter", name).tag("decision", "allowed").register(meterRegistry);
        this.deniedCounter = Counter.builder("specproof.gateway.distributed.rate.decision")
                .tag("limiter", name).tag("decision", "denied").register(meterRegistry);
    }

    /**
     * Try to consume one token for the given composite key.
     *
     * @param key the bucket key (global, or a caller-derived identity)
     * @return a Mono that emits exactly one decision and never blocks
     */
    public Mono<RateLimitResult> tryAcquire(String key) {
        String bucketKey = "specproof:ratelimit:" + name + ":" + key;
        return script.run(bucketKey, capacity, refillPerSecond, ttlMs)
                .defaultIfEmpty(RateLimitResult.ALLOWED)
                .onErrorResume(t -> Mono.just(failOpen ? RateLimitResult.ALLOWED : RateLimitResult.DENIED))
                .doOnNext(result -> {
                    if (result.isAllowed()) allowedCounter.increment();
                    else deniedCounter.increment();
                });
    }

    /** The bucket key prefix this limiter writes under (for diagnostics). */
    public String bucketPrefix() {
        return "specproof:ratelimit:" + name + ":";
    }
}
