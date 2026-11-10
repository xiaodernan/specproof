package dev.specproof.gateway.filter;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.config.GatewayProperties;
import reactor.core.publisher.Mono;

/**
 * The edge rejects a request whose declared body is larger than the operator's cap
 * before it spends a single byte proxying it upstream — a 10 MiB POST should not
 * tie up the agent runtime or the control plane just to discover it is too big.
 *
 * <p>Why a global filter: the cap must apply to every route, including the ones
 * that are not the catch-all (the control-plane's POST endpoints). A route-scoped
 * {@code RequestSize} filter would have to be repeated on each route; a global one
 * is declared once.
 *
 * <p>How it measures: on the {@code Content-Length} request header, which a sane
 * client sends before streaming. The response is a {@code 413 PAYLOAD_TOO_LARGE},
 * and the request never reaches the chain — so the upstream is never touched. The
 * request-id and security-header filters (which run earlier) still stamp the 413,
 * because their {@code beforeCommit} hooks fire when this filter completes it.
 *
 * <p>Honest boundary: a body sent with {@code Transfer-Encoding: chunked} and no
 * {@code Content-Length} reports {@code -1} here, and is NOT capped — the edge
 * cannot know its size without consuming it, and consuming-then-discarding is
 * worse than letting the upstream's own limit decide. The cap is a cheap first
 * line of defense for the common, well-behaved case, not a substitute for the
 * upstream's own payload limits.
 */
@Component
public class EdgeRequestSizeGlobalFilter implements GlobalFilter, Ordered {

    /** Config key: the declared-body cap in bytes. */
    public static final String MAX_BYTES_PROPERTY = "specproof.gateway.request-size.max-bytes";

    /** Default cap: 10 MiB. Generous enough for job specs and SPA assets. */
    public static final long DEFAULT_MAX_BYTES = 10L * 1024 * 1024;

    /** The status written when the declared size exceeds the cap. */
    public static final HttpStatus REJECTED_STATUS = HttpStatus.PAYLOAD_TOO_LARGE;

    private final boolean enabled;
    private final long maxBytes;

    /** Spring constructor — pulls the operator toggles from the externalized
     *  {@link GatewayProperties} bean (#1604) instead of @Value strings. */
    @Autowired
    public EdgeRequestSizeGlobalFilter(GatewayProperties props) {
        this(props.getRequestSize().isEnabled(), props.getRequestSize().getMaxBytes());
    }

    /** Direct constructor used by tests and manual wiring. */
    public EdgeRequestSizeGlobalFilter(boolean enabled, long maxBytes) {
        this.enabled = enabled;
        this.maxBytes = maxBytes;
    }

    /** No-arg constructor for direct construction (tests, manual wiring). */
    public EdgeRequestSizeGlobalFilter() {
        this(true, DEFAULT_MAX_BYTES);
    }

    @Override
    public int getOrder() {
        // After the request-id (+10) and security-headers (+20) filters so a
        // rejected request still carries those headers.
        return Ordered.HIGHEST_PRECEDENCE + 30;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        if (!enabled) {
            return chain.filter(exchange);
        }
        long declared = exchange.getRequest().getHeaders().getContentLength();
        // -1 = unknown size (chunked, no Content-Length): not capped here.
        if (declared > maxBytes) {
            exchange.getResponse().setStatusCode(REJECTED_STATUS);
            return exchange.getResponse().setComplete();
        }
        return chain.filter(exchange);
    }

    /** Whether the filter is currently capping requests. */
    public boolean isEnabled() {
        return enabled;
    }

    /** The current cap, in bytes. */
    public long getMaxBytes() {
        return maxBytes;
    }
}
