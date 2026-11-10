package dev.specproof.gateway.filter;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.config.GatewayProperties;
import reactor.core.publisher.Mono;

/**
 * The edge sets a small, fixed set of defensive response headers on every answer
 * it returns — including the answers it produces itself (a 503 from the circuit
 * breaker, a 502 from a dead upstream, the SPA's HTML).
 *
 * <p>Why a global filter and not a per-route one: the headers must appear on the
 * edge's OWN error responses, which never reach a route — they are emitted by
 * the circuit-breaker filter or the gateway's default error web handler. A
 * route-scoped filter would never see them. A global filter registers once and
 * covers the whole hop.
 *
 * <p>The set is deliberately conservative so it cannot break a product that is
 * simultaneously an API and an SPA (the catch-all serves the web UI):
 * <ul>
 *   <li>{@code X-Content-Type-Options: nosniff} — stop MIME sniffing.</li>
 *   <li>{@code X-Frame-Options: DENY} — the product is never framed.</li>
 *   <li>{@code Referrer-Policy: no-referrer} — do not leak paths off-site.</li>
 *   <li>{@code Cross-Origin-Opener-Policy: same-origin} — isolate the top-level
 *       document from cross-origin openers (a prereq for COEP later).</li>
 *   <li>{@code Strict-Transport-Security} — pin HTTPS. Only meaningful when the
 *       edge is reached over TLS; browsers ignore it on plain HTTP, so emitting
 *       it unconditionally from the edge is harmless and standard.</li>
 *   <li>{@code Permissions-Policy: geolocation=(), camera=(), microphone=(),
 *       payment=()} — the product needs none of these; deny them by default.</li>
 *   <li>{@code X-Permitted-Cross-Domain-Policies: none} — no Adobe cross-domain
 *       policy file is served.</li>
 * </ul>
 *
 * <p>Deliberately NOT set, and why:
 * <ul>
 *   <li>{@code Content-Security-Policy} — the catch-all route serves the SPA's
 *       HTML and assets, so a restrictive CSP would break the UI. CSP belongs on
 *       the SPA's own responses, not on a gateway that also proxies an API.</li>
 *   <li>{@code Cross-Origin-Resource-Policy} — set to {@code same-origin} it would
 *       block the SPA's own cross-origin asset loads; left unset rather than
 *       wrongly restrictive.</li>
 * </ul>
 *
 * <p>Order: {@link Ordered#HIGHEST_PRECEDENCE} plus a small offset, so the
 * headers are committed before any route filter runs — the same reasoning as
 * {@link EdgeRequestIdGlobalFilter}. They are written synchronously to the
 * response AND re-applied in {@code beforeCommit}, so a short-circuited response
 * (circuit-breaker 503) still carries them.
 */
@Component
public class EdgeSecurityHeadersGlobalFilter implements GlobalFilter, Ordered {

    /** Header name constants, exposed for tests and operators. */
    public static final String X_CONTENT_TYPE_OPTIONS = "X-Content-Type-Options";
    public static final String X_FRAME_OPTIONS = "X-Frame-Options";
    public static final String REFERRER_POLICY = "Referrer-Policy";
    public static final String CROSS_ORIGIN_OPENER_POLICY = "Cross-Origin-Opener-Policy";
    public static final String STRICT_TRANSPORT_SECURITY = "Strict-Transport-Security";
    public static final String PERMISSIONS_POLICY = "Permissions-Policy";
    public static final String X_PERMITTED_CROSS_DOMAIN_POLICIES = "X-Permitted-Cross-Domain-Policies";

    /** The values written for each header. */
    public static final String VALUE_NOSNIFF = "nosniff";
    public static final String VALUE_DENY = "DENY";
    public static final String VALUE_NO_REFERRER = "no-referrer";
    public static final String VALUE_SAME_ORIGIN = "same-origin";
    public static final String VALUE_HSTS = "max-age=31536000; includeSubDomains";
    public static final String VALUE_PERMISSIONS = "geolocation=(), camera=(), microphone=(), payment=()";
    public static final String VALUE_NO_CROSS_DOMAIN = "none";

    private final boolean enabled;

    /** Spring constructor — pulls the operator toggle from the externalized
     *  {@link GatewayProperties} bean (#1604) instead of @Value strings. */
    @Autowired
    public EdgeSecurityHeadersGlobalFilter(GatewayProperties props) {
        this(props.getSecurityHeaders().isEnabled());
    }

    /** Direct constructor used by tests and manual wiring. */
    public EdgeSecurityHeadersGlobalFilter(boolean enabled) {
        this.enabled = enabled;
    }

    /** No-arg constructor for direct construction (tests, manual wiring). */
    public EdgeSecurityHeadersGlobalFilter() {
        this(true);
    }

    @Override
    public int getOrder() {
        // After the request-id filter (+10) so both run near the front.
        return Ordered.HIGHEST_PRECEDENCE + 20;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        if (enabled) {
            // Synchronous write covers short-circuited responses (e.g. a breaker
            // 503) that commit before the chain returns to us.
            applyHeaders(exchange.getResponse().getHeaders());
            exchange.getResponse().beforeCommit(() -> {
                applyHeaders(exchange.getResponse().getHeaders());
                return Mono.empty();
            });
        }
        return chain.filter(exchange);
    }

    /** Writes the full defensive header set onto the given headers. */
    static void applyHeaders(HttpHeaders headers) {
        headers.set(X_CONTENT_TYPE_OPTIONS, VALUE_NOSNIFF);
        headers.set(X_FRAME_OPTIONS, VALUE_DENY);
        headers.set(REFERRER_POLICY, VALUE_NO_REFERRER);
        headers.set(CROSS_ORIGIN_OPENER_POLICY, VALUE_SAME_ORIGIN);
        headers.set(STRICT_TRANSPORT_SECURITY, VALUE_HSTS);
        headers.set(PERMISSIONS_POLICY, VALUE_PERMISSIONS);
        headers.set(X_PERMITTED_CROSS_DOMAIN_POLICIES, VALUE_NO_CROSS_DOMAIN);
    }

    /** Whether the filter is currently adding headers. */
    public boolean isEnabled() {
        return enabled;
    }
}
