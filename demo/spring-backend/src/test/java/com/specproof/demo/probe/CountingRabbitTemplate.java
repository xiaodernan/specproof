package com.specproof.demo.probe;

import org.springframework.amqp.core.MessagePostProcessor;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

/**
 * Counting/payload-capturing RabbitTemplate wrapper (test scope).
 *
 * Offline honesty: the demo test profile excludes RabbitAutoConfiguration
 * (application-test.yml) and tests run inside the offline execution sandbox
 * (--network none), so there is no broker to reach. The demo's own
 * TestMockBeansConfig already substitutes a Mockito mock for RabbitTemplate;
 * this wrapper plays the same role with the three capabilities the
 * reliability probes need:
 * <ul>
 *   <li>counts every convertAndSend attempt (publish_count),</li>
 *   <li>captures the published payload (type + reflective timestamp),</li>
 *   <li>injects exactly ONE broker failure into the next convertAndSend
 *       when the JVM system property specproof.probe.fail.once is "true".</li>
 * </ul>
 * It never delegates to a real connection: probing observes publish
 * ATTEMPTS, and the one-shot injected failure models a transient broker
 * outage at the template boundary.
 */
public class CountingRabbitTemplate extends RabbitTemplate {

    /** JVM system property: "true" = fail the NEXT convertAndSend once. */
    public static final String FAIL_ONCE_PROPERTY = "specproof.probe.fail.once";

    public CountingRabbitTemplate() {
        super();
    }

    @Override
    public void afterPropertiesSet() {
        // Deliberately no super call: this probe wrapper never delegates to
        // a real broker connection, so no ConnectionFactory is required
        // (the super implementation would raise "ConnectionFactory is
        // required" during Spring's bean initialization).
    }

    @Override
    public void convertAndSend(String exchange, String routingKey, Object object) {
        attempt(exchange, routingKey, object);
    }

    @Override
    public void convertAndSend(
            String exchange,
            String routingKey,
            Object object,
            MessagePostProcessor messagePostProcessor) {
        attempt(exchange, routingKey, object);
    }

    private void attempt(String exchange, String routingKey, Object payload) {
        boolean fail = Boolean.parseBoolean(
                System.getProperty(FAIL_ONCE_PROPERTY, "false"));
        if (fail) {
            // One-shot: the failure is consumed by THIS attempt only.
            System.clearProperty(FAIL_ONCE_PROPERTY);
        }
        ProbePublishRecorder.record(exchange, routingKey, payload, fail);
        if (fail) {
            throw new RuntimeException(
                    "SpecProof probe: injected one-shot broker failure");
        }
    }
}
