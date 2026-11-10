package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.filter.EdgeCircuitBreakerGatewayFilterFactory;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import reactor.core.publisher.Mono;

/**
 * The edge's circuit breaker behavior, tested without any live upstream.
 *
 * <p>Both tests drive the production {@link EdgeCircuitBreakerGatewayFilterFactory}
 * directly; the thresholds match the production {@code application.yml}
 * resilience4j wiring (sliding window 10, minimum calls 5, failure rate 50) —
 * but never re-typed from it implicitly: this file declares its own registry
 * and asserts behavior, not configuration parity of the YAML.
 */
class EdgeCircuitBreakerGatewayFilterFactoryTest {

    private static CircuitBreakerRegistry freshRegistry() {
        return CircuitBreakerRegistry.of(CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .permittedNumberOfCallsInHalfOpenState(3)
                .automaticTransitionFromOpenToHalfOpenEnabled(true)
                .build());
    }

    private static ServerWebExchange newExchange() {
        MockServerHttpRequest request = MockServerHttpRequest
                .get("http://edge.test/anything")
                .build();
        return MockServerWebExchange.builder(request).build();
    }

    private static GatewayFilterChain failingChain(AtomicInteger upstreamCalls) {
        // The upstream call is the subscription, not the composition — count it
        // lazily, or the breaker's short-circuit would be measured as still-open access.
        return exchange -> Mono.defer(() -> {
            upstreamCalls.incrementAndGet();
            return Mono.error(new RuntimeException("upstream down"));
        });
    }

    @Test
    void theBreakerOpensAfterTheConfiguredFailureRate() {
        CircuitBreakerRegistry registry = freshRegistry();
        EdgeCircuitBreakerGatewayFilterFactory factory =
                new EdgeCircuitBreakerGatewayFilterFactory(registry);
        GatewayFilter filter = factory.apply(new EdgeCircuitBreakerGatewayFilterFactory.Config());

        AtomicInteger upstreamCalls = new AtomicInteger();
        for (int i = 0; i < 5; i++) {
            ServerWebExchange exchange = newExchange();
            filter.filter(exchange, failingChain(upstreamCalls)).block();
            assertThat(exchange.getResponse().getStatusCode())
                    .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        }

        CircuitBreaker cb = registry.circuitBreaker("specproof-edge");
        assertThat(cb.getState()).isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(upstreamCalls.get()).isEqualTo(5);
    }

    @Test
    void anOpenBreakerShortCircuitsWithoutTouchingTheUpstream() {
        CircuitBreakerRegistry registry = freshRegistry();
        EdgeCircuitBreakerGatewayFilterFactory factory =
                new EdgeCircuitBreakerGatewayFilterFactory(registry);
        GatewayFilter filter = factory.apply(new EdgeCircuitBreakerGatewayFilterFactory.Config());
        registry.circuitBreaker("specproof-edge").transitionToOpenState();

        AtomicInteger upstreamCalls = new AtomicInteger();
        ServerWebExchange exchange = newExchange();
        filter.filter(exchange, failingChain(upstreamCalls)).block();

        assertThat(upstreamCalls.get()).isZero();
        assertThat(exchange.getResponse().getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
    }
}
