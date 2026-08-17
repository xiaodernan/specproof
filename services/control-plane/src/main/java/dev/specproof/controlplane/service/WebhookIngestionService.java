package dev.specproof.controlplane.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.specproof.controlplane.entity.OutboxEvent;
import dev.specproof.controlplane.entity.VerificationJob;
import dev.specproof.controlplane.entity.WebhookDelivery;
import dev.specproof.controlplane.repository.OutboxEventRepository;
import dev.specproof.controlplane.repository.VerificationJobRepository;
import dev.specproof.controlplane.repository.WebhookDeliveryRepository;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Converts verified pull_request events into durable verification jobs.
 *
 * Guarantees, in one transaction: the delivery idempotency record, the
 * verification_jobs row (status QUEUED — the outbox event is durably
 * persisted in the same transaction, so the queued claim is true), and the
 * outbox event the relay will publish. The worker's first transition
 * (QUEUED -> RUNNING) is therefore always legal.
 */
@Service
public class WebhookIngestionService {

    public static final Set<String> JOB_ACTIONS =
            Set.of("opened", "synchronize", "ready_for_review");
    public static final String ROUTING_KEY = "q.p1.verify.job";

    /** Outcome of ingesting one verified delivery. */
    public record Accepted(String jobId, boolean duplicate, boolean jobCreated) {

        public static Accepted alreadySeen() {
            return new Accepted(null, true, false);
        }

        public static Accepted ignored() {
            return new Accepted(null, false, false);
        }
    }

    private final WebhookDeliveryRepository deliveries;
    private final OutboxEventRepository outbox;
    private final VerificationJobRepository jobs;
    private final ObjectMapper mapper;

    public WebhookIngestionService(WebhookDeliveryRepository deliveries,
                                   OutboxEventRepository outbox,
                                   VerificationJobRepository jobs,
                                   ObjectMapper mapper) {
        this.deliveries = deliveries;
        this.outbox = outbox;
        this.jobs = jobs;
        this.mapper = mapper;
    }

    @Transactional
    public Accepted ingest(String deliveryId, String event, String action,
                           Map<String, Object> payload) {
        if (deliveryId == null || deliveryId.isBlank()) {
            return Accepted.ignored();
        }
        // Same delivery must never enqueue twice: pre-check, and the unique
        // index on delivery_id as the concurrency backstop.
        if (deliveries.existsByDeliveryId(deliveryId)) {
            return Accepted.alreadySeen();
        }
        try {
            deliveries.save(new WebhookDelivery(
                    deliveryId,
                    event == null ? "" : event,
                    action == null ? "" : action,
                    writePayload(payload)));
        } catch (DataIntegrityViolationException e) {
            return Accepted.alreadySeen();
        }
        if (!"pull_request".equals(event) || !JOB_ACTIONS.contains(action)) {
            return Accepted.ignored();
        }

        Map<String, Object> pr = asMap(payload.get("pull_request"));
        Map<String, Object> repo = asMap(payload.get("repository"));
        Map<String, Object> base = asMap(pr.get("base"));
        Map<String, Object> head = asMap(pr.get("head"));
        String baseRef = firstNonBlank(asString(base.get("sha")),
                asString(base.get("ref")));
        String headRef = firstNonBlank(asString(head.get("sha")),
                asString(head.get("ref")));
        String cloneUrl = asString(repo.get("clone_url"));
        if (baseRef.isEmpty() || headRef.isEmpty() || cloneUrl.isEmpty()) {
            return Accepted.ignored();
        }

        String jobId = UUID.randomUUID().toString();
        jobs.save(new VerificationJob(
                jobId, cloneUrl, baseRef, headRef, "", "QUEUED", "FAST"));

        Map<String, Object> inner = new HashMap<>();
        inner.put("job_id", jobId);
        inner.put("repo_path", cloneUrl);
        inner.put("base_ref", baseRef);
        inner.put("head_ref", headRef);
        inner.put("spec_path", "");
        inner.put("depth", "FAST");
        outbox.save(new OutboxEvent(
                "verification_job", jobId, "JobCreated",
                writePayload(inner), ROUTING_KEY));
        return new Accepted(jobId, false, true);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Map.of();
    }

    private static String asString(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static String firstNonBlank(String first, String second) {
        return first == null || first.isBlank() ? second : first;
    }

    private String writePayload(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("payload serialization failed", e);
        }
    }
}
