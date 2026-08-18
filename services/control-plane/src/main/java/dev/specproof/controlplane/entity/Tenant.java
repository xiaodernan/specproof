package dev.specproof.controlplane.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.NotBlank;

/** Multi-tenant boundary: every repository and job belongs to a tenant. */
@Entity
@Table(name = "tenants")
public class Tenant {

    @Id
    @NotBlank
    @Column(length = 64)
    private String id;

    @NotBlank
    @Column(length = 255, nullable = false)
    private String name;

    @Column(length = 64)
    private String plan = "community";

    protected Tenant() {
    }

    public Tenant(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getPlan() {
        return plan;
    }

    public void setPlan(String plan) {
        this.plan = plan;
    }
}
