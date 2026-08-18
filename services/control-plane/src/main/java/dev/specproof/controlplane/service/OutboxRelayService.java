package dev.specproof.controlplane.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.specproof.controlplane.entity.OutboxEvent;
import dev.specproof.controlplane.repository.OutboxEventRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * Publishes Control-Plane outbox rows to RabbitMQ.
 *
 * At-least-once: a row is marked published ONLY after a publisher confirm
 * (ack). On nack/timeout the row stays unpublished and the next cycle
 * retries. The wire format is the same FLAT envelope the Python relay
 * produces, so the agent-runtime worker consumes both sources identically.
 */
@Service
@ConditionalOnProperty(name = "specproof.outbox.relay-enabled",
        havingValue = "true", matchIfMissing = true)
public class OutboxRelayService {

    private static final Logger log =
            LoggerFactory.getLogger(OutboxRelayService.class);

    private final OutboxEventRepository outbox;
    private final RabbitTemplate rabbit;
    private final ObjectMapper mapper;
    private final String exchange;
    private final int batchSize;

    public OutboxRelayService(
            OutboxEventRepository outbox,
            RabbitTemplate rabbit,
            ObjectMapper mapper,
            @Value("${specproof.outbox.exchange:specproof.p1.commands}")
            String exchange,
            @Value("${specproof.outbox.batch-size:10}") int batchSize) {
        this.outbox = outbox;
        this.rabbit = rabbit;
        this.mapper = mapper;
        this.exchange = exchange;
        this.batchSize = batchSize;
    }

    @Scheduled(fixedDelayString = "${specproof.outbox.relay-interval-ms:1000}")
    @Transactional
    public void drain() {
        List<OutboxEvent> rows =
                outbox.findUnpublished(PageRequest.of(0, batchSize));
        for (OutboxEvent row : rows) {
            if (!publishConfirmed(row)) {
                // published_at stays NULL — the next cycle retries.
                continue;
            }
            row.setPublishedAt(Instant.now());
            outbox.save(row);
            log.info("CP outbox published: id={} job={} event={}",
                    row.getId(), row.getAggregateId(), row.getEventType());
        }
    }

    public long pending() {
        return outbox.countByPublishedAtIsNull();
    }

    private boolean publishConfirmed(OutboxEvent row) {
        CorrelationData correlation =
                new CorrelationData("cp-outbox-" + row.getId());
        rabbit.convertAndSend(
                exchange, row.getRoutingKey(), flatten(row), correlation);
        try {
            CorrelationData.Confirm confirm =
                    correlation.getFuture().get(5, TimeUnit.SECONDS);
            return confirm != null && confirm.isAck();
        } catch (Exception e) {
            log.warn("CP outbox publish unconfirmed id={}: {}",
                    row.getId(), e.getMessage());
            return false;
        }
    }

    /**
     * FLAT wire envelope: envelope fields merged with the inner job fields.
     * Mirrors storage/outbox_relay.py exactly so the worker's flat reader
     * sees one canonical message shape from both producers.
     */
    Map<String, Object> flatten(OutboxEvent row) {
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("event_id", "cp-outbox-" + row.getId());
        envelope.put("outbox_id", row.getId());
        envelope.put("job_id", row.getAggregateId());
        envelope.put("event_type", row.getEventType());
        envelope.put("created_at", null);
        try {
            Map<?, ?> inner = mapper.readValue(row.getPayload(), Map.class);
            for (Map.Entry<?, ?> entry : inner.entrySet()) {
                envelope.put(String.valueOf(entry.getKey()), entry.getValue());
            }
        } catch (Exception e) {
            log.warn("CP outbox payload unreadable id={}: {}",
                    row.getId(), e.getMessage());
        }
        return envelope;
    }
}
