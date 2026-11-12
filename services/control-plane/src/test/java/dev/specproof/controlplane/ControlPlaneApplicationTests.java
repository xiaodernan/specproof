package dev.specproof.controlplane;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/** Control Plane smoke: context loads and the tenant API round-trips. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ControlPlaneApplicationTests {

    @Autowired
    private TestRestTemplate rest;

    @Autowired
    private ObjectProvider<DiscoveryClient> discoveryClient;

    @Test
    void healthEndpointResponds() {
        ResponseEntity<Map> resp = rest.getForEntity("/health", Map.class);
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).containsEntry("status", "ok");
    }

    /**
     * The probe says what this instance can see of the cluster it belongs to
     * (#1631). Two things, both measurable from inside the process: the
     * discovery view (which client, and whether this service is in the
     * registry it can see) and the declared config import.
     *
     * <p>What the answer IS depends on the environment, so the leg compares
     * the probe with the very client the probe asked — a probe that
     * disagreed with the registry it can see would be the kind of green
     * that hides a cluster nobody can find.</p>
     */
    @Test
    void theHealthProbeReportsTheClusterContextItCanSee() {
        ResponseEntity<Map> resp = rest.getForEntity("/health", Map.class);
        Map<?, ?> body = resp.getBody();
        assertThat(body).isNotNull();
        Map<?, ?> discovery = (Map<?, ?>) body.get("discovery");
        assertThat(discovery).isNotNull();
        assertThat((String) discovery.get("client")).isNotBlank();

        // The probe must not lie about the registry it can see: the client it
        // asked is the one the assertion asks. (What that answer IS depends
        // on the environment — an instance with the eureka client on the
        // classpath sees itself in its own local registry even with no
        // server — so the leg compares the two, it does not assert a
        // constant.)
        DiscoveryClient client = discoveryClient.getIfAvailable();
        boolean expected = client != null
                && client.getServices().contains("specproof-control-plane");
        assertThat((Boolean) discovery.get("registered")).isEqualTo(expected);
        assertThat(String.valueOf(body.get("config_import"))).isNotEmpty();
    }

    @Test
    void tenantRoundTrip() {
        ResponseEntity<Void> created = rest.postForEntity(
                "/api/v1/tenants",
                Map.of("id", "t-" + System.nanoTime(), "name", "ACME"),
                Void.class);
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
    }
}
