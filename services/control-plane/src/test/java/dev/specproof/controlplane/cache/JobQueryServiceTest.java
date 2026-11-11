package dev.specproof.controlplane.cache;

import dev.specproof.controlplane.entity.VerificationJobView;
import dev.specproof.controlplane.repository.VerificationJobViewRepository;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The read-through cache in front of the job projection.
 *
 * <p>These legs pin the properties the class's own documentation promises, because
 * each of them is a promise a reader of the code cannot check by reading it:</p>
 *
 * <ul>
 *   <li>a <b>miss</b> loads from the database and writes back;</li>
 *   <li>a <b>hit</b> never touches the database;</li>
 *   <li>a cache that <b>throws</b> is a bypass, not a failed GET;</li>
 *   <li>a <b>database error is not swallowed</b> — it is the real cause and it
 *       must reach the client;</li>
 *   <li><b>concurrent misses coalesce</b> into ONE database query (the reason
 *       the in-flight map exists: the SPA polls every two seconds from every
 *       open tab, and the cache is coldest exactly when the load is
 *       highest);</li>
 *   <li>a row that does <b>not exist</b> is not cached as a negative fact;</li>
 *   <li>the <b>counters</b> describe what happened;</li>
 *   <li>a hit and a miss carry the <b>same bytes</b> (the cache stores the
 *       API's shape, not the entity).</li>
 * </ul>
 */
class JobQueryServiceTest {

    private VerificationJobViewRepository jobs;
    private InMemoryJobReadCache cache;
    private MeterRegistry meters;
    private JobQueryService service;

    @BeforeEach
    void setUp() {
        jobs = Mockito.mock(VerificationJobViewRepository.class);
        cache = new InMemoryJobReadCache();
        meters = new SimpleMeterRegistry();
        service = new JobQueryService(jobs, cache, meters);
    }

    private static VerificationJobView view(String id, String status) {
        VerificationJobView view = Mockito.mock(VerificationJobView.class);
        Mockito.when(view.getId()).thenReturn(id);
        Mockito.when(view.getRepoPath()).thenReturn("/workspace/orders");
        Mockito.when(view.getBaseRef()).thenReturn("base");
        Mockito.when(view.getHeadRef()).thenReturn("head");
        Mockito.when(view.getStatus()).thenReturn(status);
        Mockito.when(view.getCreatedAt()).thenReturn(LocalDateTime.of(2026, 11, 12, 9, 0));
        return view;
    }

    @Test
    void a_miss_loads_from_the_database_and_writes_back() {
        VerificationJobView row = view("job-1", "VERIFIED");
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc()).thenReturn(List.of(row));

        CacheOutcome<List<JobView>> first = service.recent();

        assertEquals(CacheOutcome.Source.MISS, first.source());
        assertEquals(1, first.value().size());
        assertEquals("job-1", first.value().get(0).id());
        Mockito.verify(jobs, Mockito.times(1)).findTop50ByOrderByCreatedAtDesc();

        CacheOutcome<List<JobView>> second = service.recent();
        assertEquals(CacheOutcome.Source.HIT, second.source());
        assertEquals(first.value(), second.value(),
                "the cached copy must be the same rows the database answered");
    }

    @Test
    void a_hit_never_touches_the_database() {
        VerificationJobView row = view("job-1", "VERIFIED");
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc()).thenReturn(List.of(row));
        service.recent();

        Mockito.clearInvocations(jobs);
        service.recent();

        Mockito.verify(jobs, Mockito.never()).findTop50ByOrderByCreatedAtDesc();
    }

    @Test
    void a_cache_that_throws_is_a_bypass_not_a_failed_get() {
        JobReadCache broken = new JobReadCache() {
            @Override
            public Optional<List<JobView>> getRecent() {
                throw new IllegalStateException("redis is on fire");
            }

            @Override
            public void putRecent(List<JobView> ignored) {
                throw new IllegalStateException("redis is on fire");
            }

            @Override
            public Optional<JobView> getJob(String id) {
                throw new IllegalStateException("redis is on fire");
            }

            @Override
            public void putJob(JobView job) {
                throw new IllegalStateException("redis is on fire");
            }

            @Override
            public String backend() {
                return "broken";
            }
        };
        JobQueryService withBrokenCache = new JobQueryService(jobs, broken, meters);
        VerificationJobView row = view("job-1", "RUNNING");
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc()).thenReturn(List.of(row));

        CacheOutcome<List<JobView>> outcome = withBrokenCache.recent();

        assertEquals(CacheOutcome.Source.BYPASS, outcome.source(),
                "a broken cache must not turn a working GET into a failing one");
        assertEquals(1, outcome.value().size());
    }

    @Test
    void a_database_error_is_not_swallowed() {
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc())
                .thenThrow(new IllegalStateException("the database is down"));

        IllegalStateException thrown = assertThrows(IllegalStateException.class, () -> service.recent());
        assertEquals("the database is down", thrown.getMessage(),
                "a cache must never turn a failing GET into a working one");
    }

    @Test
    void concurrent_misses_coalesce_into_one_database_query() throws Exception {
        AtomicInteger queries = new AtomicInteger();
        CountDownLatch readers = new CountDownLatch(8);
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc()).thenAnswer(invocation -> {
            queries.incrementAndGet();
            // hold the query open long enough for every reader to pile up behind it
            Thread.sleep(50);
            return List.of(view("job-1", "VERIFIED"));
        });

        ExecutorService pool = Executors.newFixedThreadPool(8);
        List<java.util.concurrent.Future<CacheOutcome<List<JobView>>>> futures = new ArrayList<>();
        for (int i = 0; i < 8; i++) {
            futures.add(pool.submit(() -> {
                readers.countDown();
                readers.await(2, TimeUnit.SECONDS);
                return service.recent();
            }));
        }
        for (var future : futures) {
            future.get(10, TimeUnit.SECONDS);
        }
        pool.shutdown();

        assertEquals(1, queries.get(),
                "eight simultaneous misses must cost ONE database query, not eight");
    }

    @Test
    void a_row_that_does_not_exist_is_not_cached_as_a_negative_fact() {
        Mockito.when(jobs.findById(Mockito.anyString())).thenReturn(Optional.empty());

        assertTrue(service.job("job-missing").isEmpty());

        Mockito.clearInvocations(jobs);
        assertTrue(service.job("job-missing").isEmpty());
        Mockito.verify(jobs, Mockito.times(1)).findById("job-missing");
    }

    @Test
    void the_counters_describe_what_happened() {
        VerificationJobView row = view("job-1", "VERIFIED");
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc()).thenReturn(List.of(row));

        service.recent();
        service.recent();

        assertEquals(1.0, meters.get("specproof_cp_job_cache_requests_total")
                .tag("result", "miss").counter().count(), 0.0001);
        assertEquals(1.0, meters.get("specproof_cp_job_cache_requests_total")
                .tag("result", "hit").counter().count(), 0.0001);
    }

    @Test
    void a_hit_and_a_miss_carry_the_same_bytes() {
        VerificationJobView row = view("job-1", "VERIFIED");
        Mockito.when(jobs.findTop50ByOrderByCreatedAtDesc()).thenReturn(List.of(row));

        CacheOutcome<List<JobView>> miss = service.recent();
        CacheOutcome<List<JobView>> hit = service.recent();

        assertEquals(miss.value(), hit.value(),
                "the cached copy must be the API's own shape, so both paths serialize identically");
        assertSame(JobView.class, miss.value().get(0).getClass());
    }

    @Test
    void the_backend_name_is_the_cache_s() {
        assertEquals("memory", service.cacheBackend());
        assertFalse(service.cacheBackend().isBlank());
    }
}
