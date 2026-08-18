package dev.specproof.controlplane;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
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

    @Test
    void healthEndpointResponds() {
        ResponseEntity<Map> resp = rest.getForEntity("/health", Map.class);
        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).containsEntry("status", "ok");
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
