package dev.specproof.configserver;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

/**
 * The config server must actually serve the gateway's externalized settings —
 * a config server that returns 404 for "gateway" is a fake control. This boots
 * the real server on a random port and hits its /{application}/{profile}
 * endpoint, the same endpoint a gateway would call via spring.config.import.
 */
@SpringBootTest(webEnvironment = RANDOM_PORT)
class ConfigServerApplicationTests {

  @Autowired
  private TestRestTemplate rest;

  @Test
  void servesTheGatewayConfigOverTheBus() {
    ResponseEntity<Map> response = rest.getForEntity("/gateway/default", Map.class);
    assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);

    Map<String, Object> body = response.getBody();
    assertThat(body).isNotNull().containsKey("propertySources");

    Map<String, Object> source = firstSource(body);
    assertThat(source)
        .containsEntry("specproof.gateway.mq-events.enabled", false)
        .containsEntry(
            "specproof.gateway.mq-events.exchange", "specproof.observability.events")
        .containsEntry("specproof.gateway.mq-events.queue", "q.gateway.mq-events")
        .containsEntry("specproof.gateway.request-size.enabled", true)
        .containsEntry("specproof.gateway.security-headers.enabled", true);
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> firstSource(Map<String, Object> body) {
    List<Map<String, Object>> sources =
        (List<Map<String, Object>>) body.get("propertySources");
    return (Map<String, Object>) sources.get(0).get("source");
  }
}
