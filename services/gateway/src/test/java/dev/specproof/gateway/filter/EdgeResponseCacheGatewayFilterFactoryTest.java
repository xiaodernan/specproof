package dev.specproof.gateway.filter;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.http.server.reactive.MockServerHttpResponse;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.cache.SingleFlightCache;

import reactor.core.publisher.Mono;

/**
 * The edge response cache, measured end-to-end: a MISS must capture the upstream
 * body and serve it, a subsequent identical GET must be served from the cache
 * WITHOUT calling the upstream again (single-flight + LRU working together), and
 * a non-cacheable request must pass straight through.
 */
class EdgeResponseCacheGatewayFilterFactoryTest {

    private static final String BODY = "hello-cache";

    private static ServerWebExchange cacheableGet(String path) {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(MockServerHttpRequest.get(path).build());
        // Spring Cloud Gateway refuses to build a route without a predicate
        // ("predicate must not be null"). The ASYNC builder is the one that
        // takes a plain predicate; this one matches everything: the route
        // table's own predicates are not what this file measures.
        Route route = Route.async()
                .id("cp")
                .uri(URI.create("http://control-plane:8081"))
                .predicate(candidate -> true)
                .metadata("cacheable", "true")
                .build();
        exchange.getAttributes().put(ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR, route);
        return exchange;
    }

    /**
     * The bytes the client actually received.
     *
     * <p>Spring 6.2 changed {@code MockServerHttpResponse.getBodyAsString()} to
     * return a {@code Mono<String>} (it used to return the string). Comparing
     * that Mono to a string is how this file first failed: the assertion read
     * {@code "MonoDefaultIfEmpty"} and the test said the body was empty when
     * the body was fine.</p>
     */
    private static String bodyOf(ServerWebExchange exchange) {
        String body = ((MockServerHttpResponse) exchange.getResponse())
                .getBodyAsString().block();
        return body == null ? "" : body;
    }

    private EdgeResponseCacheGatewayFilterFactory factoryWith(
            SingleFlightCache<String, EdgeResponseCacheGatewayFilterFactory.CachedResponse> cache) {
        return new EdgeResponseCacheGatewayFilterFactory(new SimpleMeterRegistry(), cache);
    }

    @Test
    void secondIdenticalGetIsServedFromCacheWithoutHittingUpstream() {
        AtomicInteger upstreamCalls = new AtomicInteger();
        var cache = new SingleFlightCache<String, EdgeResponseCacheGatewayFilterFactory.CachedResponse>(16, 30_000L);
        GatewayFilter filter = factoryWith(cache).apply(new EdgeResponseCacheGatewayFilterFactory.Config());

        GatewayFilterChain chain = (ServerWebExchange e) -> {
            upstreamCalls.incrementAndGet();
            var r = e.getResponse();
            r.setStatusCode(HttpStatus.OK);
            r.getHeaders().setContentType(MediaType.TEXT_PLAIN);
            return r.writeWith(Mono.just(r.bufferFactory().wrap(BODY.getBytes())));
        };

        // First call: MISS -> upstream runs, body captured AND delivered.
        ServerWebExchange first = cacheableGet("/api/v1/tenants");
        filter.filter(first, chain).block();
        assertThat(bodyOf(first)).isEqualTo(BODY);

        // Second call: HIT -> upstream NOT called again.
        ServerWebExchange second = cacheableGet("/api/v1/tenants");
        filter.filter(second, chain).block();
        assertThat(bodyOf(second)).isEqualTo(BODY);

        assertThat(upstreamCalls.get()).isEqualTo(1);
    }

    @Test
    void nonCacheableRequestPassesThroughAndIsNeverCached() {
        AtomicInteger upstreamCalls = new AtomicInteger();
        var cache = new SingleFlightCache<String, EdgeResponseCacheGatewayFilterFactory.CachedResponse>(16, 30_000L);
        GatewayFilter filter = factoryWith(cache).apply(new EdgeResponseCacheGatewayFilterFactory.Config());

        GatewayFilterChain chain = (ServerWebExchange e) -> {
            upstreamCalls.incrementAndGet();
            var r = e.getResponse();
            r.setStatusCode(HttpStatus.OK);
            return r.writeWith(Mono.just(r.bufferFactory().wrap(BODY.getBytes())));
        };

        // No route metadata -> not cacheable -> upstream called every time.
        ServerWebExchange a = MockServerWebExchange.from(MockServerHttpRequest.get("/api/v1/tenants").build());
        ServerWebExchange b = MockServerWebExchange.from(MockServerHttpRequest.get("/api/v1/tenants").build());
        filter.filter(a, chain).block();
        filter.filter(b, chain).block();
        assertThat(upstreamCalls.get()).isEqualTo(2);
    }
}
