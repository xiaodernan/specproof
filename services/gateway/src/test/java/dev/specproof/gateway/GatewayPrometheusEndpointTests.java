package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * The Prometheus endpoint is REAL, not a fallthrough to the catch-all.
 *
 * <p>Measured before this class existed (2026-11-10): with
 * {@code management.prometheus.metrics.export.enabled} absent, Boot 3 does
 * not register the PrometheusMeterRegistry bean, so {@code
 * /actuator/prometheus} is unmapped and the catch-all route answers for it —
 * Prometheus would scrape the AGENT RUNTIME's response through the edge and
 * never see a single edge series. That is exactly the shape of silent
 * failure the project refuses: an endpoint that answers "200" but is not a
 * metrics endpoint at all.
 *
 * <p>The one assertion that matters: the endpoint's body CONTAINS series
 * names, not merely an HTTP 200.
 */
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            "SPECPROOF_CONTROL_PLANE_URL=http://localhost:9",
            "SPECPROOF_AGENT_RUNTIME_URL=http://localhost:10",
        })
class GatewayPrometheusEndpointTests {

    @Autowired
    private TestRestTemplate restTemplate;

    @LocalManagementPort
    private int managementPort;

    @LocalServerPort
    private int edgePort;

    @Test
    void thePrometheusEndpointServesMetricsNotTheCatchAll() throws Exception {
        // Drive ONE real request through the edge first: the route timer is a
        // CumulativeTimer, so spring_cloud_gateway_requests_seconds_count only
        // exists once a request has flowed. The upstream here is a closed
        // port (10), so the gateway answers for itself; which status it
        // returns is irrelevant — the frame is what registers the meter.
        // (Before this leg existed the assertion passed only because some
        // other test class in the same JVM had driven traffic — test-order
        // dependence the gate must not have.)
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();
        client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + edgePort + "/probe"))
                        .timeout(Duration.ofSeconds(8))
                        .GET().build(),
                HttpResponse.BodyHandlers.ofString());
        ResponseEntity<String> response = restTemplate.getForEntity(
                "http://127.0.0.1:" + managementPort + "/actuator/prometheus",
                String.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(response.getBody())
                .as("/actuator/prometheus must answer with metrics, not with the "
                        + "catch-all route's reply (a 2-byte 'ok' would mean the edge "
                        + "is exporting NO metrics and the scrape is silently vacuous)")
                .contains("spring_cloud_gateway_requests_seconds_count")
                .contains("resilience4j_circuitbreaker_state")
                .contains("spring_cloud_gateway_routes_count")
                // the edge's ingress rate limiter (#1589) is wired into the
                // catch-all route: the tagged binder must publish the
                // limiter's own gauge at boot, or an operator cannot tell
                // "shedding load" from "upstream saturated"
                .contains("resilience4j_ratelimiter_available_permissions")
                .contains("specproof_gateway_rate_limited_total");
    }
}
