package dev.specproof.controlplane.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.specproof.controlplane.entity.OutboxEvent;
import dev.specproof.controlplane.repository.OutboxEventRepository;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.data.domain.Pageable;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** Relay wire contract + confirm-based publish semantics (pure unit). */
class OutboxRelayServiceTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private OutboxEvent row() {
        OutboxEvent event = new OutboxEvent(
                "verification_job", "job-1", "JobCreated",
                "{\"job_id\":\"job-1\",\"repo_path\":\"/repo\","
                        + "\"base_ref\":\"main\",\"head_ref\":\"head-sha\","
                        + "\"spec_path\":\"\",\"depth\":\"FAST\"}",
                "q.p1.verify.job");
        event.setId(7L);
        return event;
    }

    private OutboxRelayService relay(OutboxEventRepository repo,
                                     RabbitTemplate rabbit) {
        return new OutboxRelayService(
                repo, rabbit, mapper, "specproof.p1.commands", 10);
    }

    @Test
    void flattenProducesFlatWireEnvelope() throws Exception {
        OutboxRelayService service =
                relay(mock(OutboxEventRepository.class), mock(RabbitTemplate.class));
        Map<String, Object> envelope = service.flatten(row());
        assertThat(envelope).containsEntry("event_id", "cp-outbox-7");
        assertThat(envelope).containsEntry("outbox_id", 7L);
        assertThat(envelope).containsEntry("job_id", "job-1");
        assertThat(envelope).containsEntry("event_type", "JobCreated");
        assertThat(envelope).containsEntry("repo_path", "/repo");
        assertThat(envelope).containsEntry("base_ref", "main");
        assertThat(envelope).containsEntry("head_ref", "head-sha");
        assertThat(envelope).containsEntry("depth", "FAST");
        assertThat(envelope).doesNotContainKey("payload");
    }

    @Test
    void drainMarksPublishedOnlyOnConfirmAck() throws Exception {
        OutboxEventRepository repo = mock(OutboxEventRepository.class);
        RabbitTemplate rabbit = mock(RabbitTemplate.class);
        OutboxEvent event = row();
        when(repo.findUnpublished(any(Pageable.class))).thenReturn(List.of(event));
        doAnswer(invocation -> {
            CorrelationData correlation = invocation.getArgument(3);
            confirm(correlation, true);
            return null;
        }).when(rabbit).convertAndSend(
                eq("specproof.p1.commands"), eq("q.p1.verify.job"),
                any(Map.class), any(CorrelationData.class));

        relay(repo, rabbit).drain();

        verify(rabbit).convertAndSend(
                eq("specproof.p1.commands"), eq("q.p1.verify.job"),
                any(Map.class), any(CorrelationData.class));
        assertThat(event.getPublishedAt()).isNotNull();
        verify(repo).save(event);
    }

    @Test
    void drainLeavesRowUnpublishedOnNack() throws Exception {
        OutboxEventRepository repo = mock(OutboxEventRepository.class);
        RabbitTemplate rabbit = mock(RabbitTemplate.class);
        OutboxEvent event = row();
        when(repo.findUnpublished(any(Pageable.class))).thenReturn(List.of(event));
        doAnswer(invocation -> {
            CorrelationData correlation = invocation.getArgument(3);
            confirm(correlation, false);
            return null;
        }).when(rabbit).convertAndSend(
                eq("specproof.p1.commands"), eq("q.p1.verify.job"),
                any(Map.class), any(CorrelationData.class));

        relay(repo, rabbit).drain();

        assertThat(event.getPublishedAt()).isNull();
        verify(repo, never()).save(event);
    }

    private static void confirm(CorrelationData correlation, boolean ack) {
        correlation.getFuture()
                .complete(new CorrelationData.Confirm(ack, null));
    }
}
