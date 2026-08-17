package com.specproof.demo.dto;

public class UserResponse {

    private Long id;
    private String username;
    private String emailAddress;

    public UserResponse() {}

    public UserResponse(Long id, String username, String email) {
        this.id = id;
        this.username = username;
        this.emailAddress = email;
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getEmailAddress() { return emailAddress; }
    public void setEmailAddress(String emailAddress) { this.emailAddress = emailAddress; }
}
