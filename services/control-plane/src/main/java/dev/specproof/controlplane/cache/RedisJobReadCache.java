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
 * <h2>And a fourth: the backend is not called at all while it is down</h2>
 * A 50ms timeout per request is the <i>bounded</i> cost of a dead Redis, but it
 * is still a cost paid by every GET, and the connection pool pays it too. The
 * {@link JobCacheBreaker} in front of the backend turns consecutive failures into
 * an open breaker: the calls stop being made, the answers are the same
 * ("I have nothing" → the database answers), and the counters say which
 * happened — {@code specproof.cp.job.cache.breaker.calls} with
 * {@code state=short_circuited} counts the calls that were never made.
 * <p>Note what a short-circuit does NOT do: it does not increment the
 * {@code backend.ops result=error} counter. That counter answers "did the
 * backend fail?", and a short-circuit is the opposite of a failure — it is the
 * system deciding not to ask.
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
    private final JobCacheBreaker breaker;
    private final Counter hits;
    private final Counter misses;
    private final Counter errors;

    public RedisJobReadCache(StringRedisTemplate redis, ObjectMapper mapper, MeterRegistry meters) {
        this(redis, mapper, meters, new JobCacheBreaker(meters));
    }

    public RedisJobReadCache(StringRedisTemplate redis,
                             ObjectMapper mapper,
                             MeterRegistry meters,
                             JobCacheBreaker breaker) {
        this.redis = redis;
        this.mapper = mapper;
        this.breaker = breaker;
        this.hits = Counter.builder("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "hit").register(meters);
        this.misses = Counter.builder("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "miss").register(meters);
        this.errors = Counter.builder("specproof.cp.job.cache.backend.ops")
                .tag("backend", "redis").tag("result", "error").register(meters);
    }

    @Override
    public Optional<List<JobView>> getRecent() {
        return guarded("getRecent", () -> {
            String json = redis.opsForValue().get(JobCachePolicy.recentKey());
            if (json == null) {
                misses.increment();
                return Optional.empty();
            }
            hits.increment();
            return Optional.of(mapper.readValue(json, RECENT_TYPE));
        });
    }

    @Override
    public void putRecent(List<JobView> jobs) {
        guarded("putRecent", () -> {
            redis.opsForValue().set(
                    JobCachePolicy.recentKey(),
                    mapper.writeValueAsString(jobs),
                    JobCachePolicy.RECENT_TTL);
            return Optional.of(jobs);
        });
    }

    @Override
    public Optional<JobView> getJob(String id) {
        return guarded("getJob", () -> {
            String json = redis.opsForValue().get(JobCachePolicy.jobKey(id));
            if (json == null) {
                misses.increment();
                return Optional.empty();
            }
            hits.increment();
            return Optional.of(mapper.readValue(json, JobView.class));
        });
    }

    @Override
    public void putJob(JobView job) {
        guarded("putJob", () -> {
            Duration ttl = JobCachePolicy.ttlForStatus(job.status());
            redis.opsForValue().set(JobCachePolicy.jobKey(job.id()), mapper.writeValueAsString(job), ttl);
            return Optional.of(job);
        });
    }

    @Override
    public String backend() {
        return "redis";
    }

    /**
     * Run one backend call through the breaker.
     *
     * <p>Three outcomes, and the difference between them is the whole point:
     * the call went through and worked; the call went through and failed (the
     * backend is unhealthy — the breaker counts it); the call was never made
     * (the breaker is open — nothing failed, we simply stopped asking).</p>
     */
    private <T> Optional<T> guarded(String op, BackendCall<T> call) {
        if (!breaker.tryAcquire()) {
            // Short-circuited: the answer is "I have nothing", exactly what a
            // failing cache would have answered — but no round trip was paid.
            log.debug("job read cache {} skipped: the backend is short-circuited", op);
            return Optional.empty();
        }
        try {
            Optional<T> value = call.run();
            breaker.onSuccess();
            return value;
        } catch (Exception e) {
            breaker.onFailure(e);
            return failed(op, e);
        }
    }

    /**
     * One backend call. The checked exception is part of the contract because
     * the Jackson calls inside the lambdas throw it — and a backend call that
     * cannot say what went wrong is exactly what the breaker has to see.
     */
    @FunctionalInterface
    private interface BackendCall<T> {
        Optional<T> run() throws Exception;
    }

    /** Counts the failure, logs at debug (a dead cache must not flood the log), returns empty. */
    private <T> Optional<T> failed(String op, Exception e) {
        errors.increment();
        log.debug("job read cache {} failed; falling through to the database: {}", op, e.toString());
        return Optional.empty();
    }
}
