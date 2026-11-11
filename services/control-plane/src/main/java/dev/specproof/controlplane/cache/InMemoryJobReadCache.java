package dev.specproof.controlplane.cache;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.LongSupplier;

/**
 * Bounded, time-aware LRU — the cache used when no Redis is configured, and the
 * reference semantics the Redis implementation is tested against.
 *
 * <p>Two data-structure decisions worth stating:</p>
 * <ul>
 *   <li><b>LRU, not FIFO</b>: {@link LinkedHashMap} with {@code accessOrder=true}
 *       reorders on {@code get} as well as {@code put}, so a hot job row survives
 *       a stream of one-shot rows. FIFO would evict the row the dashboard polls
 *       every two seconds.</li>
 *   <li><b>Bounded</b>: {@link #MAX_ENTRIES} is a hard ceiling. An unbounded map
 *       in a long-lived process is a memory leak with extra steps — the same
 *       argument as a page cache that must not grow without a reclaim policy.
 *       Eviction is O(1) amortised via the eldest entry.</li>
 * </ul>
 *
 * <p>Time is injected ({@link LongSupplier} of epoch millis) so expiry is tested
 * by moving the clock, not by sleeping.</p>
 */
public final class InMemoryJobReadCache implements JobReadCache {

    /** Hard ceiling; 50-row list + a few thousand single rows would already be ~MBs. */
    static final int MAX_ENTRIES = 512;

    private record Entry(Object value, long expiresAtMillis) {
        boolean expired(long nowMillis) {
            return nowMillis >= expiresAtMillis;
        }
    }

    private final Map<String, Entry> entries;
    private final LongSupplier clock;

    public InMemoryJobReadCache() {
        this(System::currentTimeMillis);
    }

    public InMemoryJobReadCache(LongSupplier clock) {
        this.clock = clock;
        this.entries = new LinkedHashMap<String, Entry>(64, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(
                    Map.Entry<String, InMemoryJobReadCache.Entry> eldest) {
                return size() > MAX_ENTRIES;
            }
        };
    }

    @Override
    public synchronized Optional<List<JobView>> getRecent() {
        Object value = read(JobCachePolicy.recentKey());
        if (value == null) {
            return Optional.empty();
        }
        @SuppressWarnings("unchecked")
        List<JobView> typed = (List<JobView>) value;
        return Optional.of(typed);
    }

    @Override
    public synchronized void putRecent(List<JobView> jobs) {
        write(JobCachePolicy.recentKey(), List.copyOf(jobs), JobCachePolicy.RECENT_TTL);
    }

    @Override
    public synchronized Optional<JobView> getJob(String id) {
        Object value = read(JobCachePolicy.jobKey(id));
        return value instanceof JobView view ? Optional.of(view) : Optional.empty();
    }

    @Override
    public synchronized void putJob(JobView job) {
        write(JobCachePolicy.jobKey(job.id()), job, JobCachePolicy.ttlForStatus(job.status()));
    }

    @Override
    public String backend() {
        return "memory";
    }

    /** Visible for tests: how many entries are retained right now (including stale ones). */
    synchronized int size() {
        return entries.size();
    }

    private Object read(String key) {
        Entry entry = entries.get(key); // access-order touch
        if (entry == null) {
            return null;
        }
        if (entry.expired(clock.getAsLong())) {
            entries.remove(key);
            return null;
        }
        return entry.value();
    }

    private void write(String key, Object value, Duration ttl) {
        entries.put(key, new Entry(value, clock.getAsLong() + ttl.toMillis()));
    }

    /** Snapshot of the live keys — used by the eviction test, not by production code. */
    synchronized List<String> liveKeys() {
        long now = clock.getAsLong();
        List<String> keys = new ArrayList<>();
        entries.forEach((k, v) -> {
            if (!v.expired(now)) {
                keys.add(k);
            }
        });
        return keys;
    }
}
