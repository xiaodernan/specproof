package dev.specproof.controlplane.cache;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The Redis-backed cache.
 *
 * <p>Without a Redis server the properties are still measurable, because what
 * can go wrong here is the <b>policy</b> (which key, which TTL) and the
 * <b>failure contract</b> (a dead cache must never fail a GET):</p>
 *
 * <ul>
 *   <li>a <b>miss</b> reads empty and is counted;</li>
 *   <li>a <b>hit</b> reads the row back;</li>
 *   <li>the <b>TTL follows the row's mutability class</b>: a terminal row keeps
 *       the long TTL, a row in flight (or one whose status this version has
 *       never heard of) keeps the short one;</li>
 *   <li>the <b>key carries the version</b>, so a shape change orphans the old
 *       keys instead of deserializing them into a silent lie;</li>
 *   <li>a <b>Redis failure reads as empty</b> and never throws -- a cache that
 *       fails a GET has made the system worse than no cache at all.</li>
 * </ul>
 */
class RedisJobReadCacheTest {

    private StringRedisTemplate redis;
    private ValueOperations<String, String> values;
    private MeterRegistry meters;
    private RedisJobReadCache cache;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        redis = Mockito.mock(StringRedisTemplate.class);
        values = Mockito.mock(ValueOperations.class);
        Mockito.when(redis.opsForValue()).thenReturn(values);
        meters = new SimpleMeterRegistry();
        cache = new RedisJobReadCache(redis, mapper(), meters);
    }

    /** The mapper Spring Boot hands the cache: it knows about LocalDateTime. */
    private static ObjectMapper mapper() {
        return new ObjectMapper().registerModule(new JavaTimeModule());
    }

    private static JobView job(String id, String status) {
        return new JobView(id, "/workspace/orders", "base", "head", status,
                LocalDateTime.of(2026, 11, 12, 9, 0));
    }

    @Test
    void a_miss_reads_empty_and_is_counted() {
        Mockito.when(values.get(Mockito.anyString())).thenReturn(null);

        assertTrue(cache.getJob("job-1").isEmpty());
        assertTrue(cache.getRecent().isEmpty());
        assertEquals(2.0, meters.get("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "miss").counter().count(), 0.0001);
    }

    @Test
    void a_hit_reads_the_row_back() throws Exception {
        JobView row = job("job-1", "VERIFIED");
        Mockito.when(values.get(JobCachePolicy.jobKey("job-1")))
                .thenReturn(mapper().writeValueAsString(row));

        Optional<JobView> read = cache.getJob("job-1");

        assertTrue(read.isPresent());
        assertEquals("job-1", read.get().id());
        assertEquals("VERIFIED", read.get().status());
        assertEquals(1.0, meters.get("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "hit").counter().count(), 0.0001);
    }

    @Test
    void the_ttl_follows_the_rows_mutability_class() {
        ArgumentCaptor<Duration> ttl = ArgumentCaptor.forClass(Duration.class);

        cache.putJob(job("job-done", "VERIFIED"));
        Mockito.verify(values).set(Mockito.eq(JobCachePolicy.jobKey("job-done")),
                Mockito.anyString(), ttl.capture());
        assertEquals(JobCachePolicy.TERMINAL_TTL, ttl.getValue(),
                "a terminal row cannot change in this projection");

        cache.putJob(job("job-running", "RUNNING"));
        Mockito.verify(values).set(Mockito.eq(JobCachePolicy.jobKey("job-running")),
                Mockito.anyString(), ttl.capture());
        assertEquals(JobCachePolicy.IN_FLIGHT_TTL, ttl.getValue(),
                "a row in flight changes as the pipeline walks");

        cache.putJob(job("job-unknown", "SOMETHING_NEW"));
        Mockito.verify(values).set(Mockito.eq(JobCachePolicy.jobKey("job-unknown")),
                Mockito.anyString(), ttl.capture());
        assertEquals(JobCachePolicy.IN_FLIGHT_TTL, ttl.getValue(),
                "a status this version has never heard of is not provably final");
    }

    @Test
    void the_key_carries_the_version() {
        cache.putJob(job("job-1", "RUNNING"));

        Mockito.verify(values).set(Mockito.eq(JobCachePolicy.KEY_PREFIX + "job:job-1"),
                Mockito.anyString(), Mockito.any(Duration.class));
        assertTrue(JobCachePolicy.KEY_PREFIX.contains("v1"),
                "the key must carry a version so a shape change orphans the old keys");
    }

    @Test
    void a_redis_failure_reads_as_empty_and_never_throws() {
        Mockito.when(values.get(Mockito.anyString()))
                .thenThrow(new IllegalStateException("the redis is on fire"));

        assertTrue(cache.getJob("job-1").isEmpty(),
                "a dead cache must read as empty, never as a failed GET");
        assertTrue(cache.getRecent().isEmpty());
        assertEquals(2.0, meters.get("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "error").counter().count(), 0.0001);
    }

    @Test
    void a_write_failure_is_swallowed_too() {
        Mockito.doThrow(new IllegalStateException("the redis is on fire"))
                .when(values).set(Mockito.anyString(), Mockito.anyString(), Mockito.any(Duration.class));

        cache.putJob(job("job-1", "RUNNING"));
        cache.putRecent(List.of(job("job-1", "RUNNING")));

        assertEquals(2.0, meters.get("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "error").counter().count(), 0.0001);
    }
}
