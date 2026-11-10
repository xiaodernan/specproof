package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.filter.EdgeCircuitBreakerGatewayFilterFactory;
import dev.specproof.gateway.filter.EdgeRequestIdGlobalFilter;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import reactor.core.publisher.Mono;

/**
 * The edge's request-id contract, tested without any live upstream.
 *
 * <p>Two claims are pinned here, and both are about the edge answering
 * <em>itself</em>:
 * <ul>
 *   <li>an inbound {@code X-Request-ID} is kept as-is (the caller correlates its
 *       own logs; the edge does not rewrite it);</li>
 *   <li>a missing one becomes 16 lowercase hex characters — the agent
 *       runtime's own shape — and it reaches both the upstream request and the
 *       response, so the operator and the upstream log agree.</li>
 * </ul>
 */
class EdgeRequestIdGlobalFilterTest {

    private static ServerWebExchange exchange(String headerValue) {
        MockServerHttpRequest.BaseBuilder<?> request = MockServerHttpRequest.get("http://edge.test/x");
        if (headerValue != null) {
            request.header(EdgeRequestIdGlobalFilter.HEADER, headerValue);
        }
        return MockServerWebExchange.builder(request.build()).build();
    }

    private static String requestIdOf(ServerWebExchange exchange) {
        return exchange.getRequest().getHeaders().getFirst(EdgeRequestIdGlobalFilter.HEADER);
    }

    @Test
    void anInboundRequestIdIsKeptAsIs() {
        ServerWebExchange exchange = exchange("caller-supplied-id");
        new EdgeRequestIdGlobalFilter()
                .filter(exchange, ex -> {
                    assertThat(requestIdOf(ex)).isEqualTo("caller-supplied-id");
                    return Mono.empty();
                })
                .block();

        assertThat(exchange.getResponse().getHeaders()
                .getFirst(EdgeRequestIdGlobalFilter.HEADER)).isEqualTo("caller-supplied-id");
    }

    @Test
    void aMissingRequestIdBecomesSixteenHexCharacters() {
        ServerWebExchange exchange = exchange(null);
        new EdgeRequestIdGlobalFilter()
                .filter(exchange, ex -> {
                    String id = requestIdOf(ex);
                    assertThat(id).isNotNull();
                    assertThat(id).hasSize(16);
                    assertThat(id).matches("[0-9a-f]{16}");
                    return Mono.empty();
                })
                .block();

        assertThat(exchange.getResponse().getHeaders()
                .getFirst(EdgeRequestIdGlobalFilter.HEADER)).matches("[0-9a-f]{16}");
    }

    @Test
    void theEdgesOwnErrorCarriesTheRequestId() {
        CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .build());
        EdgeCircuitBreakerGatewayFilterFactory factory =
                new EdgeCircuitBreakerGatewayFilterFactory(registry);

        ServerWebExchange exchange = exchange("edge-owned-id");
        // The global filter runs first (higher precedence), so the breaker sees
        // the id the same way it does in production.
        new EdgeRequestIdGlobalFilter()
                .filter(exchange, ex -> factory.apply(new EdgeCircuitBreakerGatewayFilterFactory.Config())
                        .filter(ex, chained -> Mono.error(new RuntimeException("upstream down"))))
                .block();

        assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(exchange.getResponse()).isInstanceOf(MockServerHttpResponse.class);
        String body = ((MockServerHttpResponse) exchange.getResponse()).getBodyAsString().block();
        assertThat(body).contains("\"request_id\":\"edge-owned-id\"");
    }
}
