package dev.specproof.controlplane.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Knobs for the job facade cache.
 *
 * <p>{@code backend} is a kill switch as much as a selector:</p>
 * <ul>
 *   <li>{@code redis} (default) — shared cache, the deployment path;</li>
 *   <li>{@code memory} — per-JVM LRU, used by the test suite and by a single-node
 *       deployment with no Redis;</li>
 *   <li>{@code off} — no cache at all. Kept because "disable the cache" must be a
 *       configuration change an operator can make at 3am without a rollback: if
 *       the cache is suspected of serving a wrong row, this turns the suspicion
 *       into a non-issue while keeping the API up.</li>
 * </ul>
 */
@ConfigurationProperties(prefix = "specproof.control-plane.job-cache")
public class JobCacheProperties {

    /** redis | memory | off. */
    private String backend = "redis";

    public String getBackend() {
        return backend;
    }

    public void setBackend(String backend) {
        this.backend = backend;
    }
}
