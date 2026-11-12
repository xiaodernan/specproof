package dev.specproof.gateway.discovery;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;

/**
 * Opt-in discovery-backed routing (#1635): puts the service registry into the DATA
 * PLANE. When enabled, it contributes one route per discovered service under
 * {@code /sd/{serviceId}/**} so the edge can reach ad-hoc services by their
 * registry name without a curated entry — the actual instance host:port is read
 * from the registry, so the edge follows the fleet instead of a hardcoded URL.
 *
 * <p>The route is NAMESPACED under {@code /sd/} on purpose: it can never collide
 * with the curated table, and the {@link RouteTableIsomorphismGate} asserts exactly
 * that disjointness. Off by default — the curated table stays the single source of
 * truth; this is the escape hatch for services that have not earned a curated row.</p>
 *
 * <p>Fail-closed by default: the bean only exists when
 * {@code specproof.gateway.discovery-routes.enabled=true}.</p>
 */
@Component
@ConditionalOnProperty(
        prefix = "specproof.gateway.discovery-routes",
        name = "enabled",
        havingValue = "true")
public class DiscoveryRouteContributor implements RouteDefinitionLocator {

    private final DiscoveryClient discoveryClient;

    public DiscoveryRouteContributor(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @Override
    public Flux<RouteDefinition> getRouteDefinitions() {
        List<RouteDefinition> routes = new ArrayList<>();
        for (String serviceId : discoveryClient.getServices()) {
            List<ServiceInstance> instances = discoveryClient.getInstances(serviceId);
            if (instances.isEmpty()) {
                continue;
            }
            ServiceInstance instance = instances.get(0);
            RouteDefinition route = new RouteDefinition();
            route.setId("discovery-" + serviceId);
            route.setUri(URI.create("http://" + instance.getHost() + ":" + instance.getPort()));
            route.setPredicates(List.of(new PredicateDefinition("Path=/sd/" + serviceId.toLowerCase() + "/**")));
            route.setMetadata(Map.of("service-id", serviceId, "source", "discovery"));
            routes.add(route);
        }
        return Flux.fromIterable(routes);
    }
}
