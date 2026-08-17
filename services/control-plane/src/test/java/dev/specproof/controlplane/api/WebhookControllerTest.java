package dev.specproof.controlplane.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.specproof.controlplane.repository.OutboxEventRepository;
import dev.specproof.controlplane.repository.VerificationJobRepository;
import dev.specproof.controlplane.repository.WebhookDeliveryRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Webhook ingestion: signature -> dedupe -> durable job + outbox event. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class WebhookControllerTest {

    private static final String SECRET = "test-webhook-secret";

    @Autowired
    private MockMvc mvc;

    @Autowired
    private ObjectMapper mapper;

    @Autowired
    private WebhookDeliveryRepository deliveries;

    @Autowired
    private OutboxEventRepository outbox;

    @Autowired
    private VerificationJobRepository jobs;

    private String prBody() throws Exception {
        return mapper.writeValueAsString(Map.of(
                "action", "opened",
                "pull_request", Map.of(
                        "base", Map.of("ref", "main", "sha", "base-sha"),
                        "head", Map.of("ref", "feature/x", "sha", "head-sha")),
                "repository", Map.of(
                        "clone_url", "https://github.com/acme/repo.git",
                        "name", "repo",
                        "owner", Map.of("login", "acme"))));
    }

    private String signature(String body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        byte[] digest = mac.doFinal(body.getBytes(StandardCharsets.UTF_8));
        StringBuilder hex = new StringBuilder();
        for (byte b : digest) {
            hex.append(String.format("%02x", b));
        }
        return "sha256=" + hex;
    }

    private MockHttpServletRequestBuilder signed(String body, String delivery) {
        try {
            return post("/api/v1/webhooks/github")
                    .header("X-Hub-Signature-256", signature(body))
                    .header("X-GitHub-Event", "pull_request")
                    .header("X-GitHub-Delivery", delivery)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body);
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    @Test
    void validEventCreatesJobAndOutboxRow() throws Exception {
        long outboxBefore = outbox.count();
        long jobsBefore = jobs.count();
        String body = prBody();
        mvc.perform(signed(body, "delivery-1"))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.action").value("job_created"))
                .andExpect(jsonPath("$.job_id").isNotEmpty());
        assertThat(deliveries.existsByDeliveryId("delivery-1")).isTrue();
        assertThat(outbox.count()).isEqualTo(outboxBefore + 1);
        assertThat(jobs.count()).isEqualTo(jobsBefore + 1);
    }

    @Test
    void duplicateDeliveryIsIdempotent() throws Exception {
        long outboxBefore = outbox.count();
        long jobsBefore = jobs.count();
        String body = prBody();
        MockHttpServletRequestBuilder request = signed(body, "delivery-dup");
        mvc.perform(request).andExpect(status().isAccepted());
        mvc.perform(request).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.action").value("duplicate_delivery"));
        assertThat(outbox.count()).isEqualTo(outboxBefore + 1);
        assertThat(jobs.count()).isEqualTo(jobsBefore + 1);
    }

    @Test
    void badSignatureIsRejected() throws Exception {
        long outboxBefore = outbox.count();
        long jobsBefore = jobs.count();
        String body = prBody();
        mvc.perform(post("/api/v1/webhooks/github")
                        .header("X-Hub-Signature-256", "sha256=" + "0".repeat(64))
                        .header("X-GitHub-Event", "pull_request")
                        .header("X-GitHub-Delivery", "delivery-bad")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isUnauthorized());
        assertThat(outbox.count()).isEqualTo(outboxBefore);
        assertThat(jobs.count()).isEqualTo(jobsBefore);
    }

    @Test
    void ignoredActionCreatesNoJob() throws Exception {
        long outboxBefore = outbox.count();
        long jobsBefore = jobs.count();
        String body = mapper.writeValueAsString(Map.of("action", "closed"));
        mvc.perform(signed(body, "delivery-closed"))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.action").value("ignored"));
        assertThat(outbox.count()).isEqualTo(outboxBefore);
        assertThat(jobs.count()).isEqualTo(jobsBefore);
    }
}
