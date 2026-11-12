package dev.specproof.gateway.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;

import dev.specproof.gateway.config.GatewayProperties;

import reactor.core.publisher.Flux;

/**
 * The dual-route-table isomorphism gate, measured without a registry.
 *
 * <p>What can go wrong is the INVARIANT, not the wire: a path claimed twice, or a
 * route pointing at a service nobody registered. Each case is asserted at the
 * Java boundary with a mocked locator (and, where relevant, a mocked registry).</p>
 */
class RouteTableIsomorphismGateTest {

    private static RouteDefinition route(String id, String path, String serviceId) {
        RouteDefinition r = new RouteDefinition();
        r.setId(id);
        r.setPredicates(List.of(new PredicateDefinition("Path=" + path)));
        if (serviceId != null) {
            r.setMetadata(Map.of("service-id", serviceId));
        }
        return r;
    }

    private static RouteDefinitionLocator locatorOf(RouteDefinition... routes) {
        RouteDefinitionLocator locator = mock(RouteDefinitionLocator.class);
        when(locator.getRouteDefinitions()).thenReturn(Flux.just(routes));
        return locator;
    }

    private static GatewayProperties props(boolean failFast) {
        GatewayProperties p = new GatewayProperties();
        p.getRouteIsomorphismGate().setFailFast(failFast);
        return p;
    }

    @Test
    void aCleanTableWithNoRegistryIsOk() {
        RouteTableIsomorphismGate gate = new RouteTableIsomorphismGate(
                locatorOf(route("a", "/api/a", "control-plane"), route("b", "/api/b", "api")),
                null, props(false));

        GateReport report = gate.validate();

        assertThat(report.isOk()).isTrue();
        assertThat(report.registryAvailable()).isFalse();
        assertThat(report.duplicatePaths()).isEmpty();
        assertThat(report.referencedServices()).containsExactlyInAnyOrder("control-plane", "api");
    }

    @Test
    void aPathClaimedByTwoRoutesIsAViolation() {
        RouteTableIsomorphismGate gate = new RouteTableIsomorphismGate(
                locatorOf(route("a", "/api/shared", "control-plane"), route("b", "/api/shared", "api")),
                null, props(false));

        GateReport report = gate.validate();

        assertThat(report.isOk()).isFalse();
        assertThat(report.duplicatePaths()).containsExactly("/api/shared");
    }

    @Test
    void aReferencedServicePresentInTheRegistryPasses_caseInsensitive() {
        // Eureka upper-cases app names; the curated table uses lowercase ids.
        DiscoveryClient registry = mock(DiscoveryClient.class);
        when(registry.getServices()).thenReturn(List.of("CONTROL-PLANE", "API"));

        RouteTableIsomorphismGate gate = new RouteTableIsomorphismGate(
                locatorOf(route("a", "/api/a", "control-plane"), route("b", "/api/b", "api")),
                registry, props(false));

        GateReport report = gate.validate();

        assertThat(report.registryAvailable()).isTrue();
        assertThat(report.missingServices()).isEmpty();
        assertThat(report.isOk()).isTrue();
    }

    @Test
    void aReferencedServiceAbsentFromTheRegistryIsAViolation() {
        DiscoveryClient registry = mock(DiscoveryClient.class);
        when(registry.getServices()).thenReturn(List.of("OTHER"));

        RouteTableIsomorphismGate gate = new RouteTableIsomorphismGate(
                locatorOf(route("a", "/api/a", "control-plane")),
                registry, props(false));

        GateReport report = gate.validate();

        assertThat(report.isOk()).isFalse();
        assertThat(report.missingServices()).containsExactly("control-plane");
    }

    @Test
    void failFastTurnsAViolationIntoAStartupException() {
        RouteTableIsomorphismGate gate = new RouteTableIsomorphismGate(
                locatorOf(route("a", "/api/shared", "control-plane"), route("b", "/api/shared", "api")),
                null, props(true));

        assertThatThrownBy(() -> gate.run(null))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("isomorphism gate violated");
    }
}
