package dev.specproof.gateway.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Externalized edge configuration — the microservice "config externalization"
 * seam (#1604). Every operator-tunable knob the edge exposes lives here, bound
 * from {@code specproof.gateway.*} (application.yml + environment), so the
 * values have ONE home instead of being scattered as {@code @Value} strings
 * across the filters.
 *
 * <p>Defaults match the literal values the {@code @Value} constructors used
 * before this bean existed, so existing behavior — and the existing gateway
 * test suite — is unchanged when this bean is wired in.
 */
@ConfigurationProperties(prefix = "specproof.gateway")
public class GatewayProperties {

    private final RequestSize requestSize = new RequestSize();
    private final SecurityHeaders securityHeaders = new SecurityHeaders();
    private final MqEvents mqEvents = new MqEvents();
    private final RouteIsomorphismGate routeIsomorphismGate = new RouteIsomorphismGate();
    private final DiscoveryRoutes discoveryRoutes = new DiscoveryRoutes();

    public RequestSize getRequestSize() {
        return requestSize;
    }

    public SecurityHeaders getSecurityHeaders() {
        return securityHeaders;
    }

    public MqEvents getMqEvents() {
        return mqEvents;
    }

    public RouteIsomorphismGate getRouteIsomorphismGate() {
        return routeIsomorphismGate;
    }

    public DiscoveryRoutes getDiscoveryRoutes() {
        return discoveryRoutes;
    }

    /** Inbound request-body size cap (see {@code EdgeRequestSizeGlobalFilter}). */
    public static class RequestSize {
        /** Whether the edge caps inbound body size. */
        private boolean enabled = true;
        /** The declared-body cap in bytes (default 10 MiB). */
        private long maxBytes = 10L * 1024 * 1024;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public long getMaxBytes() {
            return maxBytes;
        }

        public void setMaxBytes(long maxBytes) {
            this.maxBytes = maxBytes;
        }
    }

    /** Defensive response-header set (see {@code EdgeSecurityHeadersGlobalFilter}). */
    public static class SecurityHeaders {
        /** Whether the edge stamps the defensive response-header set. */
        private boolean enabled = true;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    /** W190 observability event-bus subscription (see {@code GatewayMqEventConsumer}, #1603). */
    public static class MqEvents {
        /** Whether the edge subscribes to the event bus. Default off (fail-closed). */
        private boolean enabled = false;
        /** The topic exchange the agent runtime publishes events to. */
        private String exchange = "specproof.observability.events";
        /** The durable queue the edge binds for its own consumption. */
        private String queue = "q.gateway.mq-events";

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public String getExchange() {
            return exchange;
        }

        public void setExchange(String exchange) {
            this.exchange = exchange;
        }

        public String getQueue() {
            return queue;
        }

        public void setQueue(String queue) {
            this.queue = queue;
        }
    }

    /**
     * The dual-route-table isomorphism gate (#1635): the edge's curated path table
     * and the service registry must agree on which services back which paths. When
     * a discovery client is present, every route that names a {@code service-id}
     * (see route {@code metadata}) must exist in the registry; the gate fails
     * (or only warns) otherwise. Default fail-fast off so a missing service
     * degrades the edge, it does not wedge its boot.
     */
    public static class RouteIsomorphismGate {
        /** When true, a violated gate throws at startup instead of only reporting. */
        private boolean failFast = false;

        public boolean isFailFast() {
            return failFast;
        }

        public void setFailFast(boolean failFast) {
            this.failFast = failFast;
        }
    }

    /**
     * Opt-in discovery-backed routing (#1635): when enabled, a locator contributes
     * one route per discovered service under {@code /sd/{serviceId}/**} (namespaced
     * so it cannot collide with the curated table). Off by default — the curated
     * table is the source of truth; this is the escape hatch for ad-hoc services.
     */
    public static class DiscoveryRoutes {
        private boolean enabled = false;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }
}
