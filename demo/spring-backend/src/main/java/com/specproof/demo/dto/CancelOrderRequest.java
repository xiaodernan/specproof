package com.specproof.demo.dto;

import jakarta.validation.constraints.NotBlank;

public class CancelOrderRequest {

    @NotBlank
    private String requestId;

    public CancelOrderRequest() {}

    public CancelOrderRequest(String requestId) {
        this.requestId = requestId;
    }

    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
}
