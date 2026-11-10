package dev.specproof.gateway.filter;

import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import io.github.resilience4j.micrometer.tagged.TaggedRateLimiterMetrics;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;
import io.github.resilience4j.ratelimiter.RateLimiterRegistry;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import reactor.core.publisher.Mono;

/**
 * The edge's ingress rate limiter (Resilience4j RateLimiter, Spring Cloud
 * Gateway element).
 *
 * <p>What this filter enforces, while it is wired into a route:
 *
 * <ul>
 *   <li>token bucket per limiter instance: {@code limitForPeriod} permits
 *       are admitted per {@code limitRefreshPeriod};</li>
 *   <li>when the bucket is empty, the request is answered locally with
 *       {@code 429} and a JSON body that names the edge — the upstream is
 *       never called;</li>
 *   <li>{@code timeoutDuration = PT0S}: the limiter never waits. An edge
 *       that blocks on an exhausted bucket holds a connection thread and
 *       becomes the thing it was protecting;</li>
 *   <li>rejections carry the request id (same contract as the 503 the
 *       circuit breaker writes) plus a {@code Retry-After} hint;</li>
 *   <li>the limiter is exposed to micrometer through the tagged binder, so
 *       Prometheus sees {@code resilience4j_ratelimiter_available_permissions}
 *       / {@code resilience4j_ratelimiter_waiting_threads} with a {@code name}
 *       tag, and {@code specproof_gateway_rate_limited_total} counts this
 *       filter's rejects — an operator can tell "upstream saturated" from
 *       "edge shedding load".</li>
 * </ul>
 *
 * <p>The limiter is keyed on nothing at all: the edge deliberately does not
 * do auth (see ADR-018), so there is no tenant or principal to key on.
 * Per-caller limiting would require the edge to parse identities, which it
 * refuses to do. A global ingress bucket is the honest control here.
 *
 * <p>There is deliberately no header-based override and no per-route knob
 * outside the YAML filter arguments — the contract is static and lives in
 * {@code application.yml} next to the route that uses it.
 */
@Component
public class EdgeRateLimiterGatewayFilterFactory
        extends AbstractGatewayFilterFactory<EdgeRateLimiterGatewayFilterFactory.Config> {

    /** The YAML argument prefix for the RateLimiter instance name. */
    public static final String DEFAULT_INSTANCE = "specproof-edge-public";

    private final RateLimiterRegistry rateLimiterRegistry;
    private final MeterRegistry meterRegistry;

    public EdgeRateLimiterGatewayFilterFactory(MeterRegistry meterRegistry) {
        super(Config.class);
        this.meterRegistry = meterRegistry;
        this.rateLimiterRegistry = RateLimiterRegistry.ofDefaults();
        // Binds both the gauges for limiters that already exist and (through
        // the registry's event consumer) any created later, e.g. by apply()
        // when the YAML filter arguments are read at startup.
        TaggedRateLimiterMetrics.ofRateLimiterRegistry(rateLimiterRegistry).bindTo(meterRegistry);
    }

    @Override
    public String name() {
        return "EdgeRateLimiter";
    }

    @Override
    public GatewayFilter apply(Config config) {
        RateLimiterConfig rateLimiterConfig = RateLimiterConfig.custom()
                .limitForPeriod(config.getLimitForPeriod())
                .limitRefreshPeriod(config.getLimitRefreshPeriod())
                .timeoutDuration(config.getTimeoutDuration())
                .build();
        RateLimiter limiter = rateLimiterRegistry.rateLimiter(config.getName(), rateLimiterConfig);
        Counter rejected = Counter.builder("specproof.gateway.rate.limited")
                .description("Requests the edge's Resilience4j rate limiter answered with 429")
                .tag("limiter", config.getName())
                .register(meterRegistry);
        return (ServerWebExchange exchange,
                org.springframework.cloud.gateway.filter.GatewayFilterChain chain) -> {
            // acquirePermission() honours the configured timeoutDuration;
            // with PT0S this never blocks and never queues the caller.
            if (limiter.acquirePermission()) {
                return chain.filter(exchange);
            }
            rejected.increment();
            return write429(exchange, config);
        };
    }

    private static Mono<Void> write429(ServerWebExchange exchange, Config config) {
        String requestId = EdgeRequestIdGlobalFilter.requestIdOf(exchange);
        StringBuilder json = new StringBuilder()
                .append("{\"error\":\"rate_limited\",\"edge\":\"rate-limit\",")
                .append("\"retry_after_seconds\":")
                .append(Math.max(1, config.getLimitRefreshPeriod().toSeconds()));
        if (requestId != null && !requestId.isBlank()) {
            json.append(",\"request_id\":\"").append(requestId).append("\"");
        }
        json.append("}");
        byte[] body = json.toString().getBytes(StandardCharsets.UTF_8);
        exchange.getResponse().setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        exchange.getResponse().getHeaders()
                .set("Retry-After", String.valueOf(Math.max(1, config.getLimitRefreshPeriod().toSeconds())));
        exchange.getResponse().getHeaders().setContentLength(body.length);
        return exchange.getResponse()
                .writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(body)))
                .onErrorResume(t -> Mono.empty());
    }

    public static class Config {
        /** The resilience4j RateLimiter instance name (declared in YAML). */
        private String name = DEFAULT_INSTANCE;
        /** Permits admitted per refresh period (the whole contract). */
        private int limitForPeriod = 50;
        /** Window over which permits refresh. */
        private Duration limitRefreshPeriod = Duration.ofSeconds(1);
        /** PT0S: reject immediately, never block the edge's threads. */
        private Duration timeoutDuration = Duration.ZERO;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public int getLimitForPeriod() {
            return limitForPeriod;
        }

        public void setLimitForPeriod(int limitForPeriod) {
            this.limitForPeriod = limitForPeriod;
        }

        public Duration getLimitRefreshPeriod() {
            return limitRefreshPeriod;
        }

        public void setLimitRefreshPeriod(Duration limitRefreshPeriod) {
            this.limitRefreshPeriod = limitRefreshPeriod;
        }

        public Duration getTimeoutDuration() {
            return timeoutDuration;
        }

        public void setTimeoutDuration(Duration timeoutDuration) {
            this.timeoutDuration = timeoutDuration;
        }
    }
}
