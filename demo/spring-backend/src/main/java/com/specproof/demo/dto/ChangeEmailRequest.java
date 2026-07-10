package com.specproof.demo.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class ChangeEmailRequest {

    @NotBlank
    @Email
    private String newEmail;

    public ChangeEmailRequest() {}

    public ChangeEmailRequest(String newEmail) {
        this.newEmail = newEmail;
    }

    public String getNewEmail() { return newEmail; }
    public void setNewEmail(String newEmail) { this.newEmail = newEmail; }
}
