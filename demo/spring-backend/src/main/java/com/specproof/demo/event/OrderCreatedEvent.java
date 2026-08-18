package com.specproof.demo.event;

import java.io.Serializable;
import java.time.Instant;

public class OrderCreatedEvent implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long orderId;
    private Long productId;
    private Integer quantity;
    private String requestId;
    private Instant timestamp;

    public OrderCreatedEvent() {}

    public OrderCreatedEvent(Long orderId, Long productId, Integer quantity, String requestId) {
        this.orderId = orderId;
        this.productId = productId;
        this.quantity = quantity;
        this.requestId = requestId;
        this.timestamp = Instant.now();
    }

    public Long getOrderId() { return orderId; }
    public void setOrderId(Long orderId) { this.orderId = orderId; }

    public Long getProductId() { return productId; }
    public void setProductId(Long productId) { this.productId = productId; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }

    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }
}
