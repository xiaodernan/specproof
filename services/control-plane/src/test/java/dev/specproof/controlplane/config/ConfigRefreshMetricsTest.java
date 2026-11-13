package dev.specproof.controlplane.config;

import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;

import java.util.List;
import java.util.Set;

/**
 * The control plane's refresh witness, measured without a broker.
 *
 * <p>Spring Cloud publishes {@link EnvironmentChangeEvent} when the operator
 * hits {@code POST /actuator/refresh} (the refresh endpoint from
 * spring-cloud-context, already on the classpath — no Spring Cloud Bus, no
 * broker). This bean counts them and remembers the last one — nothing else.
 * The legs below pin the honest behavior of that witness:
 *
 * <ol>
 *   <li>it counts events, naming the meter an operator would put in a
 *       dashboard next to the config-health probes;</li>
 *   <li>it remembers the last refresh's keys, sorted, and the time it
 *       happened — so a probe can ask "has this instance SEEN ANY refresh,
 *       and which keys did it see" without logging semantics;</li>
 *   <li>it does nothing before the first event — an instance that never saw
 *       a refresh reports no keys and no time, rather than a fabricated
 *       zero-instant.</li>
 * </ol>
 */
class ConfigRefreshMetricsTest {

    @Test
    void a_registered_listener_counts_refresh_events() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ConfigRefreshMetrics witness = new ConfigRefreshMetrics(meters);

        witness.onApplicationEvent(
                new EnvironmentChangeEvent(
                        this, Set.of("specproof.control-plane.job-cache.backend")));
        witness.onApplicationEvent(
                new EnvironmentChangeEvent(
                        this,
                        Set.of(
                                "eureka.client.service-url.defaultZone",
                                "specproof.control-plane.job-cache.backend")));

        assertThat(meters.get(ConfigRefreshMetrics.REFRESH_EVENTS_METER).counter().count())
                .isEqualTo(2.0);
        // The gauge of the last event's keys does not double-count.
        assertThat(witness.lastRefreshKeys())
                .containsExactly(
                        "eureka.client.service-url.defaultZone",
                        "specproof.control-plane.job-cache.backend");
        assertThat(witness.lastRefreshAt()).isNotNull();
    }

    @Test
    void the_witness_reports_nothing_before_the_first_refresh() {
        ConfigRefreshMetrics witness = new ConfigRefreshMetrics(new SimpleMeterRegistry());

        assertThat(witness.lastRefreshAt()).isNull();
        assertThat(witness.lastRefreshKeys()).isEmpty();
    }

    @Test
    void no_source_keys_are_reported_as_an_empty_sorted_list() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ConfigRefreshMetrics witness = new ConfigRefreshMetrics(meters);

        witness.onApplicationEvent(new EnvironmentChangeEvent(this, Set.of()));

        assertThat(meters.get(ConfigRefreshMetrics.REFRESH_EVENTS_METER).counter().count())
                .isEqualTo(1.0);
        assertThat(witness.lastRefreshKeys()).isEqualTo(List.of());
    }
}
