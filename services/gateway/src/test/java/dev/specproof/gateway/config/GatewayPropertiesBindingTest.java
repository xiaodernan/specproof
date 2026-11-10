package dev.specproof.gateway.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

/**
 * The edge's config externalization (#1604): every operator knob lives in one
 * {@link GatewayProperties} bean bound from {@code specproof.gateway.*}, instead
 * of being scattered as {@code @Value} strings across the filters.
 *
 * <p>Claims pinned here:
 * <ul>
 *   <li>the bean binds from {@code specproof.gateway.*} (documented defaults
 *       merged with the {@code @TestPropertySource} overrides on this class:
 *       request-size stays on, max-bytes overridden to 2048, security-headers
 *       overridden off, mq-events stays off with the documented exchange/queue);</li>
 *   <li>environment overrides win (e.g. {@code specproof.gateway.request-size.max-bytes})
 *       — proving the value is read from config, not hard-coded;</li>
 *   <li>mq-events stays OFF here on purpose: enabling it would start a RabbitMQ
 *       listener and the test would need a broker. The default-off contract is
 *       itself verified by the binding asserting {@code enabled == false}.</li>
 * </ul>
 */
@SpringBootTest
@TestPropertySource(properties = {
    "specproof.gateway.request-size.max-bytes=2048",
    "specproof.gateway.security-headers.enabled=false",
})
class GatewayPropertiesBindingTest {

    @Autowired
    private GatewayProperties properties;

    @Test
    void bindsExternalizedConfigWithOverrides() {
        // Effective values = documented defaults merged with the class-level overrides.
        assertThat(properties.getRequestSize().isEnabled()).isTrue(); // default, not overridden
        assertThat(properties.getSecurityHeaders().isEnabled()).isFalse(); // overridden off
        assertThat(properties.getMqEvents().isEnabled()).isFalse(); // default off
        assertThat(properties.getMqEvents().getExchange())
            .isEqualTo("specproof.observability.events");
        assertThat(properties.getMqEvents().getQueue()).isEqualTo("q.gateway.mq-events");
    }

    @Test
    void environmentOverridesWinOverHardCodedDefaults() {
        // max-bytes overridden from the 10 MiB default to 2048, and security-headers
        // flipped off — proving the value is read from config, not hard-coded.
        assertThat(properties.getRequestSize().getMaxBytes()).isEqualTo(2048);
        assertThat(properties.getSecurityHeaders().isEnabled()).isFalse();
    }
}
