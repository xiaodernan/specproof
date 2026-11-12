package dev.specproof.gateway.filter;

import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.ratelimit.RateLimitResult;
import dev.specproof.gateway.ratelimit.RedisTokenBucketRateLimiter;
import dev.specproof.gateway.ratelimit.RedisTokenBucketScript;
import dev.specproof.gateway.ratelimit.TokenBucketScript;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import reactor.core.publisher.Mono;

/**
 * The edge's DISTRIBUTED ingress rate limiter (Redis-backed token bucket,
 * Spring Cloud Gateway element, #1634).
 *
 * <p>This is the fleet-wide sibling of {@link EdgeRateLimiterGatewayFilterFactory}
 * (which keeps a per-instance in-memory bucket). That filter is correct only when
 * the edge is a single node; the moment there are two replicas, each admits its
 * own 50 req/s and the real edge rate becomes 100. This filter moves the bucket
 * into Redis so the limit is enforced ONCE, across every replica — the same
 * "one authority, no clock trust" reasoning the control plane's Redis cache uses.</p>
 *
 * <p>Activation is opt-in: the filter bean is created only when
 * {@code specproof.gateway.distributed-ratelimit.enabled=true}. When it is off
 * (the default) the bean does not exist, so the route table must not reference
 * {@code EdgeDistributedRateLimiter} — do that only after flipping the switch.
 * A bucket that points at a dead Redis resolves to the configured fallback
 * (fail-open admits, fail-closed 429s) and never blocks the event loop.</p>
 *
 * <p>Keying follows ADR-018: the edge does no auth, so the default key is a
 * single global bucket. A {@code keyStrategy: x-forwarded-for} mode exists for
 * operators who want per-origin shaping in front of an authenticated upstream,
 * but it is NOT tenant isolation and must not be sold as such.</p>
 */
@Component
@ConditionalOnProperty(
        prefix = "specproof.gateway.distributed-ratelimit",
        name = "enabled",
        havingValue = "true")
public class EdgeDistributedRateLimiterGatewayFilterFactory
        extends AbstractGatewayFilterFactory<EdgeDistributedRateLimiterGatewayFilterFactory.Config> {

    public static final String DEFAULT_INSTANCE = "specproof-edge-distributed";

    private final TokenBucketScript bucketScript;
    private final MeterRegistry meterRegistry;

    /** Production wiring: build the Redis-backed script from the reactive template. */
    public EdgeDistributedRateLimiterGatewayFilterFactory(
            ReactiveStringRedisTemplate redis, MeterRegistry meterRegistry) {
        super(Config.class);
        this.meterRegistry = meterRegistry;
        this.bucketScript = new RedisTokenBucketScript(redis,
                RedisScript.of(new ClassPathResource("redis/ratelimit-token-bucket.lua"), List.class));
    }

    /** Alternative wiring: inject a script directly (e.g. a mock, or a custom
     *  transport) with no Redis. Public so it can be used from tests in a sibling
     *  package and from operators who want to swap the bucket backend. */
    public EdgeDistributedRateLimiterGatewayFilterFactory(
            TokenBucketScript bucketScript, MeterRegistry meterRegistry) {
        super(Config.class);
        this.meterRegistry = meterRegistry;
        this.bucketScript = bucketScript;
    }

    @Override
    public String name() {
        return "EdgeDistributedRateLimiter";
    }

    @Override
    public GatewayFilter apply(Config config) {
        long ttlMs = ttlFor(config.getCapacity(), config.getRefillPerSecond());
        RedisTokenBucketRateLimiter limiter = new RedisTokenBucketRateLimiter(
                bucketScript, meterRegistry, config.getName(),
                config.getCapacity(), config.getRefillPerSecond(), ttlMs,
                "open".equalsIgnoreCase(config.getFailMode()));

        Counter rejected = Counter.builder("specproof.gateway.distributed.rate.limited")
                .tag("limiter", config.getName())
                .register(meterRegistry);
        String keyStrategy = config.getKeyStrategy();

        return (ServerWebExchange exchange, GatewayFilterChain chain) -> {
            String key = resolveKey(exchange, keyStrategy);
            return limiter.tryAcquire(key)
                    .flatMap(result -> result.isAllowed()
                            ? chain.filter(exchange)
                            : write429(exchange, config, result, rejected));
        };
    }

    /**
     * A key's idle TTL is just past the time to refill from empty — enough to
     * hold a full bucket's worth of state, short enough that a dead caller's key
     * does not live forever.
     */
    private static long ttlFor(int capacity, double refillPerSecond) {
        double secondsToFull = refillPerSecond > 0 ? (double) capacity / refillPerSecond : 1.0;
        return (long) (secondsToFull * 1000.0) + 2000L;
    }

    private static String resolveKey(ServerWebExchange exchange, String strategy) {
        if ("x-forwarded-for".equalsIgnoreCase(strategy)) {
            String xff = exchange.getRequest().getHeaders().getFirst("X-Forwarded-For");
            if (xff != null && !xff.isBlank()) {
                return xff.split(",")[0].trim();
            }
        }
        return "global";
    }

    private static Mono<Void> write429(ServerWebExchange exchange, Config config,
                                      RateLimitResult result, Counter rejected) {
        rejected.increment();
        String requestId = EdgeRequestIdGlobalFilter.requestIdOf(exchange);
        long retryAfter = Math.max(1, result.getRetryAfterMs());
        StringBuilder json = new StringBuilder()
                .append("{\"error\":\"rate_limited\",\"edge\":\"distributed-rate-limit\"")
                .append(",\"retry_after_seconds\":").append(retryAfter)
                .append(",\"remaining\":").append(result.getRemaining());
        if (requestId != null && !requestId.isBlank()) {
            json.append(",\"request_id\":\"").append(requestId).append("\"");
        }
        json.append("}");
        byte[] body = json.toString().getBytes(StandardCharsets.UTF_8);
        exchange.getResponse().setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        exchange.getResponse().getHeaders().set("Retry-After", String.valueOf(retryAfter));
        exchange.getResponse().getHeaders().setContentLength(body.length);
        return exchange.getResponse()
                .writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(body)))
                .onErrorResume(t -> Mono.empty());
    }

    public static class Config {
        /** The distributed limiter instance name (the Redis key prefix). */
        private String name = DEFAULT_INSTANCE;
        /** Burst capacity: tokens a bucket can hold at once. */
        private int capacity = 100;
        /** Tokens replenished per second (the steady-state rate). */
        private double refillPerSecond = 50;
        /** Key strategy: {@code global} (default) or {@code x-forwarded-for}. */
        private String keyStrategy = "global";
        /** Redis-unavailable fallback: {@code open} admits, {@code closed} 429s. */
        private String failMode = "open";

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getCapacity() {
            return capacity;
        }

        public void setCapacity(int capacity) {
            this.capacity = capacity;
        }

        public double getRefillPerSecond() {
            return refillPerSecond;
        }

        public void setRefillPerSecond(double refillPerSecond) {
            this.refillPerSecond = refillPerSecond;
        }

        public String getKeyStrategy() {
            return keyStrategy;
        }

        public void setKeyStrategy(String keyStrategy) {
            this.keyStrategy = keyStrategy;
        }

        public String getFailMode() {
            return failMode;
        }

        public void setFailMode(String failMode) {
            this.failMode = failMode;
        }
    }
}
