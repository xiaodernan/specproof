package dev.specproof.controlplane.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.validation.constraints.NotBlank;

/** A human user within a tenant (role-scoped). */
@Entity
@Table(
    name = "control_plane_users",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_tenant_login", columnNames = {"tenant_id", "login"}
    )
)
public class ControlPlaneUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne
    @JoinColumn(name = "tenant_id", nullable = false)
    private Tenant tenant;

    @NotBlank
    @Column(length = 255, nullable = false)
    private String login;

    @NotBlank
    @Column(length = 32, nullable = false)
    private String role = "member";

    protected ControlPlaneUser() {
    }

    public ControlPlaneUser(Tenant tenant, String login, String role) {
        this.tenant = tenant;
        this.login = login;
        this.role = role;
    }

    public Long getId() {
        return id;
    }

    public String getLogin() {
        return login;
    }

    public String getRole() {
        return role;
    }
}
