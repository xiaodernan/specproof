package dev.specproof.gateway.filter;

import java.nio.charset.StandardCharsets;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;

import reactor.core.publisher.Mono;

/**
 * The edge's circuit breaker for upstream calls (Spring Cloud Gateway element).
 *
 * <p>The failure contract this filter enforces, while it is wired into a route:
 *
 * <ul>
 *   <li>upstream call failures are counted against the named resilience4j
 *       {@link CircuitBreaker} (sliding window + failure rate threshold are
 *       declared in application.yml — never re-typed here);</li>
 *   <li>once the breaker is OPEN, upstream is never called: the request is
 *       answered locally with {@code 503} and a JSON body that names the edge;</li>
 *   <li>half-open probes flow through automatically
 *       (auto-transition), matching resilience4j's own semantics.</li>
 * </ul>
 *
 * <p>There is deliberately no fallback URI and no new HTTP path: the 503 is
 * produced inside the filter chain, so the edge exposes nothing that can be
 * called to "test" the breaker.
 */
@Component
public class EdgeCircuitBreakerGatewayFilterFactory
        extends AbstractGatewayFilterFactory<EdgeCircuitBreakerGatewayFilterFactory.Config> {

    /** The YAML config prefix for the CircuitBreaker instance name. */
    public static final String DEFAULT_INSTANCE = "specproof-edge";

    private final CircuitBreakerRegistry circuitBreakerRegistry;

    public EdgeCircuitBreakerGatewayFilterFactory(CircuitBreakerRegistry circuitBreakerRegistry) {
        super(Config.class);
        this.circuitBreakerRegistry = circuitBreakerRegistry;
    }

    @Override
    public String name() {
        return "EdgeCircuitBreaker";
    }

    @Override
    public GatewayFilter apply(Config config) {
        CircuitBreaker breaker = circuitBreakerRegistry.circuitBreaker(config.name);
        return (ServerWebExchange exchange,
                org.springframework.cloud.gateway.filter.GatewayFilterChain chain)
                -> chain.filter(exchange)
                        .transform(CircuitBreakerOperator.of(breaker))
                        .onErrorResume(t -> write503(exchange, breaker.getState()));
    }

    private static Mono<Void> write503(ServerWebExchange exchange,
                                       CircuitBreaker.State state) {
        byte[] body = ("{\"error\":\"upstream_unavailable\",\"edge\":\"circuit-open\","
                + "\"state\":\"" + state.name().toLowerCase() + "\"}")
                .getBytes(StandardCharsets.UTF_8);
        exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        exchange.getResponse().getHeaders().setContentType(MediaType.APPLICATION_JSON);
        exchange.getResponse().getHeaders().setContentLength(body.length);
        return exchange.getResponse()
                .writeWith(Mono.just(exchange.getResponse().bufferFactory().wrap(body)))
                .onErrorResume(t -> Mono.empty());
    }

    public static class Config {
        /** The resilience4j CircuitBreaker instance name (declared in YAML). */
        private String name = DEFAULT_INSTANCE;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }
}
