package dev.specproof.controlplane.api;

import dev.specproof.controlplane.entity.Tenant;
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

/** Tenant administration endpoints. */
@RestController
@RequestMapping("/api/v1/tenants")
public class TenantController {

    private final TenantRepository tenants;

    public TenantController(TenantRepository tenants) {
        this.tenants = tenants;
    }

    @GetMapping
    public List<Tenant> list() {
        return tenants.findAll();
    }

    @PostMapping
    public ResponseEntity<Tenant> create(@Valid @RequestBody CreateTenantRequest request) {
        if (tenants.existsById(request.id())) {
            return ResponseEntity.status(HttpStatus.CONFLICT).build();
        }
        Tenant tenant = new Tenant(request.id(), request.name());
        if (request.plan() != null) {
            tenant.setPlan(request.plan());
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(tenants.save(tenant));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Tenant> get(@PathVariable String id) {
        return tenants.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    /** Request body for tenant creation (Java records = concise DTOs). */
    public record CreateTenantRequest(
            @NotBlank String id,
            @NotBlank String name,
            String plan) {
    }
}
