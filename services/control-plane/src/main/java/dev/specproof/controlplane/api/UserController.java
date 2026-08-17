package dev.specproof.controlplane.api;

import dev.specproof.controlplane.entity.ControlPlaneUser;
import dev.specproof.controlplane.entity.Tenant;
import dev.specproof.controlplane.repository.ControlPlaneUserRepository;
import dev.specproof.controlplane.repository.TenantRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Tenant-scoped user administration. */
@RestController
@RequestMapping("/api/v1/tenants/{tenantId}/users")
public class UserController {

    private final TenantRepository tenants;
    private final ControlPlaneUserRepository users;

    public UserController(TenantRepository tenants, ControlPlaneUserRepository users) {
        this.tenants = tenants;
        this.users = users;
    }

    @GetMapping
    public ResponseEntity<List<ControlPlaneUser>> list(@PathVariable String tenantId) {
        if (!tenants.existsById(tenantId)) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(users.findByTenantId(tenantId));
    }

    @PostMapping
    public ResponseEntity<ControlPlaneUser> create(
            @PathVariable String tenantId,
            @Valid @RequestBody CreateUserRequest request) {
        Tenant tenant = tenants.findById(tenantId).orElse(null);
        if (tenant == null) {
            return ResponseEntity.notFound().build();
        }
        ControlPlaneUser user = new ControlPlaneUser(
                tenant, request.login(), request.role());
        return ResponseEntity.status(HttpStatus.CREATED).body(users.save(user));
    }

    public record CreateUserRequest(
            @NotBlank String login,
            String role) {
    }
}
