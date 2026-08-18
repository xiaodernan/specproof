package dev.specproof.controlplane.repository;

import dev.specproof.controlplane.entity.WebhookDelivery;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WebhookDeliveryRepository
        extends JpaRepository<WebhookDelivery, Long> {

    boolean existsByDeliveryId(String deliveryId);
}
