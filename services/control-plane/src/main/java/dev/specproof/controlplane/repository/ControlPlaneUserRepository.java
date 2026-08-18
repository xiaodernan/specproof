package dev.specproof.controlplane.repository;

import dev.specproof.controlplane.entity.ControlPlaneUser;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

/** Users scoped by tenant. */
public interface ControlPlaneUserRepository
        extends JpaRepository<ControlPlaneUser, Long> {

    List<ControlPlaneUser> findByTenantId(String tenantId);
}
