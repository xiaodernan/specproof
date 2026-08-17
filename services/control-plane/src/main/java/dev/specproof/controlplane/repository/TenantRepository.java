package dev.specproof.controlplane.repository;

import dev.specproof.controlplane.entity.Tenant;
import org.springframework.data.jpa.repository.JpaRepository;

/** Tenant repository (MySQL source of truth). */
public interface TenantRepository extends JpaRepository<Tenant, String> {
}
