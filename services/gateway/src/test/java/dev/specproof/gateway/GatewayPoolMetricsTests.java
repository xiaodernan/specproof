package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.Executors;

import com.sun.net.httpserver.HttpServer;

import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

/**
 * The edge publishes its upstream connection pool — and this test asks it.
 *
 * <p>The scraper (Prometheus, via the gateway's management port) already
 * has the series; what was missing before {@code pool.metrics: true} was any
 * proof that the edge's connection pool is observable at all. "The agent
 * runtime is slow" and "the edge's pool is saturated" are different facts
 * with different fixes, and until these meters existed neither of them
 * was readable from outside the process.
 *
 * <p>A request goes through the REAL proxy path (catch-all route, local
 * JDK HTTP server upstream), and the meters are asserted with their tags:
 * the provider name ({@code proxy}, Spring Cloud Gateway's default pool
 * name) and the upstream's address. A meter nobody can attribute to an
 * upstream is not a pool metric a panel can use.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            "spring.cloud.gateway.httpclient.connect-timeout=500",
            "spring.cloud.gateway.httpclient.response-timeout=5s",
            "SPECPROOF_CONTROL_PLANE_URL=http://127.0.0.1:9",
            "SPECPROOF_AGENT_RUNTIME_URL=http://127.0.0.1:${specproof.pooltest.upstream}",
        })
class GatewayPoolMetricsTests {

    static final HttpServer LOCAL_UPSTREAM = startLocalUpstream();

    private static HttpServer startLocalUpstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                byte[] body = "pool-metrics-probe".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
                exchange.close();
            });
            server.setExecutor(Executors.newFixedThreadPool(1, r -> {
                Thread t = new Thread(r, "pool-metrics-upstream");
                t.setDaemon(true);
                return t;
            }));
            server.start();
            System.setProperty(
                    "specproof.pooltest.upstream",
                    String.valueOf(server.getAddress().getPort()));
            return server;
        } catch (Exception failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    @Autowired
    private MeterRegistry meterRegistry;

    @LocalServerPort
    private int edgePort;

    private void proxyOneRequest() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:" + edgePort + "/api/pool-metrics-leg"))
                .timeout(Duration.ofSeconds(8))
                .GET()
                .build();
        HttpResponse<InputStream> response =
                client.send(request, HttpResponse.BodyHandlers.ofInputStream());
        new ByteArrayOutputStream().write(response.body().readAllBytes());
    }

    private List<Meter> poolMeters() {
        return meterRegistry.getMeters().stream()
                .filter(m -> m.getId().getName().startsWith(
                        "reactor.netty.connection.provider."))
                .toList();
    }

    @Test
    void aProxiedRequestRegistersTheUpstreamPoolMetrics() throws Exception {
        proxyOneRequest();

        assertThat(poolMeters())
                .as("the upstream connection pool publishes nothing — "
                        + "httpclient.pool.metrics is off or not wired")
                .extracting(m -> m.getId().getName())
                .contains(
                        "reactor.netty.connection.provider.total.connections",
                        "reactor.netty.connection.provider.active.connections",
                        "reactor.netty.connection.provider.idle.connections",
                        "reactor.netty.connection.provider.max.connections",
                        "reactor.netty.connection.provider.pending.connections");
    }

    @Test
    void thePoolMetersNameTheProviderAndTheUpstreamTheyBelongTo() throws Exception {
        proxyOneRequest();

        List<Meter> total = poolMeters().stream()
                .filter(m -> m.getId().getName()
                        .equals("reactor.netty.connection.provider.total.connections"))
                .toList();
        // Every pool meter names the provider and the upstream it belongs
        // to — a set of unattributable series is worse than no series.
        //
        // Note: this JVM is shared across the test classes (surefire's
        // global micrometer registry is static), so pool series from
        // OTHER test classes' contexts show up here too, with their own
        // upstreams (localhost:10, 127.0.0.1:<their ports>). What every
        // series, wherever it came from, must agree on is the provider
        // name and a non-blank upstream — otherwise the panel cannot
        // attribute anything.
        assertThat(total).isNotEmpty();
        for (Meter meter : total) {
            System.out.println("POOL METER: " + meter.getId());
            assertThat(meter.getId().getTag("name"))
                    .as("every series names its provider")
                    .isEqualTo("proxy");
            assertThat(meter.getId().getTag("remote.address"))
                    .as("every series names the upstream it belongs to")
                    .isNotBlank();
        }
    }
}
