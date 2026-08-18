package dev.specproof.controlplane.repository;

import dev.specproof.controlplane.entity.VerificationJob;
import org.springframework.data.jpa.repository.JpaRepository;

/** Writable repository for job rows the Control Plane itself creates. */
public interface VerificationJobRepository
        extends JpaRepository<VerificationJob, String> {
}
