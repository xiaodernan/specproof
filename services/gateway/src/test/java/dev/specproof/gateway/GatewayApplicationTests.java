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

    @Autowired
    private io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry circuitBreakerRegistry;

    @Autowired
    private io.micrometer.core.instrument.MeterRegistry meterRegistry;

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
    void everyGettableControlPlaneRouteCarriesTheRetryFilter() {
        // Retry is GET-only on purpose: the mutating routes (tenants POST,
        // tenant-users POST, github-webhook POST) must never be retried by
        // the edge — a retry would duplicate the side effect upstream. The
        // read-<typed>=* reads are idempotent, so the edge retries 5XX twice
        // with small backoff (first 100ms x2 -> 500ms).
        java.util.Set<String> retryable = java.util.Set.of(
                "control-plane-jobs",
                "control-plane-tenants",
                "control-plane-tenant-item",
                "control-plane-tenant-users");
        var webhook = routes().stream()
                .filter(r -> r.getId().equals("control-plane-github-webhook"))
                .findFirst()
                .orElseThrow();
        assertThat(webhook.getFilters())
                .extracting(f -> f.getName())
                .doesNotContain("Retry");

        var controlPlane = routes().stream()
                .filter(r -> retryable.contains(r.getId()))
                .collect(java.util.stream.Collectors.toMap(RouteDefinition::getId, r -> r));
        assertThat(controlPlane).hasSize(4);
        assertThat(controlPlane.values()).allSatisfy(route ->
                assertThat(route.getFilters())
                        .anySatisfy(f -> {
                            assertThat(f.getName()).isEqualTo("Retry");
                            String args = f.getArgs().values().stream()
                                    .map(Object::toString).reduce("", (a, b) -> a + "," + b);
                            assertThat(args).contains("INTERNAL_SERVER_ERROR");
                            assertThat(args).contains("GET");
                        }));
    }

    @Test
    void everyControlPlaneRouteCarriesItsOwnBreaker() {
        // A hung control plane must never trip the breaker the catch-all
        // relies on, so the five control-plane routes carry EdgeCircuitBreaker
        // with instance=specproof-control-plane (#1597). The catch-all keeps
        // its own instance (specproof-edge) — the two planes share neither
        // the breaker nor the failure domain.
        java.util.Set<String> controlPlaneIds = java.util.Set.of(
                "control-plane-jobs",
                "control-plane-tenants",
                "control-plane-tenant-item",
                "control-plane-tenant-users",
                "control-plane-github-webhook");
        var controlPlane = routes().stream()
                .filter(r -> controlPlaneIds.contains(r.getId()))
                .collect(java.util.stream.Collectors.toMap(RouteDefinition::getId, r -> r));
        assertThat(controlPlane).hasSize(5);
        assertThat(controlPlane.values()).allSatisfy(route ->
                assertThat(route.getFilters())
                        .anySatisfy(f -> {
                            assertThat(f.getName()).isEqualTo("EdgeCircuitBreaker");
                            String joined = f.getArgs().values().stream()
                                    .map(Object::toString).reduce("", (a, b) -> a + "," + b);
                            assertThat(joined).contains("specproof-control-plane");
                        }));

        // both instances exist in the registry, independently named
        assertThat(circuitBreakerRegistry.getAllCircuitBreakers())
                .extracting(io.github.resilience4j.circuitbreaker.CircuitBreaker::getName)
                .contains("specproof-edge", "specproof-control-plane");
    }

    @Test
    void theManagementPlaneStaysBoundToLoopbackInsideTheTest() {
        assertThat(environment.getProperty("management.server.address"))
                .isEqualTo("127.0.0.1");
    }

    @Test
    void theEdgeCircuitBreakerMetricsAreExposed() {
        io.github.resilience4j.circuitbreaker.CircuitBreaker cb =
                circuitBreakerRegistry.circuitBreaker("specproof-edge");
        cb.tryAcquirePermission();
        cb.onSuccess(1, java.util.concurrent.TimeUnit.MILLISECONDS);

        var circuitBreakerMeters = meterRegistry.getMeters().stream()
                .filter(m -> m.getId().getName().startsWith("resilience4j.circuitbreaker"))
                .toList();
        assertThat(circuitBreakerMeters).isNotEmpty();
        assertThat(circuitBreakerMeters)
                .anySatisfy(m -> assertThat(m.getId().getTag("name"))
                        .isEqualTo("specproof-edge"));
    }
}
