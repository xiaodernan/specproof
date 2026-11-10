package dev.specproof.gateway.mq;

import static org.assertj.core.api.Assertions.assertThat;

import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

/**
 * The wire contract, read from the shipped annotation rather than from a copy.
 *
 * <p>{@code tests/unit/test_w190_event_bus_has_both_sides.py} reconciles the
 * Java source with the Python producer; this test keeps the Java side honest at
 * runtime: the six keys the listener actually binds must be the six names
 * {@link GatewayMqEventConsumer#KNOWN_EVENTS} says it knows, and the bean must
 * stay inert unless an operator explicitly opts in. A seventh event added to
 * the list without adding a binding (or the reverse) is red here, not a
 * message that vanishes into an unbound routing key.
 */
class GatewayMqEventBindingTest {

    private static QueueBinding binding() throws NoSuchMethodException {
        Method method = GatewayMqEventConsumer.class.getMethod("consume", Message.class);
        RabbitListener listener = method.getAnnotation(RabbitListener.class);
        assertThat(listener).as("@RabbitListener on consume(Message)").isNotNull();
        assertThat(listener.bindings()).hasSize(1);
        return listener.bindings()[0];
    }

    @Test
    void theBoundKeysAreExactlyTheKnownEvents() throws Exception {
        QueueBinding binding = binding();
        assertThat(binding.key())
            .containsExactlyElementsOf(GatewayMqEventConsumer.KNOWN_EVENTS);
    }

    @Test
    void theExchangeIsADurableTopicPointingAtTheBus() throws Exception {
        QueueBinding binding = binding();
        assertThat(binding.exchange().value())
            .contains("specproof.observability.events");
        assertThat(binding.exchange().type()).isEqualTo("topic");
        assertThat(binding.exchange().durable()).isEqualTo("true");
        assertThat(binding.value().value()).contains("q.gateway.mq-events");
        assertThat(binding.value().durable()).isEqualTo("true");
    }

    @Test
    void theBeanIsConditionalOnAnExplicitTrue() {
        ConditionalOnProperty condition =
            GatewayMqEventConsumer.class.getAnnotation(ConditionalOnProperty.class);
        assertThat(condition).isNotNull();
        assertThat(condition.prefix()).isEqualTo("specproof.gateway.mq-events");
        assertThat(condition.name()).contains("enabled");
        assertThat(condition.havingValue()).isEqualTo("true");
    }

    @Test
    void theMetricNameIsStableForTheDashboard() {
        assertThat(GatewayMqEventConsumer.METRIC_NAME)
            .isEqualTo("specproof.gateway.mq.event");
    }
}
