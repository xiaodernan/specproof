package dev.specproof.controlplane.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * Writable owner-side mapping of verification_jobs. The Control Plane
 * creates the job row (PENDING/QUEUED) together with the outbox event in
 * one transaction; the agent-runtime worker then owns the transitions.
 * Columns not mapped here (retry counters, summary, github_check_json) are
 * left to the runtime / database defaults.
 */
@Entity
@Table(name = "verification_jobs")
public class VerificationJob {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "repo_path", length = 512, nullable = false)
    private String repoPath;

    @Column(name = "base_ref", length = 255, nullable = false)
    private String baseRef;

    @Column(name = "head_ref", length = 255, nullable = false)
    private String headRef;

    @Column(name = "spec_path", length = 1024, nullable = false)
    private String specPath;

    @Column(length = 16)
    private String status;

    @Column(length = 16)
    private String depth;

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;

    protected VerificationJob() {
    }

    public VerificationJob(String id, String repoPath, String baseRef,
                           String headRef, String specPath, String status,
                           String depth) {
        this.id = id;
        this.repoPath = repoPath;
        this.baseRef = baseRef;
        this.headRef = headRef;
        this.specPath = specPath;
        this.status = status;
        this.depth = depth;
    }

    public String getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }
}
