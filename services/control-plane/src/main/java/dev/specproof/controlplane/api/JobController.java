package dev.specproof.controlplane.api;

import dev.specproof.controlplane.entity.VerificationJobView;
import dev.specproof.controlplane.repository.VerificationJobViewRepository;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/** Job status facade — reads the runtime's source of truth, never writes. */
@RestController
@RequestMapping("/api/v1/jobs")
public class JobController {

    private final VerificationJobViewRepository jobs;

    public JobController(VerificationJobViewRepository jobs) {
        this.jobs = jobs;
    }

    @GetMapping
    public List<VerificationJobView> recent() {
        return jobs.findTop50ByOrderByCreatedAtDesc();
    }

    @GetMapping("/{id}")
    public ResponseEntity<VerificationJobView> get(@PathVariable String id) {
        return jobs.findById(id)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }
}
