package dev.specproof.gateway.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.gateway.route.RouteDefinition;

import reactor.core.publisher.Flux;

/**
 * The opt-in discovery-backed route contributor, driven with a mocked registry.
 *
 * <p>Without a broker: the contributor must turn each registered service into one
 * namespaced route ({@code /sd/{serviceId}/**}) whose URI is the real instance
 * host:port pulled from the registry — that is the "registry into the data plane"
 * step, and it must never collide with the curated table.</p>
 */
class DiscoveryRouteContributorTest {

    private static ServiceInstance instance(String host, int port) {
        ServiceInstance inst = mock(ServiceInstance.class);
        when(inst.getHost()).thenReturn(host);
        when(inst.getPort()).thenReturn(port);
        return inst;
    }

    @Test
    void eachRegisteredServiceBecomesOneNamespacedRoute() {
        ServiceInstance cpInstance = instance("10.0.0.5", 8081);
        ServiceInstance apiInstance = instance("10.0.0.9", 8000);

        DiscoveryClient registry = mock(DiscoveryClient.class);
        when(registry.getServices()).thenReturn(List.of("control-plane", "api"));
        when(registry.getInstances("control-plane")).thenReturn(List.of(cpInstance));
        when(registry.getInstances("api")).thenReturn(List.of(apiInstance));

        DiscoveryRouteContributor contributor = new DiscoveryRouteContributor(registry);
        List<RouteDefinition> routes = contributor.getRouteDefinitions().collectList().block();

        assertThat(routes).hasSize(2);

        RouteDefinition cp = routes.stream().filter(r -> r.getId().equals("discovery-control-plane")).findFirst().orElseThrow();
        assertThat(cp.getUri().toString()).isEqualTo("http://10.0.0.5:8081");
        assertThat(cp.getPredicates().get(0).getArgs().values())
                .contains("/sd/control-plane/**");
        assertThat(cp.getMetadata()).containsEntry("source", "discovery");

        RouteDefinition api = routes.stream().filter(r -> r.getId().equals("discovery-api")).findFirst().orElseThrow();
        assertThat(api.getUri().toString()).isEqualTo("http://10.0.0.9:8000");
        assertThat(api.getPredicates().get(0).getArgs().values()).contains("/sd/api/**");
    }

    @Test
    void servicesWithNoLiveInstancesAreSkipped() {
        DiscoveryClient registry = mock(DiscoveryClient.class);
        when(registry.getServices()).thenReturn(List.of("ghost"));
        when(registry.getInstances("ghost")).thenReturn(List.of());

        DiscoveryRouteContributor contributor = new DiscoveryRouteContributor(registry);
        List<RouteDefinition> routes = contributor.getRouteDefinitions().collectList().block();

        assertThat(routes).isEmpty();
    }
}
