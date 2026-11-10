package dev.specproof.gateway.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * Registers {@link GatewayProperties} as a bound bean. No extra dependency —
 * {@code @ConfigurationProperties} is core Spring Boot. The edge's filters
 * inject this bean instead of reading {@code @Value} strings directly (#1604),
 * so every tunable lives in one externally-configurable object.
 */
@Configuration
@EnableConfigurationProperties(GatewayProperties.class)
public class GatewayConfig {
}
