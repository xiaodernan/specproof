package dev.specproof.gateway.mq;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

/**
 * Tag cardinality pin: a hostile or broken producer must not be able to
 * inflate the {@code event} tag set. Only the six published kinds exist as
 * their own series; anything else lands on {@code "unknown"} — bounded,
 * together with {@code "malformed"}, to eight series max.
 */
class GatewayMqEventCardinalityTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();

    private GatewayMqEventConsumer consumer() {
        return new GatewayMqEventConsumer(
            registry, "specproof.observability.events", "q.gateway.mq-events");
    }

    private double count(String event) {
        return registry.counter(GatewayMqEventConsumer.METRIC_NAME, "event", event).count();
    }

    @Test
    void unpublishedEventNameFallsBackToUnknown() {
        consumer().handle(Map.of("event", "tag-bomb-attempt-0001"));
        assertThat(count("tag-bomb-attempt-0001")).isZero();
        assertThat(count("unknown")).isEqualTo(1.0);
    }

    @Test
    void thousandsOfDistinctJunkNamesCollapseToUnknown() {
        GatewayMqEventConsumer c = consumer();
        for (int i = 0; i < 1000; i++) {
            c.handle(Map.of("event", "junk-" + i));
        }
        long series = registry.getMeters().stream()
            .filter(m -> m.getId().getName().equals(GatewayMqEventConsumer.METRIC_NAME))
            .count();
        assertThat(series).isEqualTo(1);
        assertThat(count("unknown")).isEqualTo(1000.0);
    }

    @Test
    void emptyStringEventNameCountsAsUnknown() {
        consumer().handle(Map.of("event", ""));
        assertThat(count("unknown")).isEqualTo(1.0);
    }
}
