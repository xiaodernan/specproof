package dev.specproof.gateway.discovery;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.gateway.handler.predicate.PredicateDefinition;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;
import org.springframework.lang.Nullable;
import org.springframework.stereotype.Component;

import dev.specproof.gateway.config.GatewayProperties;

/**
 * The dual-route-table isomorphism gate (#1635).
 *
 * <p>The edge keeps ONE curated path table (application.yml) that says which plane
 * owns which path. The service registry (Eureka) is the OTHER table — it says
 * which service instances actually exist. These two tables must agree, or the edge
 * is silently routing to a service nobody registered. This gate checks exactly
 * that, at startup and on {@code /actuator/health}:</p>
 *
 * <ul>
 *   <li><b>path uniqueness</b> — no path is claimed by two curated routes (the
 *       Python gate {@code test_gateway_route_table_covers_every_plane_route.py}
 *       checks coverage; this checks the dual — non-overlap);</li>
 *   <li><b>service presence</b> — every route that names a {@code service-id}
 *       (route metadata) must exist in the registry. Comparison is
 *       case-insensitive because Eureka upper-cases app names, while the curated
 *       table uses lowercase service ids.</li>
 * </ul>
 *
 * <p>When the registry is absent (tests, or a deliberately registry-less edge) the
 * service-presence leg is SKIPPED, not failed — the gate degrades to a structural
 * check rather than blocking boot. {@code fail-fast} (off by default) turns a
 * violation into a startup exception instead of a warning + DOWN health.</p>
 */
@Component
public class RouteTableIsomorphismGate implements HealthIndicator, ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(RouteTableIsomorphismGate.class);

    private final RouteDefinitionLocator routeLocator;
    @Nullable
    private final DiscoveryClient discoveryClient;
    private final boolean failFast;

    public RouteTableIsomorphismGate(RouteDefinitionLocator routeLocator,
                                     @Nullable DiscoveryClient discoveryClient,
                                     GatewayProperties props) {
        this.routeLocator = routeLocator;
        this.discoveryClient = discoveryClient;
        this.failFast = props.getRouteIsomorphismGate().isFailFast();
    }

    /** Run the check. Safe to call repeatedly; caches the last report for health. */
    public GateReport validate() {
        List<RouteDefinition> routes = routeLocator.getRouteDefinitions().collectList().block();
        if (routes == null) {
            routes = List.of();
        }

        Map<String, Long> pathCounts = new LinkedHashMap<>();
        List<String> referencedServices = new ArrayList<>();
        for (RouteDefinition r : routes) {
            for (String p : routePaths(r)) {
                pathCounts.merge(p, 1L, Long::sum);
            }
            Map<String, Object> meta = r.getMetadata();
            Object svcRaw = meta != null ? meta.get("service-id") : null;
            String svc = svcRaw != null ? svcRaw.toString() : null;
            if (svc != null && !svc.isBlank()) {
                referencedServices.add(svc);
            }
        }
        List<String> duplicates = pathCounts.entrySet().stream()
                .filter(e -> e.getValue() > 1)
                .map(Map.Entry::getKey)
                .sorted()
                .toList();

        boolean registryAvailable = discoveryClient != null;
        List<String> missingServices = List.of();
        if (registryAvailable) {
            java.util.Set<String> registered = discoveryClient.getServices().stream()
                    .map(String::toUpperCase)
                    .collect(Collectors.toSet());
            missingServices = referencedServices.stream()
                    .filter(s -> !registered.contains(s.toUpperCase()))
                    .distinct()
                    .sorted()
                    .toList();
        }

        boolean ok = duplicates.isEmpty() && missingServices.isEmpty();
        GateReport report = new GateReport(ok, registryAvailable, duplicates, missingServices,
                referencedServices.stream().distinct().sorted().toList());
        lastReport = report;
        return report;
    }

    private static List<String> routePaths(RouteDefinition r) {
        List<String> paths = new ArrayList<>();
        if (r.getPredicates() == null) {
            return paths;
        }
        for (PredicateDefinition p : r.getPredicates()) {
            if (!"Path".equalsIgnoreCase(p.getName())) {
                continue;
            }
            for (String value : p.getArgs().values()) {
                for (String segment : value.split(",")) {
                    String s = segment.trim();
                    if (!s.isEmpty()) {
                        paths.add(s);
                    }
                }
            }
        }
        return paths;
    }

    private volatile GateReport lastReport;

    @Override
    public void run(ApplicationArguments args) {
        GateReport r = validate();
        if (r.isOk()) {
            log.info("route-table isomorphism gate OK (referenced services={}, registry available={})",
                    r.referencedServices().size(), r.registryAvailable());
            return;
        }
        String detail = "duplicatePaths=" + r.duplicatePaths()
                + " missingServices=" + r.missingServices();
        if (failFast) {
            throw new IllegalStateException("route-table isomorphism gate violated: " + detail);
        }
        log.warn("route-table isomorphism gate VIOLATED (non-fatal): {}", detail);
    }

    @Override
    public Health health() {
        GateReport r = lastReport != null ? lastReport : validate();
        Health.Builder builder = r.isOk() ? Health.up() : Health.down();
        return builder
                .withDetail("duplicatePaths", r.duplicatePaths())
                .withDetail("missingServices", r.missingServices())
                .withDetail("registryAvailable", r.registryAvailable())
                .withDetail("referencedServices", r.referencedServices())
                .build();
    }
}
