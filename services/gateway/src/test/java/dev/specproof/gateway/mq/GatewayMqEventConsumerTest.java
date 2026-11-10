package dev.specproof.gateway.mq;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

/**
 * The edge's W190 event consumer, tested without any broker.
 *
 * <p>Claims pinned here (each backed by a direct call into the testable
 * {@link GatewayMqEventConsumer#handle(Map)} core, so no RabbitMQ is needed):
 * <ul>
 *   <li>each known event name is tallied under its own tag;</li>
 *   <li>different event names accumulate independently, same name adds up;</li>
 *   <li>a payload missing an {@code event} field (or with a non-string one)
 *       is counted under {@code "unknown"} rather than dropped;</li>
 *   <li>a null payload is safe and counts as {@code "unknown"};</li>
 *   <li>the consumer reports the exchange/queue it binds to.</li>
 * </ul>
 */
class GatewayMqEventConsumerTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();

    private GatewayMqEventConsumer consumer() {
        return new GatewayMqEventConsumer(
            registry, "specproof.observability.events", "q.gateway.mq-events");
    }

    private double count(String event) {
        return registry.counter(GatewayMqEventConsumer.METRIC_NAME, "event", event).count();
    }

    @Test
    void countsAKnownEventByName() {
        consumer().handle(Map.of("event", "consumed"));
        assertThat(count("consumed")).isEqualTo(1.0);
    }

    @Test
    void talliesEachEventTypeIndependently() {
        GatewayMqEventConsumer c = consumer();
        c.handle(Map.of("event", "published"));
        c.handle(Map.of("event", "consumed"));
        c.handle(Map.of("event", "consumed"));

        assertThat(count("published")).isEqualTo(1.0);
        assertThat(count("consumed")).isEqualTo(2.0);
        assertThat(count("dead_lettered")).isEqualTo(0.0);
    }

    @Test
    void everyDocumentedEventNameIsTallied() {
        GatewayMqEventConsumer c = consumer();
        for (String name : GatewayMqEventConsumer.KNOWN_EVENTS) {
            c.handle(Map.of("event", name));
        }
        for (String name : GatewayMqEventConsumer.KNOWN_EVENTS) {
            assertThat(count(name))
                .as("event %s should be counted once", name)
                .isEqualTo(1.0);
        }
    }

    @Test
    void missingEventNameCountsAsUnknown() {
        consumer().handle(Map.of("other", "x"));
        assertThat(count("unknown")).isEqualTo(1.0);
    }

    @Test
    void nonStringEventNameCountsAsUnknown() {
        consumer().handle(Map.of("event", 123));
        assertThat(count("unknown")).isEqualTo(1.0);
    }

    @Test
    void nullPayloadIsSafeAndCountsAsUnknown() {
        consumer().handle(null);
        assertThat(count("unknown")).isEqualTo(1.0);
    }

    @Test
    void exposesBoundExchangeAndQueue() {
        GatewayMqEventConsumer c = consumer();
        assertThat(c.getExchange()).isEqualTo("specproof.observability.events");
        assertThat(c.getQueue()).isEqualTo("q.gateway.mq-events");
    }

    @Test
    void knownEventsAreTheSixDocumentedOnes() {
        assertThat(GatewayMqEventConsumer.KNOWN_EVENTS).containsExactly(
            "published",
            "publish_confirm_timeout",
            "consumed",
            "duplicate_acked",
            "retry_scheduled",
            "dead_lettered");
    }
}
