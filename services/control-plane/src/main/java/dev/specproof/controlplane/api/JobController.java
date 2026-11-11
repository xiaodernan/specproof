package dev.specproof.controlplane.api;

import dev.specproof.controlplane.cache.CacheOutcome;
import dev.specproof.controlplane.cache.JobQueryService;
import dev.specproof.controlplane.cache.JobView;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * Job status facade — reads the runtime's source of truth, never writes.
 *
 * <p>Every response says where its bytes came from
 * ({@code X-SpecProof-Cache: hit|miss|coalesced|bypass}) and which backend
 * answered ({@code X-SpecProof-Cache-Backend: redis|memory|off}). Two headers
 * instead of a paragraph of documentation: an operator who sees a row the CLI
 * contradicts can tell in one look whether the API is reading the table or a
 * five-second-old copy of it. {@code hit} is not a promise of freshness — it is
 * a promise that the TTL policy chose to serve this row, and that policy is
 * bounded by {@code JobCachePolicy}.</p>
 */
@RestController
@RequestMapping("/api/v1/jobs")
public class JobController {

    private static final String CACHE_HEADER = "X-SpecProof-Cache";
    private static final String BACKEND_HEADER = "X-SpecProof-Cache-Backend";

    private final JobQueryService jobs;

    public JobController(JobQueryService jobs) {
        this.jobs = jobs;
    }

    @GetMapping
    public ResponseEntity<List<JobView>> recent() {
        CacheOutcome<List<JobView>> outcome = jobs.recent();
        return ResponseEntity.ok()
                .header(CACHE_HEADER, outcome.headerValue())
                .header(BACKEND_HEADER, jobs.cacheBackend())
                .body(outcome.value());
    }

    @GetMapping("/{id}")
    public ResponseEntity<JobView> get(@PathVariable String id) {
        return jobs.job(id)
                .map(outcome -> ResponseEntity.ok()
                        .header(CACHE_HEADER, outcome.headerValue())
                        .header(BACKEND_HEADER, jobs.cacheBackend())
                        .body(outcome.value()))
                .orElseGet(() -> ResponseEntity.notFound()
                        // A 404 is never cached here, and the header says so: a row
                        // that does not exist yet may exist one second from now, and
                        // a negative cache would make creation look broken.
                        .header(CACHE_HEADER, "miss")
                        .header(BACKEND_HEADER, jobs.cacheBackend())
                        .build());
    }
}
