package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * The edge publishes its route table for operators — and this is the test
 * that says so.
 *
 * <p>Three copies of that table exist (the YAML the gateway routes by, the
 * Java test that names the routes, and the Grafana panel an operator
 * reads); the Python gate {@code tests/unit/test_edge_route_table_copies_
 * agree.py} holds the written copies against each other. This class holds
 * the <em>runtime</em> copy: Spring Cloud Gateway's own
 * {@code /actuator/gateway/routes} endpoint — the reading the gateway
 * itself publishes, which is what an operator (or a dashboard) can scrape.
 *
 * <p>Until now that endpoint was enabled in {@code application.yml} and
 * never asked for anything: "the route table is published" was a claim
 * about a configuration line, not a measurement of the endpoint.
 *
 * <p>The second half of this class pins the other half of the same
 * configuration: the actuator lives on its OWN port, because on the edge
 * port it would publish the upstream topology (the route table names each
 * plane's internal URL) and the edge is the public face of the product.
 */
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            // Two DIFFERENT upstreams, so "which plane does this route
            // point at" is a measurement and not a coincidence.
            "SPECPROOF_CONTROL_PLANE_URL=http://localhost:9",
            "SPECPROOF_AGENT_RUNTIME_URL=http://localhost:10",
        })
class GatewayActuatorRoutesTests {

    @Autowired
    private TestRestTemplate restTemplate;

    @LocalManagementPort
    private int managementPort;

    @LocalServerPort
    private int edgePort;

    @Autowired
    private io.micrometer.core.instrument.MeterRegistry meters;

    @Autowired
    private dev.specproof.gateway.config.EdgeConfigRefreshMetrics refreshWitness;

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private ResponseEntity<String> get(String url) {
        return restTemplate.getForEntity(url, String.class);
    }

    private List<Map<String, Object>> publishedRoutes() throws Exception {
        ResponseEntity<String> response =
                get("http://127.0.0.1:" + managementPort + "/actuator/gateway/routes");
        assertThat(response.getStatusCode().value())
                .as("the gateway's own route-table endpoint must answer on the "
                        + "management port; body was: %s", response.getBody())
                .isEqualTo(200);
        return MAPPER.readValue(response.getBody(),
                new TypeReference<List<Map<String, Object>>>() { });
    }

    private static Object metadata(Map<String, Object> route, String key) {
        Object metadata = route.get("metadata");
        assertThat(metadata).as("route %s has no metadata", route.get("route_id")).isInstanceOf(Map.class);
        return ((Map<?, ?>) metadata).get(key);
    }

    private static String routeId(Map<String, Object> route) {
        return String.valueOf(route.get("route_id"));
    }

    /**
     * The refresh contract, same claim-on-the-wire as the routes:
     * POST /actuator/refresh on the MANAGEMENT port must answer 200, and the
     * edge's own witness meter must move — the "命名" half and the "存在" half
     * are different claims, and only this one distinguishes them. The edge
     * port deliberately does not serve this endpoint, and the control-plane
     * witness (#1646) is a separate meter; nothing here proves the fleet
     * moved together — only that THIS edge refreshed.
     */
    @Test
    void theRefreshEndpointActuallyRefreshesAndCounts() {
        double before = meters
                .get(dev.specproof.gateway.config.EdgeConfigRefreshMetrics.REFRESH_EVENTS_METER)
                .counter()
                .count();

        ResponseEntity<String> response = restTemplate.postForEntity(
                "http://127.0.0.1:" + managementPort + "/actuator/refresh", null, String.class);
        assertThat(response.getStatusCode().value())
                .as("the edge's refresh endpoint must answer on the management port; body was: %s",
                        response.getBody())
                .isEqualTo(200);

        double after = meters
                .get(dev.specproof.gateway.config.EdgeConfigRefreshMetrics.REFRESH_EVENTS_METER)
                .counter()
                .count();
        assertThat(after).isGreaterThanOrEqualTo(before + 1.0);
        assertThat(refreshWitness.lastRefreshAt()).isNotNull();
    }

    @Test
    void theActuatorPublishesExactlyTheSixDeclaredRoutes() throws Exception {
        List<Map<String, Object>> routes = publishedRoutes();
        assertThat(routes).hasSize(6);
        assertThat(routes).extracting("route_id")
                .containsExactlyInAnyOrder(
                        "control-plane-jobs",
                        "control-plane-tenants",
                        "control-plane-tenant-item",
                        "control-plane-tenant-users",
                        "control-plane-github-webhook",
                        "agent-runtime-default");
    }

    @Test
    void theActuatorPublishesWhichPlaneOwnsEachRoute() throws Exception {
        for (Map<String, Object> route : publishedRoutes()) {
            String id = routeId(route);
            String expected = id.startsWith("control-plane-") ? "control-plane" : "agent-runtime";
            assertThat(metadata(route, "plane"))
                    .as("route %s", id)
                    .isEqualTo(expected);
        }
    }

    @Test
    void theActuatorPublishesWhichUpstreamEachRoutePointsAt() throws Exception {
        for (Map<String, Object> route : publishedRoutes()) {
            String id = routeId(route);
            String expected = id.startsWith("control-plane-")
                    ? "http://localhost:9"
                    : "http://localhost:10";
            assertThat(String.valueOf(route.get("uri")))
                    .as("route %s", id)
                    .isEqualTo(expected);
        }
    }

    @Test
    void theActuatorPublishesTheCatchAllLast() throws Exception {
        // The order of the published list is the order the gateway matches
        // in, and the catch-all must stay last — a catch-all that matched
        // first would swallow every specific route above it.
        List<Map<String, Object>> routes = publishedRoutes();
        assertThat(routeId(routes.get(routes.size() - 1))).isEqualTo("agent-runtime-default");
    }

    @Test
    void theRouteTableIsNotServedOnTheEdgePort() {
        // The edge port is the product's public face, and the route table
        // names each plane's internal upstream URL, so the actuator lives on
        // its OWN port. The edge port has no actuator route — so the
        // catch-all claims the path and proxies it to the agent runtime
        // (a closed port in this test), and the answer is the edge's own
        // 503, never the route table.
        ResponseEntity<String> response = get("http://127.0.0.1:" + edgePort + "/actuator/gateway/routes");
        assertThat(response.getStatusCode().value())
                .as("the actuator must not answer on the edge port; body was: %s",
                        response.getBody())
                .isEqualTo(503);
        assertThat(response.getBody())
                .as("the route table must not leak on the edge port; body was: %s",
                        response.getBody())
                .contains("\"edge\":\"circuit-open\"")
                .doesNotContain("route_id");
    }
}
