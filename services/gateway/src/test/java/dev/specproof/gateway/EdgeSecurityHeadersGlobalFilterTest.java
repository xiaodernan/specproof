package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.filter.EdgeSecurityHeadersGlobalFilter;

import reactor.core.publisher.Mono;

/**
 * The edge's security-header contract, tested without any live upstream.
 *
 * <p>Two claims are pinned here:
 * <ul>
 *   <li>when enabled, the full defensive header set is present on the response;</li>
 *   <li>when disabled (operator toggle), none of the edge's headers are added.</li>
 * </ul>
 */
class EdgeSecurityHeadersGlobalFilterTest {

    private static ServerWebExchange exchange() {
        MockServerHttpRequest request = MockServerHttpRequest.get("http://edge.test/x").build();
        return MockServerWebExchange.builder(request).build();
    }

    private static HttpHeaders responseHeadersOf(ServerWebExchange exchange) {
        new EdgeSecurityHeadersGlobalFilter()
                .filter(exchange, ex -> Mono.empty())
                .block();
        return exchange.getResponse().getHeaders();
    }

    @Test
    void theFullDefensiveHeaderSetIsPresentWhenEnabled() {
        HttpHeaders headers = responseHeadersOf(exchange());

        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.X_CONTENT_TYPE_OPTIONS))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_NOSNIFF);
        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.X_FRAME_OPTIONS))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_DENY);
        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.REFERRER_POLICY))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_NO_REFERRER);
        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.CROSS_ORIGIN_OPENER_POLICY))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_SAME_ORIGIN);
        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.STRICT_TRANSPORT_SECURITY))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_HSTS);
        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.PERMISSIONS_POLICY))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_PERMISSIONS);
        assertThat(headers.getFirst(EdgeSecurityHeadersGlobalFilter.X_PERMITTED_CROSS_DOMAIN_POLICIES))
                .isEqualTo(EdgeSecurityHeadersGlobalFilter.VALUE_NO_CROSS_DOMAIN);
    }

    @Test
    void noEdgeSecurityHeadersAreAddedWhenDisabled() {
        ServerWebExchange exchange = exchange();
        new EdgeSecurityHeadersGlobalFilter(false)
                .filter(exchange, ex -> Mono.empty())
                .block();

        HttpHeaders headers = exchange.getResponse().getHeaders();
        assertThat(headers).doesNotContainKey(EdgeSecurityHeadersGlobalFilter.X_CONTENT_TYPE_OPTIONS);
        assertThat(headers).doesNotContainKey(EdgeSecurityHeadersGlobalFilter.X_FRAME_OPTIONS);
        assertThat(headers).doesNotContainKey(EdgeSecurityHeadersGlobalFilter.STRICT_TRANSPORT_SECURITY);
        assertThat(headers).doesNotContainKey(EdgeSecurityHeadersGlobalFilter.PERMISSIONS_POLICY);
    }

    @Test
    void theFilterIsEnabledByDefault() {
        assertThat(new EdgeSecurityHeadersGlobalFilter().isEnabled()).isTrue();
    }
}
