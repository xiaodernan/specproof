package dev.specproof.gateway.filter;

import java.util.UUID;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpRequestDecorator;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ServerWebExchangeDecorator;

import reactor.core.publisher.Mono;

/**
 * The edge mints the request id when nobody else did, and keeps one id for the
 * whole hop.
 *
 * <p>Why the edge owns this: the agent runtime already reads {@code X-Request-ID}
 * and generates a 16-hex id when the request has none (see
 * {@code api/middleware.py::RequestIDMiddleware}). But the edge answers some
 * requests <em>itself</em> — a 503 from the circuit breaker, a 502 from a dead
 * upstream — and those answers reached the operator with no id at all: nothing
 * to quote, nothing to grep the upstream logs for. The id the edge mints here
 * is forwarded upstream, so the agent runtime's structured logs and the
 * operator's error page carry the same value.
 *
 * <p>Contract (the same shape as the agent runtime's):
 * <ul>
 *   <li>header name {@code X-Request-ID};</li>
 *   <li>an inbound id is <strong>kept as-is</strong> — the edge never rewrites
 *       an id it was given, because the caller is correlating its own logs;</li>
 *   <li>a missing id becomes 16 lowercase hex characters, the agent runtime's
 *       own shape ({@code uuid4().hex[:16]}), so both planes produce ids a
 *       reader cannot tell apart;</li>
 *   <li>the id is echoed on the response, including on the edge's own errors.</li>
 * </ul>
 *
 * <p>Order: {@link Ordered#HIGHEST_PRECEDENCE} plus a small offset, so the id
 * exists before any route filter runs — the circuit breaker reads it to put it
 * in its 503 body.
 *
 * <p>The request is wrapped in a decorator rather than rebuilt through
 * {@code exchange.mutate()}: the decorator keeps the original exchange's
 * attributes (so the circuit breaker reads the same id) and works on every
 * exchange implementation, including the test doubles.
 */
@Component
public class EdgeRequestIdGlobalFilter implements GlobalFilter, Ordered {

    /** The header both planes use. */
    public static final String HEADER = "X-Request-ID";

    /** The exchange attribute the id is stored under. */
    public static final String ATTRIBUTE = "edge.request_id";

    /** The length of a generated id: the agent runtime's shape. */
    private static final int ID_LENGTH = 16;

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 10;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String inbound = exchange.getRequest().getHeaders().getFirst(HEADER);
        String requestId = (inbound == null || inbound.isBlank())
                ? newRequestId()
                : inbound.trim();

        // The attribute lives on the ORIGINAL exchange, so every later filter
        // reads the same id even though the request is a decorator.
        exchange.getAttributes().put(ATTRIBUTE, requestId);

        // The upstream must see the id …
        ServerHttpRequest decoratedRequest = new ServerHttpRequestDecorator(exchange.getRequest()) {
            @Override
            public HttpHeaders getHeaders() {
                HttpHeaders headers = new HttpHeaders();
                headers.putAll(super.getHeaders());
                headers.set(HEADER, requestId);
                return headers;
            }
        };

        // … and the response must carry it back, including when the edge
        // answers without the upstream ever being reached.
        exchange.getResponse().getHeaders().set(HEADER, requestId);
        exchange.getResponse().beforeCommit(() -> {
            exchange.getResponse().getHeaders().set(HEADER, requestId);
            return Mono.empty();
        });

        ServerWebExchange mutated = new ServerWebExchangeDecorator(exchange) {
            @Override
            public ServerHttpRequest getRequest() {
                return decoratedRequest;
            }
        };
        return chain.filter(mutated);
    }

    /** A fresh id, in the agent runtime's shape. */
    static String newRequestId() {
        String hex = UUID.randomUUID().toString().replace("-", "");
        return hex.substring(0, ID_LENGTH);
    }

    /** The id of this exchange, if the filter has run on it. */
    public static String requestIdOf(ServerWebExchange exchange) {
        Object value = exchange.getAttributes().get(ATTRIBUTE);
        return value == null ? null : String.valueOf(value);
    }
}
