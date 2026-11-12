package dev.specproof.gateway.filter;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.util.Map;
import java.util.Optional;

import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.http.server.reactive.ServerHttpResponseDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.cache.SingleFlightCache;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/**
 * The edge's opt-in RESPONSE CACHE (#1637, performance leg).
 *
 * <p>Combines the three ideas the brief asks for into one filter:
 * <b>single-flight coalescing</b> (concurrent identical GETs collapse to one
 * upstream call), a <b>bounded LRU</b> (memory is O(capacity), so a hot edge
 * cannot be driven OOM by its own cache — the hardware-adaptation knob), and a
 * <b>TTL</b> (never serve a value older than the operator's SLA window). The
 * coalescing + LRU live in {@link SingleFlightCache}; this filter is the wiring
 * that captures a 2xx GET response, stores it, and replays it on a hit.</p>
 *
 * <p>Activation is two-level and fail-open: the bean only exists when
 * {@code specproof.gateway.response-cache.enabled=true} (default off), AND a
 * route must opt in via metadata {@code cacheable: true} (and optionally
 * {@code cache-ttl: <seconds>}). A non-2xx response, a response larger than the
 * body cap, or any capture error degrades to a plain pass-through — the cache
 * never blocks the event loop and never fails a request it did not have to.</p>
 */
@Component
@ConditionalOnProperty(
        prefix = "specproof.gateway.response-cache",
        name = "enabled",
        havingValue = "true")
public class EdgeResponseCacheGatewayFilterFactory
        extends AbstractGatewayFilterFactory<EdgeResponseCacheGatewayFilterFactory.Config> {

    private static final int DEFAULT_CAPACITY = 1024;
    private static final long DEFAULT_TTL_SECONDS = 30;
    private static final int MAX_BODY_BYTES = 256 * 1024;

    private final SingleFlightCache<String, CachedResponse> cache;
    private final MeterRegistry meterRegistry;

    /** Production wiring: a default-bounded in-memory cache. */
    public EdgeResponseCacheGatewayFilterFactory(MeterRegistry meterRegistry) {
        super(Config.class);
        this.meterRegistry = meterRegistry;
        this.cache = new SingleFlightCache<>(DEFAULT_CAPACITY, DEFAULT_TTL_SECONDS * 1000L);
    }

    /** Test wiring: inject a cache (e.g. preloaded) without a broker. */
    EdgeResponseCacheGatewayFilterFactory(MeterRegistry meterRegistry,
                                          SingleFlightCache<String, CachedResponse> cache) {
        super(Config.class);
        this.meterRegistry = meterRegistry;
        this.cache = cache;
    }

    @Override
    public String name() {
        return "EdgeResponseCache";
    }

    @Override
    public GatewayFilter apply(Config config) {
        return (ServerWebExchange exchange, GatewayFilterChain chain) -> {
            if (!isCacheable(exchange)) {
                return chain.filter(exchange);
            }
            String key = cacheKey(exchange);
            Optional<CachedResponse> hit = cache.getIfPresent(key);
            if (hit.isPresent() && hit.get().cacheable) {
                return writeCached(exchange, hit.get());
            }
            long ttlMillis = ttlForRoute(exchange);
            // The loader runs the upstream ONCE; .cache() in SingleFlightCache
            // shares that single run across concurrent waiters, and the result
            // is stored (LRU + TTL) on completion.
            return cache.get(key, k -> fetchAndCapture(exchange, chain, ttlMillis)).then();
        };
    }

    private Mono<CachedResponse> fetchAndCapture(ServerWebExchange exchange, GatewayFilterChain chain,
                                                long ttlMillis) {
        ServerHttpResponse original = exchange.getResponse();
        CapturingResponse capturing = new CapturingResponse(original);
        ServerWebExchange mutated = exchange.mutate().response(capturing).build();
        return chain.filter(mutated).then(Mono.defer(() -> {
            HttpStatusCode status = capturing.getStatusCode();
            boolean ok = status != null && status.is2xxSuccessful();
            if (!ok || capturing.body().length > MAX_BODY_BYTES) {
                return Mono.just(CachedResponse.NON_CACHEABLE);
            }
            return Mono.just(new CachedResponse(status, new HttpHeaders(capturing.getHeaders()),
                    capturing.body(), true));
        }));
    }

    private static Mono<Void> writeCached(ServerWebExchange exchange, CachedResponse cr) {
        if (!cr.cacheable) {
            return exchange.getResponse().setComplete();
        }
        ServerHttpResponse resp = exchange.getResponse();
        resp.setStatusCode(cr.status);
        HttpHeaders headers = resp.getHeaders();
        cr.headers.forEach((name, values) -> {
            if (shouldSkipHeader(name)) {
                return;
            }
            for (String v : values) {
                headers.add(name, v);
            }
        });
        byte[] body = cr.body;
        headers.setContentLength(body.length);
        if (!headers.containsKey(HttpHeaders.CONTENT_TYPE)) {
            headers.setContentType(MediaType.APPLICATION_JSON);
        }
        return resp.writeWith(Mono.just(resp.bufferFactory().wrap(body)));
    }

    private static boolean shouldSkipHeader(String name) {
        return HttpHeaders.CONTENT_LENGTH.equalsIgnoreCase(name)
                || HttpHeaders.TRANSFER_ENCODING.equalsIgnoreCase(name);
    }

    private static boolean isCacheable(ServerWebExchange exchange) {
        if (exchange.getRequest().getMethod() == null
                || !"GET".equalsIgnoreCase(exchange.getRequest().getMethod().name())) {
            return false;
        }
        return routeMetadata(exchange, "cacheable").map("true"::equalsIgnoreCase).orElse(false);
    }

    private static String cacheKey(ServerWebExchange exchange) {
        String path = exchange.getRequest().getPath().toString();
        String query = exchange.getRequest().getURI().getRawQuery();
        return query == null ? path : path + "?" + query;
    }

    private long ttlForRoute(ServerWebExchange exchange) {
        return routeMetadata(exchange, "cache-ttl")
                .map(s -> {
                    try {
                        return Long.parseLong(s);
                    } catch (NumberFormatException e) {
                        return DEFAULT_TTL_SECONDS;
                    }
                })
                .orElse(DEFAULT_TTL_SECONDS) * 1000L;
    }

    private static Optional<String> routeMetadata(ServerWebExchange exchange, String key) {
        Route route = exchange.getAttribute(ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
        if (route == null) {
            return Optional.empty();
        }
        Map<String, Object> meta = route.getMetadata();
        if (meta == null) {
            return Optional.empty();
        }
        Object value = meta.get(key);
        return value == null ? Optional.empty() : Optional.of(value.toString());
    }

    /** A captured, replayable response. {@link #NON_CACHEABLE} is a sentinel for
     *  responses we deliberately refuse to keep (errors, oversized). Package-private
     *  so the filter's own tests can name it as the SingleFlightCache value type. */
    static final class CachedResponse {
        static final CachedResponse NON_CACHEABLE =
                new CachedResponse(null, new HttpHeaders(), new byte[0], false);

        private final HttpStatusCode status;
        private final HttpHeaders headers;
        private final byte[] body;
        private final boolean cacheable;

        CachedResponse(HttpStatusCode status, HttpHeaders headers, byte[] body, boolean cacheable) {
            this.status = status;
            this.headers = headers;
            this.body = body;
            this.cacheable = cacheable;
        }
    }

    /** Tees the response body into a byte sink while still writing through to the
     *  real client. {@code asByteBuffer()} copies without advancing the buffer's
     *  reader index, so the downstream write sees an intact buffer. */
    private static final class CapturingResponse extends ServerHttpResponseDecorator {
        private final ByteArrayOutputStream sink = new ByteArrayOutputStream();

        CapturingResponse(ServerHttpResponse delegate) {
            super(delegate);
        }

        byte[] body() {
            return sink.toByteArray();
        }

        @Override
        public Mono<Void> writeWith(org.reactivestreams.Publisher<? extends DataBuffer> body) {
            return DataBufferUtils.join(Flux.from(body).doOnNext(this::copy))
                    .flatMap(buf -> super.writeWith(Mono.just(buf)));
        }

        @Override
        public Mono<Void> writeAndFlushWith(
                org.reactivestreams.Publisher<? extends org.reactivestreams.Publisher<? extends DataBuffer>> body) {
            Flux<DataBuffer> all = Flux.from(body).flatMap(Flux::from);
            return writeWith(all);
        }

        private void copy(DataBuffer b) {
            ByteBuffer bb = b.asByteBuffer();
            byte[] bytes = new byte[bb.remaining()];
            bb.get(bytes);
            sink.write(bytes, 0, bytes.length);
        }
    }

    public static class Config {
    }
}
