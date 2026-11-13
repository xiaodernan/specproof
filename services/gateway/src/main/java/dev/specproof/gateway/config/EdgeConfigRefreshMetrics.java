package dev.specproof.gateway.config;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

/**
 * The edge's witness for in-place config refreshes.
 *
 * <p>The shared config server ({@code services/config-server}, #1609) serves the
 * edge's dynamic overrides — operator-tunable values that move without a redeploy.
 * Spring Cloud exposes {@code POST /actuator/refresh} on this instance's
 * management port (refresh endpoint from {@code spring-cloud-context}, already on
 * the classpath via {@code spring-cloud-starter-config}; the management port is
 * loopback by default so the refresh surface is never the public one). Hitting it
 * reloads the environment in place and publishes an
 * {@link EnvironmentChangeEvent}.
 *
 * <p>This bean is registered <b>unconditionally</b>. It does nothing until an
 * {@link EnvironmentChangeEvent} arrives; on an edge that never refreshes that
 * day never comes, and the meter it owns has nothing to count.
 *
 * <p>What it does: counts {@code specproof.edge.config.refresh.events} and
 * remembers the last refresh (its keys and its time) — the edge counterpart of
 * the control plane's refresh witness (#1646), so an operator pairing the two
 * can tell "the refresh reached the edge" from "the refresh reached the
 * control plane" instead of assuming the fleet moved together.
 */
@Component
public final class EdgeConfigRefreshMetrics {

    /** The meter name — one counter, monotone edge truth. */
    public static final String REFRESH_EVENTS_METER = "specproof.edge.config.refresh.events";

    private final AtomicReference<Instant> lastRefreshAt = new AtomicReference<>();
    private final AtomicReference<List<String>> lastRefreshKeys =
            new AtomicReference<>(List.of());
    private final Counter refreshEvents;

    public EdgeConfigRefreshMetrics(MeterRegistry meters) {
        this.refreshEvents = Counter.builder(REFRESH_EVENTS_METER).register(meters);
    }

    /** Record a refresh this edge reported. */
    @EventListener
    public void onApplicationEvent(EnvironmentChangeEvent event) {
        refreshEvents.increment();
        lastRefreshAt.set(Instant.now());
        Set<String> keys = event.getKeys();
        lastRefreshKeys.set(keys == null ? List.of() : keys.stream().sorted().toList());
    }

    /** When this edge last reported a config refresh, if ever. */
    public Instant lastRefreshAt() {
        return lastRefreshAt.get();
    }

    /** The keys of the last reported refresh, sorted; empty before the first. */
    public List<String> lastRefreshKeys() {
        return lastRefreshKeys.get();
    }
}
