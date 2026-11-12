package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.filter.EdgeDistributedRateLimiterGatewayFilterFactory;
import dev.specproof.gateway.filter.EdgeRequestIdGlobalFilter;
import dev.specproof.gateway.ratelimit.RateLimitResult;
import dev.specproof.gateway.ratelimit.TokenBucketScript;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import reactor.core.publisher.Mono;

/**
 * The edge's distributed rate limiter, driven end-to-end through the production
 * filter factory with a mocked Redis transport. The Lua script's math is asserted
 * elsewhere; here the contract is the edge's own 429: it must carry the request
 * id and a {@code Retry-After}, admit when the bucket says yes, and never touch
 * the upstream when it says no.
 */
class EdgeDistributedRateLimiterGatewayFilterFactoryTest {

    private final TokenBucketScript script = mock(TokenBucketScript.class);

    private static EdgeDistributedRateLimiterGatewayFilterFactory.Config config() {
        EdgeDistributedRateLimiterGatewayFilterFactory.Config c =
                new EdgeDistributedRateLimiterGatewayFilterFactory.Config();
        c.setName("specproof-edge-distributed-test");
        c.setCapacity(100);
        c.setRefillPerSecond(50);
        c.setKeyStrategy("global");
        c.setFailMode("open");
        return c;
    }

    private static ServerWebExchange newExchange() {
        MockServerHttpRequest request = MockServerHttpRequest.get("http://edge.test/api/v1/anything").build();
        return MockServerWebExchange.builder(request).build();
    }

    private static GatewayFilterChain okChain(AtomicInteger upstreamCalls) {
        return exchange -> {
            upstreamCalls.incrementAndGet();
            exchange.getResponse().setStatusCode(HttpStatus.OK);
            return exchange.getResponse().setComplete();
        };
    }

    @Test
    void aBucketWithCapacityAdmitsTheRequest() {
        when(script.run(anyString(), anyLong(), anyDouble(), anyLong()))
                .thenReturn(Mono.just(new RateLimitResult(true, 99L, 0L)));
        EdgeDistributedRateLimiterGatewayFilterFactory factory =
                new EdgeDistributedRateLimiterGatewayFilterFactory(script, new SimpleMeterRegistry());
        GatewayFilter filter = factory.apply(config());

        AtomicInteger upstreamCalls = new AtomicInteger();
        ServerWebExchange exchange = newExchange();
        new EdgeRequestIdGlobalFilter()
                .filter(exchange, mutated -> filter.filter(mutated, okChain(upstreamCalls)))
                .block();

        assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(upstreamCalls.get()).isEqualTo(1);
    }

    @Test
    void anExhaustedBucketAnswers429WithRetryAfterAndRequestId() {
        when(script.run(anyString(), anyLong(), anyDouble(), anyLong()))
                .thenReturn(Mono.just(new RateLimitResult(false, 0L, 20L)));
        EdgeDistributedRateLimiterGatewayFilterFactory factory =
                new EdgeDistributedRateLimiterGatewayFilterFactory(script, new SimpleMeterRegistry());
        GatewayFilter filter = factory.apply(config());

        AtomicInteger upstreamCalls = new AtomicInteger();
        ServerWebExchange exchange = newExchange();
        new EdgeRequestIdGlobalFilter()
                .filter(exchange, mutated -> filter.filter(mutated, okChain(upstreamCalls)))
                .block();

        assertThat(upstreamCalls.get()).isEqualTo(0);
        assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.TOO_MANY_REQUESTS);
        assertThat(exchange.getResponse().getHeaders().getFirst("Retry-After")).isEqualTo("20");
        String body = ((MockServerHttpResponse) exchange.getResponse()).getBodyAsString().block();
        assertThat(body).contains("\"rate_limited\"");
        assertThat(body).contains("\"remaining\":0");
        assertThat(body).containsPattern("\"request_id\":\"[0-9a-f]{16}\"");
    }

    @Test
    void xForwardedForKeyingDoesNotCrashAndStillAdmits() {
        when(script.run(anyString(), anyLong(), anyDouble(), anyLong()))
                .thenReturn(Mono.just(new RateLimitResult(true, 99L, 0L)));
        EdgeDistributedRateLimiterGatewayFilterFactory.Config c = config();
        c.setKeyStrategy("x-forwarded-for");
        EdgeDistributedRateLimiterGatewayFilterFactory factory =
                new EdgeDistributedRateLimiterGatewayFilterFactory(script, new SimpleMeterRegistry());
        GatewayFilter filter = factory.apply(c);

        AtomicInteger upstreamCalls = new AtomicInteger();
        MockServerHttpRequest request = MockServerHttpRequest.get("http://edge.test/api/v1/anything")
                .header("X-Forwarded-For", "203.0.113.7, 10.0.0.1").build();
        ServerWebExchange exchange = MockServerWebExchange.builder(request).build();
        new EdgeRequestIdGlobalFilter()
                .filter(exchange, mutated -> filter.filter(mutated, okChain(upstreamCalls)))
                .block();

        assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(upstreamCalls.get()).isEqualTo(1);
    }
}
