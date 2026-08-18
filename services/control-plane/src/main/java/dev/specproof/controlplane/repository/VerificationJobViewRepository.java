package dev.specproof.controlplane.repository;

import dev.specproof.controlplane.entity.VerificationJobView;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/** Read-only facade over the agent runtime's job table. */
public interface VerificationJobViewRepository
        extends JpaRepository<VerificationJobView, String> {

    List<VerificationJobView> findTop50ByOrderByCreatedAtDesc();
}
