package dev.specproof.controlplane.cache;

import java.time.Duration;
import java.util.List;
import java.util.Optional;

/**
 * The read-through cache in front of the job projection.
 *
 * <p>Contract, in one sentence: <b>an implementation may lose writes and may
 * return {@link Optional#empty()}, but it may never throw.</b> A cache exists to
 * remove load from the database; the day it becomes a new way for a GET to fail,
 * it has made the system worse than no cache at all. Every implementation in
 * this package swallows backend errors, and {@code JobQueryService} treats the
 * empty answer as "unknown, go to the database".</p>
 *
 * <p>Values are {@link JobView} rather than entities so the cached bytes are the
 * API's bytes — see {@link JobView} for why.</p>
 */
public interface JobReadCache {

    Optional<List<JobView>> getRecent();

    void putRecent(List<JobView> jobs);

    Optional<JobView> getJob(String id);

    void putJob(JobView job);

    /** Human-readable backend name, used in metrics and in the debug header. */
    String backend();

    /** Expiry applied to a row of the given status — implementations must honour it. */
    default Duration ttlFor(String status) {
        return JobCachePolicy.ttlForStatus(status);
    }
}
