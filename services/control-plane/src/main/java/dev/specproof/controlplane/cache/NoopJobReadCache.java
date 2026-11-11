package dev.specproof.controlplane.cache;

import java.util.List;
import java.util.Optional;

/**
 * The {@code backend=off} cache: every read misses, every write is discarded.
 *
 * <p>This is not a stub for tests — tests use {@link InMemoryJobReadCache}, which
 * has real semantics. This is the operator's kill switch. It exists because
 * "turn the cache off" must be answerable with a property flip, and because a
 * {@code null} cache would push the same {@code if (cache != null)} branch into
 * every caller, where the next refactor would forget one.</p>
 */
public final class NoopJobReadCache implements JobReadCache {

    @Override
    public Optional<List<JobView>> getRecent() {
        return Optional.empty();
    }

    @Override
    public void putRecent(List<JobView> jobs) {
        // deliberately discarded
    }

    @Override
    public Optional<JobView> getJob(String id) {
        return Optional.empty();
    }

    @Override
    public void putJob(JobView job) {
        // deliberately discarded
    }

    @Override
    public String backend() {
        return "off";
    }
}
