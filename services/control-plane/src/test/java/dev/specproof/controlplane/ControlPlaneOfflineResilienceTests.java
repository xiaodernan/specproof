package dev.specproof.controlplane;

import static org.assertj.core.api.Assertions.assertThat;

import dev.specproof.controlplane.config.JobCacheProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

/**
 * The honest version of the claim "#1631 put the control plane in the Spring
 * Cloud family".
 *
 * <p>The interesting property is not that the config server and the registry
 * work when they are up — it is that the control plane still boots, still
 * serves, and still keeps its own defaults when <b>both are down</b>. A
 * service that refuses to start whenever a config server hiccups has traded
 * one dependency for another, and the whole point of the {@code optional:}
 * import is that the word "optional" is load-bearing.</p>
 *
 * <p>This test turns both clients ON — the opposite of the test profile — and
 * points them at {@code 127.0.0.1:9}, the discard port, closed on every
 * machine. The assertions are facts about the running application:</p>
 * <ul>
 *   <li>the context starts at all (a failed {@code optional:} import must not
 *       be fatal; a failed Eureka registration must not be fatal either);</li>
 *   <li>the cache knobs keep their local defaults — the service falls back to
 *       its own file rather than to "whatever the server would have said";</li>
 *   <li>the breaker thresholds are the ones this build ships, so a config
 *       server outage cannot silently change how the cache degrades.</li>
 * </ul>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            // Both clients ON — and both pointed at a closed port.
            "spring.cloud.config.enabled=true",
            "spring.config.import=optional:configserver:http://127.0.0.1:9",
            "eureka.client.enabled=true",
            "eureka.client.register-with-eureka=true",
            "eureka.client.fetch-registry=true",
            "eureka.client.service-url.defaultZone=http://127.0.0.1:9/eureka/",
            // Do not let a dead registry keep a heartbeat thread around after the test.
            "eureka.client.initial-instance-info-replication-interval-seconds=1",
        })
class ControlPlaneOfflineResilienceTests {

    @Autowired
    private Environment environment;

    @Autowired
    private JobCacheProperties jobCache;

    @Test
    void theControlPlaneStillBootsAndKeepsItsOwnDefaultsWhenBothServersAreDown() {
        assertThat(environment.getProperty("spring.application.name"))
                .isEqualTo("specproof-control-plane");
        assertThat(jobCache.getBackend()).isEqualTo("redis");
        assertThat(jobCache.getBreakerFailureThreshold()).isEqualTo(5);
        assertThat(jobCache.getBreakerWaitMs()).isEqualTo(5000L);
    }
}
