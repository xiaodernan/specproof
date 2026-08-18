package dev.specproof.controlplane.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/** Readiness probe for the compose healthchecks and load balancers. */
@RestController
public class HealthController {

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("service", "specproof-control-plane", "status", "ok");
    }
}
