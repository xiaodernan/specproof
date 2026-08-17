package dev.specproof.controlplane.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import org.hibernate.annotations.Immutable;

/**
 * READ-ONLY projection of the verification_jobs table owned by the agent
 * runtime. The control plane exposes job state as a business facade; writes
 * only happen at creation time through VerificationJob (QUEUED), after
 * which the outbox/worker path owns all transitions.
 */
@Entity
@Immutable
@Table(name = "verification_jobs")
public class VerificationJobView {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "repo_path", length = 512)
    private String repoPath;

    @Column(name = "base_ref", length = 255)
    private String baseRef;

    @Column(name = "head_ref", length = 255)
    private String headRef;

    @Column(length = 16)
    private String status;

    @Column(name = "created_at")
    private java.time.LocalDateTime createdAt;

    protected VerificationJobView() {
    }

    public String getId() {
        return id;
    }

    public String getRepoPath() {
        return repoPath;
    }

    public String getBaseRef() {
        return baseRef;
    }

    public String getHeadRef() {
        return headRef;
    }

    public String getStatus() {
        return status;
    }

    public java.time.LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
