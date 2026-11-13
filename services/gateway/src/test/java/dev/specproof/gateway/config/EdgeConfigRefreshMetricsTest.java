package dev.specproof.gateway.config;

import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;

import java.util.List;
import java.util.Set;

/**
 * The edge's refresh witness, measured without a network or a config server.
 *
 * <p>Same contract as the control plane's witness (#1646), on the edge's own
 * meter namespace. Legs pin:
 *
 * <ol>
 *   <li>it counts events, naming the meter an operator would pair with
 *       {@code specproof_cp_config_refresh_events_total};</li>
 *   <li>it remembers the last refresh's keys, sorted, and the time it happened;</li>
 *   <li>it reports nothing before the first event — no fabricated zero-instant.</li>
 * </ol>
 */
class EdgeConfigRefreshMetricsTest {

    @Test
    void a_registered_listener_counts_refresh_events() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        EdgeConfigRefreshMetrics witness = new EdgeConfigRefreshMetrics(meters);

        witness.onApplicationEvent(
                new EnvironmentChangeEvent(
                        this, Set.of("specproof.gateway.rate-limit.default")));
        witness.onApplicationEvent(
                new EnvironmentChangeEvent(
                        this,
                        Set.of(
                                "specproof.edge.security.headers.frame-options",
                                "specproof.gateway.rate-limit.default")));

        assertThat(meters.get(EdgeConfigRefreshMetrics.REFRESH_EVENTS_METER).counter().count())
                .isEqualTo(2.0);
        assertThat(witness.lastRefreshKeys())
                .containsExactly(
                        "specproof.edge.security.headers.frame-options",
                        "specproof.gateway.rate-limit.default");
        assertThat(witness.lastRefreshAt()).isNotNull();
    }

    @Test
    void the_witness_reports_nothing_before_the_first_refresh() {
        EdgeConfigRefreshMetrics witness = new EdgeConfigRefreshMetrics(new SimpleMeterRegistry());

        assertThat(witness.lastRefreshAt()).isNull();
        assertThat(witness.lastRefreshKeys()).isEmpty();
    }

    @Test
    void no_source_keys_are_reported_as_an_empty_sorted_list() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        EdgeConfigRefreshMetrics witness = new EdgeConfigRefreshMetrics(meters);

        witness.onApplicationEvent(new EnvironmentChangeEvent(this, Set.of()));

        assertThat(meters.get(EdgeConfigRefreshMetrics.REFRESH_EVENTS_METER).counter().count())
                .isEqualTo(1.0);
        assertThat(witness.lastRefreshKeys()).isEqualTo(List.of());
    }
}
