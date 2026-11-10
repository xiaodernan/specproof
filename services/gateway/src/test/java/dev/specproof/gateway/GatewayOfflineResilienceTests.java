package dev.specproof.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.gateway.route.RouteDefinition;
import org.springframework.cloud.gateway.route.RouteDefinitionLocator;
import org.springframework.core.env.Environment;

/**
 * The honest version of the claim "#1608 wired the edge to a config server and a
 * service registry".
 *
 * <p>The main {@code application.yml} now carries both a
 * {@code spring.config.import=optional:configserver:...} and an Eureka client. The
 * interesting property is not that they work when both servers are up — it is
 * that the edge still boots and still serves its complete route table when BOTH
 * are down, because a product whose edge refuses to start whenever a config
 * server hiccups has traded one dependency for another.</p>
 *
 * <p>This test turns both clients ON (the opposite of {@code application-test.yml})
 * and points them at {@code 127.0.0.1:9} — the discard port, closed on every
 * machine. The assertions are then facts about the running application:</p>
 * <ul>
 *   <li>the context starts at all (a failed {@code optional:} import must not be
 *       fatal; a failed Eureka registration must not be fatal either);</li>
 *   <li>all six declared routes are still there — the config import must not have
 *       swallowed the local document that owns them;</li>
 *   <li>{@code GatewayProperties} keeps its local defaults, i.e. the edge falls
 *       back to its own file rather than to "whatever the server would have
 *       said".</li>
 * </ul>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
            "server.port=0",
            "management.server.port=0",
            "management.server.address=127.0.0.1",
            "SPECPROOF_CONTROL_PLANE_URL=http://localhost:9",
            "SPECPROOF_AGENT_RUNTIME_URL=http://localhost:9",
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
class GatewayOfflineResilienceTests {

    @Autowired
    private RouteDefinitionLocator routeDefinitionLocator;

    @Autowired
    private Environment environment;

    @Autowired
    private dev.specproof.gateway.config.GatewayProperties gatewayProperties;

    private List<RouteDefinition> routes() {
        return routeDefinitionLocator.getRouteDefinitions().collectList().block();
    }

    @Test
    void theEdgeStillServesItsWholeRouteTableWhenTheConfigServerAndTheRegistryAreDown() {
        assertThat(routes())
                .extracting(RouteDefinition::getId)
                .containsExactlyInAnyOrder(
                        "control-plane-jobs",
                        "control-plane-tenants",
                        "control-plane-tenant-item",
                        "control-plane-tenant-users",
                        "control-plane-github-webhook",
                        "agent-runtime-default");
    }

    @Test
    void aDeadConfigServerLeavesTheLocalDefaultsInForce() {
        // The local file is the fallback, and it must be the SAME values the config
        // server would have served (services/config-server/.../config/gateway.yml).
        assertThat(gatewayProperties.getMqEvents().isEnabled()).isFalse();
        assertThat(gatewayProperties.getMqEvents().getExchange())
                .isEqualTo("specproof.observability.events");
        assertThat(gatewayProperties.getMqEvents().getQueue()).isEqualTo("q.gateway.mq-events");
        assertThat(gatewayProperties.getRequestSize().isEnabled()).isTrue();
        assertThat(gatewayProperties.getRequestSize().getMaxBytes()).isEqualTo(10 * 1024 * 1024);
        assertThat(gatewayProperties.getSecurityHeaders().isEnabled()).isTrue();
    }

    @Test
    void theImportLocationIsTheOneThisTestPinned() {
        // Guards against the test silently passing because the import was dropped:
        // the environment must still carry the (dead) config-server location.
        assertThat(environment.getProperty("spring.config.import", String[].class))
                .contains("optional:configserver:http://127.0.0.1:9");
    }
}
