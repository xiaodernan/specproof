package dev.specproof.controlplane;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

/**
 * The Prometheus endpoint is REAL, not a default fallthrough.
 *
 * <p>The control plane's actuator exposure lists {@code prometheus} in
 * application.yml — a scrape target only exists on paper until the endpoint
 * answers with series. Measured before this class existed (2026-11-13): the
 * yml named the endpoint but no test ever asked for it, so "the control plane
 * is observable" was a configuration sentence, not a measurement.</p>
 *
 * <p>The assertions that matter:</p>
 * <ol>
 *   <li>the endpoint answers 200 with a real body (not an empty page, not the
 *   tenant API answering on a wrong route);</li>
 *   <li>the body contains the control plane's own meter
 *   {@code specproof_cp_config_refresh_events_total} — the witness registered
 *   its counter at construction, so the series exists before any refresh
 *   happens (this is the exact shape an edge catch-all fallthrough produces:
 *   an answer that looks like metrics but carries none of ours);</li>
 *   <li>and a platform series (jvm_*) is present, proving the registry is a
 *   real PrometheusMeterRegistry and not a hand-rolled shim.</li>
 * </ol>
 */
@ActiveProfiles("test")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ControlPlanePrometheusEndpointTests {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void thePrometheusEndpointServesMetricsNotTheApi() {
        ResponseEntity<String> response = rest.getForEntity("/actuator/prometheus", String.class);

        assertThat(response.getStatusCode().value()).isEqualTo(200);
        String body = response.getBody();
        assertThat(body)
                .as("the /actuator/prometheus body must carry series, not a 200 with nothing")
                .isNotNull()
                .contains("specproof_cp_config_refresh_events_total")
                .contains("jvm_");
    }
}
