package dev.specproof.controlplane.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.specproof.controlplane.service.GithubWebhookVerifier;
import dev.specproof.controlplane.service.WebhookIngestionService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

/**
 * GitHub webhook ingestion: verify (fail-closed) -> dedupe -> durable job +
 * outbox event -> 202. The payload is parsed only AFTER the signature
 * check — unauthenticated bytes are never touched as JSON.
 */
@RestController
@RequestMapping("/api/v1/webhooks")
public class WebhookController {

    private final GithubWebhookVerifier verifier;
    private final WebhookIngestionService ingestion;
    private final ObjectMapper mapper;

    public WebhookController(GithubWebhookVerifier verifier,
                             WebhookIngestionService ingestion,
                             ObjectMapper mapper) {
        this.verifier = verifier;
        this.ingestion = ingestion;
        this.mapper = mapper;
    }

    @PostMapping("/github")
    public ResponseEntity<Map<String, Object>> github(
            @RequestHeader(value = "X-Hub-Signature-256",
                    required = false) String signature,
            @RequestHeader(value = "X-GitHub-Event",
                    required = false) String event,
            @RequestHeader(value = "X-GitHub-Delivery",
                    required = false) String deliveryId,
            @RequestBody byte[] body) {
        try {
            if (!verifier.verify(body, signature)) {
                return unauthorized();
            }
        } catch (GithubWebhookVerifier.SecretNotConfiguredException e) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(error);
        }

        Map<String, Object> payload;
        try {
            payload = mapper.readValue(body, Map.class);
        } catch (Exception e) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "invalid_json");
            return ResponseEntity.badRequest().body(error);
        }

        WebhookIngestionService.Accepted accepted = ingestion.ingest(
                deliveryId, event, asString(payload.get("action")), payload);

        Map<String, Object> response = new HashMap<>();
        response.put("accepted", true);
        if (accepted.duplicate()) {
            response.put("action", "duplicate_delivery");
        } else if (accepted.jobCreated()) {
            response.put("action", "job_created");
            response.put("job_id", accepted.jobId());
        } else {
            response.put("action", "ignored");
        }
        return ResponseEntity.accepted().body(response);
    }

    private static ResponseEntity<Map<String, Object>> unauthorized() {
        Map<String, Object> error = new HashMap<>();
        error.put("error", "invalid_signature");
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(error);
    }

    private static String asString(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
