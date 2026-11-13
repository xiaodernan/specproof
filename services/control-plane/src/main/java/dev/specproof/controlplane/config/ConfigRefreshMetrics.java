package dev.specproof.controlplane.config;

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
 * The control plane's witness for in-place config refreshes.
 *
 * <p>The shared config server ({@code services/config-server}, #1609) serves
 * dynamic overrides for the edge and for this service. Spring Cloud exposes
 * {@code POST /actuator/refresh} (refresh endpoint from
 * {@code spring-cloud-context}, already on the classpath via
 * {@code spring-cloud-starter-config} — no broker, no new jar): hitting it
 * reloads the environment in place and publishes an
 * {@link EnvironmentChangeEvent}. That is the refresh path this service
 * supports — an operator edits the config server, then curls refresh on the
 * instance (or on a load balancer loop), and the change lands without a
 * redeploy.
 *
 * <p>This bean is registered <b>unconditionally</b>. It does nothing until an
 * {@link EnvironmentChangeEvent} arrives; on a fleet that never refreshes
 * that day never comes, and the meter it owns has nothing to count. That is
 * the same shape as every other opt-in element in this service: the wiring
 * exists, the operational action decides.
 *
 * <p>What it does: counts {@code specproof.cp.config.refresh.events} and
 * remembers the last refresh (its keys and its time). That is what an
 * operator wants next to the config-health probes: "has this instance SEEN
 * any refresh, and when?" — and next to the deterministic rebuild story: a
 * probe that reads the new value proves the refresh landed, not merely that
 * the request was issued.
 */
@Component
public final class ConfigRefreshMetrics {

    /** The meter name — one counter, monotone fleet truth. */
    public static final String REFRESH_EVENTS_METER = "specproof.cp.config.refresh.events";

    private final AtomicReference<Instant> lastRefreshAt = new AtomicReference<>();
    private final AtomicReference<List<String>> lastRefreshKeys =
            new AtomicReference<>(List.of());
    private final Counter refreshEvents;

    public ConfigRefreshMetrics(MeterRegistry meters) {
        this.refreshEvents = Counter.builder(REFRESH_EVENTS_METER).register(meters);
    }

    /** Record a refresh the fleet reported. */
    @EventListener
    public void onApplicationEvent(EnvironmentChangeEvent event) {
        refreshEvents.increment();
        lastRefreshAt.set(Instant.now());
        Set<String> keys = event.getKeys();
        lastRefreshKeys.set(keys == null ? List.of() : keys.stream().sorted().toList());
    }

    /** When the fleet last reported a config refresh, if ever. */
    public Instant lastRefreshAt() {
        return lastRefreshAt.get();
    }

    /** The keys of the last reported refresh, sorted; empty before the first. */
    public List<String> lastRefreshKeys() {
        return lastRefreshKeys.get();
    }
}
