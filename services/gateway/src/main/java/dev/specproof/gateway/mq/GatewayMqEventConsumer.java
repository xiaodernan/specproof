package dev.specproof.gateway.mq;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.Exchange;
import org.springframework.amqp.rabbit.annotation.Queue;
import org.springframework.amqp.rabbit.annotation.QueueBinding;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import io.micrometer.core.instrument.MeterRegistry;

/**
 * Edge-side subscriber for the W190 six-event RabbitMQ observability bus.
 *
 * <p>The Python agent runtime ({@code storage/rabbitmq.py}) emits one structured
 * event per pipeline step — published, publish_confirm_timeout, consumed,
 * duplicate_acked, retry_scheduled, dead_lettered — onto the
 * {@code specproof.observability.events} topic exchange, one routing key per
 * event name. This consumer tallies each event into a Micrometer counter
 * ({@value #METRIC_NAME}, tagged by {@code event}), so the gateway's
 * Prometheus scrape exposes the agent runtime's message-pipeline health at the
 * edge without the edge ever talking to the agent runtime's database.
 *
 * <p>Why a Spring Cloud element: this is the concrete microservice seam between
 * the Python agent runtime and the Spring Cloud edge. The agent runtime owns
 * the broker topology and the events; the gateway owns only a read-only,
 * durable queue bound to six routing keys. Neither side imports the other's
 * code — they meet on the exchange, which is the entire point of an event bus.
 *
 * <p>Fail-closed by default: the whole bean is {@link ConditionalOnProperty}
 * on {@code specproof.gateway.mq-events.enabled}. When it is false (the
 * shipped default), this bean is never created, so Spring AMQP never registers
 * a listener container and the gateway boots with no broker connection at all.
 * An operator turns it on only when the {@code specproof.observability.events}
 * exchange and its six routing keys actually exist. Turning it on without that
 * topology in place fails loudly (the container cannot bind) rather than
 * silently swallowing events.
 */
@Component
@ConditionalOnProperty(
    prefix = "specproof.gateway.mq-events",
    name = "enabled",
    havingValue = "true")
public class GatewayMqEventConsumer {

    /** Micrometer counter name; exported as {@code specproof_gateway_mq_event_total}. */
    public static final String METRIC_NAME = "specproof.gateway.mq.event";

    /** The six event names published onto {@code specproof.observability.events}. */
    public static final List<String> KNOWN_EVENTS = List.of(
        "published",
        "publish_confirm_timeout",
        "consumed",
        "duplicate_acked",
        "retry_scheduled",
        "dead_lettered");

    private static final TypeReference<Map<String, Object>> PAYLOAD_TYPE =
        new TypeReference<>() {};

    private final MeterRegistry registry;
    private final ObjectMapper mapper;
    private final String exchange;
    private final String queue;

    public GatewayMqEventConsumer(
            MeterRegistry registry,
            @Value("${specproof.gateway.mq-events.exchange:specproof.observability.events}") String exchange,
            @Value("${specproof.gateway.mq-events.queue:q.gateway.mq-events}") String queue) {
        this.registry = registry;
        this.mapper = new ObjectMapper();
        this.exchange = exchange;
        this.queue = queue;
    }

    /**
     * The only listener. Binds a durable queue to the events exchange with the
     * six routing keys; Spring AMQP declares both on container start. Payloads
     * are JSON; a malformed one is counted under {@code event="malformed"} so a
     * poison message is visible on the dashboard instead of crashing the
     * container (which would stall every other event too).
     */
    @RabbitListener(bindings = @QueueBinding(
        exchange = @Exchange(
            value = "${specproof.gateway.mq-events.exchange:specproof.observability.events}",
            type = "topic",
            durable = "true"),
        value = @Queue(
            value = "${specproof.gateway.mq-events.queue:q.gateway.mq-events}",
            durable = "true"),
        key = {
            "published",
            "publish_confirm_timeout",
            "consumed",
            "duplicate_acked",
            "retry_scheduled",
            "dead_lettered"
        }))
    public void consume(Message message) {
        Map<String, Object> payload;
        try {
            payload = mapper.readValue(message.getBody(), PAYLOAD_TYPE);
        } catch (Exception e) {
            registry.counter(METRIC_NAME, "event", "malformed").increment();
            return;
        }
        handle(payload);
    }

    /**
     * Testable core: tallies one observability event by its {@code event} name.
     * A missing or non-string name is counted under {@code "unknown"} rather
     * than dropped — the edge reports what it sees, it does not guess.
     */
    void handle(Map<String, Object> payload) {
        Object raw = payload == null ? null : payload.get("event");
        String name = raw instanceof String s ? s : "unknown";
        registry.counter(METRIC_NAME, "event", name).increment();
    }

    /** The exchange this consumer subscribes to (for diagnostics/health). */
    public String getExchange() {
        return exchange;
    }

    /** The durable queue this consumer declares (for diagnostics/health). */
    public String getQueue() {
        return queue;
    }
}
