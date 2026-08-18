package com.specproof.demo.dto;

import java.math.BigDecimal;

public class OrderResponse {

    private Long id;
    private Long productId;
    private Integer quantity;
    private String requestId;
    private BigDecimal amount;
    private Integer stockRemaining;

    public OrderResponse() {}

    public OrderResponse(
            Long id,
            Long productId,
            Integer quantity,
            String requestId,
            BigDecimal amount,
            Integer stockRemaining) {
        this.id = id;
        this.productId = productId;
        this.quantity = quantity;
        this.requestId = requestId;
        this.amount = amount;
        this.stockRemaining = stockRemaining;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public Long getProductId() { return productId; }
    public void setProductId(Long productId) { this.productId = productId; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }

    public Integer getStockRemaining() { return stockRemaining; }
    public void setStockRemaining(Integer stockRemaining) { this.stockRemaining = stockRemaining; }
}
