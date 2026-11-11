package dev.specproof.controlplane.cache;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;
import java.util.List;
import java.util.Optional;

/**
 * Redis-backed {@link JobReadCache} — the real deployment path.
 *
 * <h2>The three decisions that make this safe to put in front of a GET</h2>
 * <ol>
 *   <li><b>Expiry is server-side.</b> Values are written with {@code SET ... EX},
 *       so Redis owns the deadline. A client-side deadline would need every
 *       instance's clock to agree; a fleet of containers that drift by a second
 *       would then disagree about freshness. One authority, no clock trust.</li>
 *   <li><b>Every Redis call is bounded in time by configuration, not by hope.</b>
 *       {@code spring.data.redis.timeout} / {@code connect-timeout} are set to
 *       50ms in {@code application.yml}. A cache whose socket can hang for the
 *       default 60s turns "the database is slow" into "the whole facade is
 *       down" — the classic failure where the cache becomes the outage. With a
 *       50ms command timeout the worst case is one wasted round trip.</li>
 *   <li><b>No exception escapes.</b> Any failure — connection refused, timeout,
 *       a value written by an older schema that no longer parses, an OOM in the
 *       serializer — is counted and reported as {@link Optional#empty()}. The
 *       caller then reads the database, which is always correct, just slower.
 *       The contract is in {@link JobReadCache}; this class is where it would be
 *       easiest to break, so the catch is deliberately broad and the reason is
 *       written down rather than implied.</li>
 * </ol>
 *
 * <p>What this deliberately does NOT do: distributed locking, write-through,
 * pub/sub invalidation. The writer of {@code verification_jobs} is the Python
 * runtime (a different process, a different language); adding a lock here would
 * not make it cooperate. The TTL policy in {@link JobCachePolicy} is the honest
 * mechanism for a projection nobody can invalidate.</p>
 */
public final class RedisJobReadCache implements JobReadCache {

    private static final Logger log = LoggerFactory.getLogger(RedisJobReadCache.class);
    private static final TypeReference<List<JobView>> RECENT_TYPE = new TypeReference<>() {
    };

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;
    private final Counter hits;
    private final Counter misses;
    private final Counter errors;

    public RedisJobReadCache(StringRedisTemplate redis, ObjectMapper mapper, MeterRegistry meters) {
        this.redis = redis;
        this.mapper = mapper;
        this.hits = Counter.builder("specproof_cp_job_cache_backend_ops_total")
                .tag("backend", "redis").tag("result", "hit").register(meters);
        this.misses = Counter.builder("specproof_cp_job_cache_backend_ops_total")
                .tag("backend", "redis").tag("result", "miss").register(meters);
        this.errors = Counter.builder("specproof_cp_job_cache_backend_ops_total")
                .tag("backend", "redis").tag("result", "error").register(meters);
    }

    @Override
    public Optional<List<JobView>> getRecent() {
        try {
            String json = redis.opsForValue().get(JobCachePolicy.recentKey());
            if (json == null) {
                misses.increment();
                return Optional.empty();
            }
            hits.increment();
            return Optional.of(mapper.readValue(json, RECENT_TYPE));
        } catch (Exception e) {
            return failed("getRecent", e);
        }
    }

    @Override
    public void putRecent(List<JobView> jobs) {
        try {
            redis.opsForValue().set(
                    JobCachePolicy.recentKey(),
                    mapper.writeValueAsString(jobs),
                    JobCachePolicy.RECENT_TTL);
        } catch (Exception e) {
            failed("putRecent", e);
        }
    }

    @Override
    public Optional<JobView> getJob(String id) {
        try {
            String json = redis.opsForValue().get(JobCachePolicy.jobKey(id));
            if (json == null) {
                misses.increment();
                return Optional.empty();
            }
            hits.increment();
            return Optional.of(mapper.readValue(json, JobView.class));
        } catch (Exception e) {
            return failed("getJob", e);
        }
    }

    @Override
    public void putJob(JobView job) {
        try {
            Duration ttl = JobCachePolicy.ttlForStatus(job.status());
            redis.opsForValue().set(JobCachePolicy.jobKey(job.id()), mapper.writeValueAsString(job), ttl);
        } catch (Exception e) {
            failed("putJob", e);
        }
    }

    @Override
    public String backend() {
        return "redis";
    }

    /** Counts the failure, logs at debug (a dead cache must not flood the log), returns empty. */
    private <T> Optional<T> failed(String op, Exception e) {
        errors.increment();
        log.debug("job read cache {} failed; falling through to the database: {}", op, e.toString());
        return Optional.empty();
    }
}
