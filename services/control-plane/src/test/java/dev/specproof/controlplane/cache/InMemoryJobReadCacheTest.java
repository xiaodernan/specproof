package dev.specproof.controlplane.cache;

import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The bounded, time-aware LRU that backs the cache when no Redis is configured.
 *
 * <p>Two properties matter and neither is visible by reading the class:</p>
 *
 * <ul>
 *   <li>an <b>expired</b> entry reads as a miss (the clock is injected, so the
 *       expiry is measured rather than waited for), and</li>
 *   <li>the cache is <b>bounded</b>: past its ceiling the least recently used
 *       entry goes, and "least recently used" means the one that was read
 *       least recently — a hot row survives a stream of one-shot rows.</li>
 * </ul>
 */
class InMemoryJobReadCacheTest {

    private static JobView job(String id) {
        return new JobView(id, "/workspace/orders", "base", "head", "RUNNING",
                LocalDateTime.of(2026, 11, 12, 9, 0));
    }

    @Test
    void an_expired_entry_reads_as_a_miss() {
        AtomicLong now = new AtomicLong(1_000_000L);
        InMemoryJobReadCache cache = new InMemoryJobReadCache(now::get);

        cache.putJob(job("job-1"));
        assertTrue(cache.getJob("job-1").isPresent());

        // step past the in-flight TTL (5s) and the row is gone
        now.addAndGet(JobCachePolicy.IN_FLIGHT_TTL.toMillis() + 1);
        assertTrue(cache.getJob("job-1").isEmpty(),
                "an expired row must read as a miss, not as a stale answer");
    }

    @Test
    void a_terminal_row_outlives_an_in_flight_row() {
        AtomicLong now = new AtomicLong(1_000_000L);
        InMemoryJobReadCache cache = new InMemoryJobReadCache(now::get);

        cache.putJob(new JobView("job-done", "/workspace/orders", "base", "head", "VERIFIED",
                LocalDateTime.of(2026, 11, 12, 9, 0)));
        cache.putJob(job("job-1"));

        // past the in-flight TTL: the running row is gone, the terminal one
        // (which cannot change in this projection) is still there
        now.addAndGet(JobCachePolicy.IN_FLIGHT_TTL.toMillis() + 1);
        assertTrue(cache.getJob("job-1").isEmpty(),
                "a row that changes as the pipeline walks must expire quickly");
        assertTrue(cache.getJob("job-done").isPresent(),
                "a terminal row cannot change in this projection, so it stays");
    }

    @Test
    void the_cache_is_bounded_and_evicts_the_least_recently_used_row() {
        InMemoryJobReadCache cache = new InMemoryJobReadCache();

        // fill it past its ceiling, touching the first row so it is NOT the
        // least recently used any more
        cache.putJob(job("job-0"));
        for (int i = 1; i <= InMemoryJobReadCache.MAX_ENTRIES; i++) {
            cache.putJob(job("job-" + i));
            cache.getJob("job-0");
        }
        cache.putJob(job("job-last"));

        assertTrue(cache.getJob("job-last").isPresent(), "the newest row must be there");
        assertTrue(cache.getJob("job-1").isEmpty(),
                "the oldest row must have been evicted");
    }

    @Test
    void the_recent_list_is_stored_and_read_back_whole() {
        InMemoryJobReadCache cache = new InMemoryJobReadCache();

        cache.putRecent(List.of(job("job-1"), job("job-2")));

        Optional<List<JobView>> read = cache.getRecent();
        assertTrue(read.isPresent());
        assertEquals(2, read.get().size());
        assertEquals("job-2", read.get().get(1).id());
    }

    @Test
    void the_backend_names_itself() {
        assertEquals("memory", new InMemoryJobReadCache().backend());
        assertEquals("off", new NoopJobReadCache().backend());
    }

    @Test
    void the_noop_cache_reads_nothing_and_keeps_nothing() {
        NoopJobReadCache cache = new NoopJobReadCache();

        cache.putJob(job("job-1"));
        cache.putRecent(List.of(job("job-1")));

        assertTrue(cache.getJob("job-1").isEmpty());
        assertTrue(cache.getRecent().isEmpty());
    }
}
