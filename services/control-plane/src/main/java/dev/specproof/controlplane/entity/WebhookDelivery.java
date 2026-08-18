package dev.specproof.controlplane.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.Instant;

/**
 * One received GitHub webhook delivery — the idempotency record for the
 * whole ingestion path. The unique delivery_id index is the race backstop
 * behind the existsByDeliveryId pre-check.
 */
@Entity
@Table(name = "webhook_deliveries")
public class WebhookDelivery {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "delivery_id", length = 64, unique = true, nullable = false)
    private String deliveryId;

    @Column(length = 64, nullable = false)
    private String event;

    @Column(length = 64, nullable = false)
    private String action;

    @Column(columnDefinition = "LONGTEXT")
    private String payload;

    @Column(name = "received_at", insertable = false, updatable = false)
    private Instant receivedAt;

    protected WebhookDelivery() {
    }

    public WebhookDelivery(String deliveryId, String event, String action,
                           String payload) {
        this.deliveryId = deliveryId;
        this.event = event;
        this.action = action;
        this.payload = payload;
    }

    public Long getId() {
        return id;
    }

    public String getDeliveryId() {
        return deliveryId;
    }

    public String getEvent() {
        return event;
    }

    public String getAction() {
        return action;
    }
}
