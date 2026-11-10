package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;
import org.springframework.core.env.Environment;

/**
 * The edge's first runtime test — Spring Boot's gateway actually starts and
 * actually serves the table the Python gate (`tests/unit/test_gateway_route_table_
 * covers_every_plane_route.py`) only reads statically.
 *
 * The test does not re-read the YAML by hand: it asks the running application
 * for the bean the gateway itself uses to build the route table
 * ({@link RouteDefinitionLocator}), so the assertions hold for the real
 * runtime wiring, not for a second parse of the same file.
 *
 * Upstreams point at a closed port; nothing else runs against them. The
 * management endpoints bind the random loopback ports the test assigns.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            "SPECPROOF_CONTROL_PLANE_URL=http://localhost:9",
            "SPECPROOF_AGENT_RUNTIME_URL=http://localhost:9",
        })
class GatewayApplicationTests {

    @Autowired
    private RouteDefinitionLocator routeDefinitionLocator;

    @Autowired
    private Environment environment;

    private List<RouteDefinition> routes() {
        return routeDefinitionLocator.getRouteDefinitions().collectList().block();
    }

    @Test
    void theGatewayServesExactlyTheSixDeclaredRoutes() {
        assertThat(routes())
                .extracting(RouteDefinition::getId)
                .containsExactlyInAnyOrder(
                        "control-plane-jobs",
                        "control-plane-tenants",
                        "control-plane-tenant-item",
                        "control-plane-tenant-users",
                        "control-plane-github-webhook",
                        "agent-runtime-default")
                .hasSize(6);
    }

    private static String anyArgValue(org.springframework.cloud.gateway.handler.predicate.PredicateDefinition p) {
        return p.getArgs().values().stream()
                .map(Object::toString)
                .reduce("", (a, b) -> a + "," + b);
    }

    @Test
    void theControlPlaneJobsRouteMatchesOneSegmentAndOnlyGet() {
        RouteDefinition jobs = routes().stream()
                .filter(r -> r.getId().equals("control-plane-jobs"))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("control-plane-jobs missing"));
        assertThat(jobs.getUri()).hasToString("http://localhost:9");
        assertThat(jobs.getMetadata()).containsEntry("plane", "control-plane");
        RouteDefinition jobsFinal = jobs;
        assertThat(jobsFinal.getPredicates())
                .anySatisfy(p -> {
                    assertThat(p.getName()).isEqualTo("Path");
                    assertThat(anyArgValue(p)).contains("/api/v1/jobs", "/api/v1/jobs/{id}");
                })
                .anySatisfy(p -> {
                    assertThat(p.getName()).isEqualTo("Method");
                    assertThat(anyArgValue(p)).contains("GET");
                });
    }

    @Test
    void theCatchAllWindowsTheAgentRuntimeAndMatchesAnything() {
        RouteDefinition catchAll = routes().stream()
                .filter(r -> r.getId().equals("agent-runtime-default"))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("agent-runtime-default missing"));
        assertThat(catchAll.getUri()).hasToString("http://localhost:9");
        assertThat(catchAll.getMetadata()).containsEntry("plane", "agent-runtime");
        assertThat(catchAll.getPredicates())
                .anySatisfy(p -> {
                    assertThat(p.getName()).isEqualTo("Path");
                    assertThat(anyArgValue(p)).contains("/**");
                });
    }

    @Test
    void theCatchAllRouteCarriesTheEdgeCircuitBreakerFilter() {
        RouteDefinition catchAll = routes().stream()
                .filter(r -> r.getId().equals("agent-runtime-default"))
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("agent-runtime-default missing"));
        assertThat(catchAll.getFilters())
                .extracting(f -> f.getName())
                .contains("EdgeCircuitBreaker");
    }

    @Test
    void theManagementPlaneStaysBoundToLoopbackInsideTheTest() {
        assertThat(environment.getProperty("management.server.address"))
                .isEqualTo("127.0.0.1");
    }
}
