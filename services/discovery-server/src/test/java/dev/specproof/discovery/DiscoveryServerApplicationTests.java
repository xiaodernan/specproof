package dev.specproof.discovery;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * The registry must come up as a Spring context: the {@code @EnableEurekaServer}
 * auto-configuration, the actuator endpoints, and the YAML wiring all have to
 * resolve before anything can register against it.
 */
@SpringBootTest
class DiscoveryServerApplicationTests {

    @Test
    void contextLoads() {
        // If the Eureka server context fails to assemble (missing auto-config,
        // bad YAML, an offline-only dependency that is not cached), this fails
        // and the build is red before any service tries to register.
    }
}
