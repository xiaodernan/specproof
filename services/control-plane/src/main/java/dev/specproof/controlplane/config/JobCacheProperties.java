package dev.specproof.controlplane.config;

import dev.specproof.controlplane.cache.JobCacheBreaker;
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

    /**
     * Consecutive backend failures that open the circuit (#1631). While the
     * circuit is open the cache backend is not called at all: the answers are
     * the same ("the cache has nothing"), the cost is not.
     */
    private int breakerFailureThreshold = JobCacheBreaker.DEFAULT_FAILURE_THRESHOLD;

    /**
     * How long the circuit stays open before one probe is let through
     * (#1631). The probe decides whether the backend is back.
     */
    private long breakerWaitMs = JobCacheBreaker.DEFAULT_WAIT.toMillis();

    public String getBackend() {
        return backend;
    }

    public void setBackend(String backend) {
        this.backend = backend;
    }

    public int getBreakerFailureThreshold() {
        return breakerFailureThreshold;
    }

    public void setBreakerFailureThreshold(int breakerFailureThreshold) {
        this.breakerFailureThreshold = breakerFailureThreshold;
    }

    public long getBreakerWaitMs() {
        return breakerWaitMs;
    }

    public void setBreakerWaitMs(long breakerWaitMs) {
        this.breakerWaitMs = breakerWaitMs;
    }
}
