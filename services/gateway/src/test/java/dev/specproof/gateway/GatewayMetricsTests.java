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
import org.springframework.test.context.ActiveProfiles;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;

/**
 * The edge's own metrics (Spring Cloud Gateway's {@code spring.cloud.gateway.metrics})
 * are on — and this class asks the registry.
 *
 * <p>Spring Cloud Gateway emits a CumulativeTimer per route it serves
 * ({@code spring.cloud.gateway.requests}, tagged by {@code routeId} /
 * {@code httpMethod} / {@code outcome} / {@code routeUri} …) plus a gauge for
 * how many routes are configured ({@code spring.cloud.gateway.routes.count}).
 * The management port already scrapes this process, so both land in
 * Prometheus with no further wiring — the only thing that was missing was
 * the flag, and no proof that it does anything.
 *
 * <p>Name the plane a request is stuck on: without these meters, the
 * management port tells you the breaker is closed and the pool is not
 * saturated, and says nothing about WHICH route the requests are flowing
 * through or how they finished.
 */
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            "SPECPROOF_CONTROL_PLANE_URL=http://127.0.0.1:9",
            "SPECPROOF_AGENT_RUNTIME_URL=http://127.0.0.1:${specproof.gwmetrics.upstream}",
        })
class GatewayMetricsTests {

    static final HttpServer LOCAL_UPSTREAM = startLocalUpstream();

    private static HttpServer startLocalUpstream() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                byte[] body = "gateway-metrics-leg".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
                exchange.close();
            });
            server.setExecutor(Executors.newFixedThreadPool(1, r -> {
                Thread t = new Thread(r, "gateway-metrics-upstream");
                t.setDaemon(true);
                return t;
            }));
            server.start();
            System.setProperty(
                    "specproof.gwmetrics.upstream",
                    String.valueOf(server.getAddress().getPort()));
            return server;
        } catch (Exception failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    @Autowired
    private MeterRegistry meterRegistry;

    @Autowired
    private TestRestTemplate restTemplate;

    @LocalManagementPort
    private int managementPort;

    @LocalServerPort
    private int edgePort;

    private void proxyOneRequest() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        HttpResponse<InputStream> response = client.send(
                HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + edgePort + "/api/metrics-leg"))
                        .timeout(Duration.ofSeconds(8)).GET().build(),
                HttpResponse.BodyHandlers.ofInputStream());
        new ByteArrayOutputStream().write(response.body().readAllBytes());
    }

    @Test
    void aProxiedRequestRegistersTheRouteTimerTaggedWithTheRouteId() throws Exception {
        proxyOneRequest();

        List<Meter> requestMeters = meterRegistry.getMeters().stream()
                .filter(m -> m.getId().getName().equals("spring.cloud.gateway.requests"))
                .toList();
        // Surefire's JVM shares micrometer's static registry across test
        // classes, so other tests may leave their own route-timers behind;
        // what must always exist after a real proxied request is THIS leg's route.
        assertThat(requestMeters)
                .as("no gateway route timer registered — spring.cloud.gateway.metrics "
                        + "is off or not wired")
                .extracting(m -> m.getId().getTag("routeId"))
                .contains("agent-runtime-default");
        Meter ours = requestMeters.stream()
                .filter(m -> "agent-runtime-default".equals(m.getId().getTag("routeId")))
                .findFirst()
                .orElseThrow();
        assertThat(ours.getId().getTag("httpMethod")).isEqualTo("GET");
        assertThat(ours.getId().getTag("outcome")).isEqualTo("SUCCESSFUL");
        assertThat(ours.getId().getTag("routeUri"))
                .as("the meter names the upstream the route points at")
                .startsWith("http://127.0.0.1:");
    }

    @Test
    void theGatewayPublishesHowManyRoutesItServes() {
        List<Meter> countMeters = meterRegistry.getMeters().stream()
                .filter(m -> m.getId().getName().equals("spring.cloud.gateway.routes.count"))
                .toList();
        assertThat(countMeters).hasSize(1);
        double value = countMeters.get(0) instanceof io.micrometer.core.instrument.Gauge gauge
                ? gauge.value() : Double.NaN;
        assertThat(value)
                .as("the meter the operator sees says how many routes the edge serves")
                .isEqualTo(6.0);
    }

    @Test
    void theRouteTimerPublishesHistogramBucketsToThePrometheusEndpoint() throws Exception {
        proxyOneRequest();

        // The percentiles-histogram Boot property is the only thing standing
        // between the route timer and computable per-route percentiles. This
        // leg asks the actuator — not the JVM's internal registry — so the
        // whole path (Boot binding -> micrometer -> /actuator/prometheus) is
        // measured, not assumed.
        String prometheus = restTemplate
                .getForEntity("http://127.0.0.1:" + managementPort + "/actuator/prometheus",
                        String.class)
                .getBody();
        org.assertj.core.api.Assertions.assertThat(prometheus)
                .as("the prometheus endpoint must publish the route timer's bucket series")
                .contains("spring_cloud_gateway_requests_seconds_bucket")
                .contains("route_id=\"agent-runtime-default\"");
    }
}
