package com.specproof.demo.event;

import java.io.Serializable;
import java.time.Instant;

public class EmailChangedEvent implements Serializable {

    private static final long serialVersionUID = 1L;

    private Long userId;
    private String oldEmail;
    private String newEmail;
    private Instant timestamp;

    public EmailChangedEvent() {}

    public EmailChangedEvent(Long userId, String oldEmail, String newEmail) {
        this.userId = userId;
        this.oldEmail = oldEmail;
        this.newEmail = newEmail;
        this.timestamp = Instant.now();
    }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }

    public String getOldEmail() { return oldEmail; }
    public void setOldEmail(String oldEmail) { this.oldEmail = oldEmail; }

    public String getNewEmail() { return newEmail; }
    public void setNewEmail(String newEmail) { this.newEmail = newEmail; }

    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant timestamp) { this.timestamp = timestamp; }
}
