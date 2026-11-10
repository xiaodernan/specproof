package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.ServerWebExchange;

import dev.specproof.gateway.filter.EdgeRequestSizeGlobalFilter;

import reactor.core.publisher.Mono;

/**
 * The edge's request-size cap, tested without any live upstream.
 *
 * <p>Claims pinned here:
 * <ul>
 *   <li>an oversized declared body is rejected with 413 and the chain is never called;</li>
 *   <li>a body under the cap passes through to the chain;</li>
 *   <li>an unknown size (no {@code Content-Length}) passes through — the edge does
 *       not consume-and-discard chunked bodies;</li>
 *   <li>when disabled, even an oversized body passes through.</li>
 * </ul>
 */
class EdgeRequestSizeGlobalFilterTest {

    private static final long SMALL_CAP = 1024;

    private static ServerWebExchange exchangeWithContentLength(Long contentLength) {
        MockServerHttpRequest.BaseBuilder<?> request = MockServerHttpRequest.post("http://edge.test/x");
        if (contentLength != null) {
            request.header("Content-Length", Long.toString(contentLength));
        }
        return MockServerWebExchange.builder(request.build()).build();
    }

    private static final class RecordingChain implements org.springframework.cloud.gateway.filter.GatewayFilterChain {
        final AtomicBoolean called = new AtomicBoolean(false);

        @Override
        public Mono<Void> filter(ServerWebExchange exchange) {
            called.set(true);
            return Mono.empty();
        }
    }

    @Test
    void oversizedDeclaredBodyIsRejectedWith413AndChainIsSkipped() {
        EdgeRequestSizeGlobalFilter filter = new EdgeRequestSizeGlobalFilter(true, SMALL_CAP);
        RecordingChain chain = new RecordingChain();
        ServerWebExchange exchange = exchangeWithContentLength(999_999L);

        filter.filter(exchange, chain).block();

        assertThat(chain.called).isFalse();
        assertThat(exchange.getResponse().getStatusCode()).isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE);
    }

    @Test
    void bodyUnderCapPassesThroughToTheChain() {
        EdgeRequestSizeGlobalFilter filter = new EdgeRequestSizeGlobalFilter(true, SMALL_CAP);
        RecordingChain chain = new RecordingChain();

        filter.filter(exchangeWithContentLength(100L), chain).block();

        assertThat(chain.called).isTrue();
    }

    @Test
    void unknownSizePassesThroughAndIsNotConsumed() {
        EdgeRequestSizeGlobalFilter filter = new EdgeRequestSizeGlobalFilter(true, SMALL_CAP);
        RecordingChain chain = new RecordingChain();

        // No Content-Length header at all (simulates chunked upload).
        filter.filter(exchangeWithContentLength(null), chain).block();

        assertThat(chain.called).isTrue();
    }

    @Test
    void disabledFilterDoesNotRejectOversizedBodies() {
        EdgeRequestSizeGlobalFilter filter = new EdgeRequestSizeGlobalFilter(false, SMALL_CAP);
        RecordingChain chain = new RecordingChain();

        filter.filter(exchangeWithContentLength(999_999L), chain).block();

        assertThat(chain.called).isTrue();
    }

    @Test
    void theFilterIsEnabledByDefaultWithTheTenMiBCap() {
        EdgeRequestSizeGlobalFilter filter = new EdgeRequestSizeGlobalFilter();
        assertThat(filter.isEnabled()).isTrue();
        assertThat(filter.getMaxBytes()).isEqualTo(10L * 1024 * 1024);
    }
}
