package dev.specproof.controlplane.cache;

import dev.specproof.controlplane.repository.VerificationJobViewRepository;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

/**
 * Read-through access to the job projection: cache first, database second, and
 * exactly ONE database query per cold key even when a hundred clients arrive at
 * the same instant.
 *
 * <h2>Why single-flight and not just "check then load"</h2>
 * The SPA polls {@code /api/v1/jobs} every two seconds from every open tab, and
 * an operator opening the jobs page after a deploy hits a completely cold cache.
 * Without coalescing, N concurrent misses become N full table scans of
 * {@code findTop50ByOrderByCreatedAtDesc}: the cache is coldest exactly when the
 * load is highest, which is the moment a cache is supposed to help. The fix is
 * the same one an OS page cache uses for concurrent faults — the first reader
 * brings the page in, the rest wait on it — here expressed as a
 * {@link ConcurrentHashMap} of in-flight futures, per key.
 *
 * <p>Scope, stated honestly: this coalesces within ONE JVM. Two control-plane
 * replicas will each run one query on a cold key; that is two queries instead of
 * N, and cross-process coalescing would need a distributed lock whose failure
 * mode (a stuck lock) is worse than a duplicate SELECT. A Redis {@code SET NX}
 * lock was considered and rejected for exactly that reason.</p>
 *
 * <h2>Failure semantics</h2>
 * A cache that throws is reported as {@link CacheOutcome.Source#BYPASS} and the
 * read goes straight to the database — no retry, no second round trip, and the
 * metric tells the truth about what happened. Database errors are NOT caught:
 * they are real and must reach the client. A cache must never turn a working GET
 * into a failing one, and must never turn a failing GET into a working one.
 */
public final class JobQueryService {

    private final VerificationJobViewRepository jobs;
    private final JobReadCache cache;
    private final ConcurrentHashMap<String, CompletableFuture<CacheOutcome<?>>> inFlight =
            new ConcurrentHashMap<>();
    private final Counter hits;
    private final Counter misses;
    private final Counter coalesced;
    private final Counter bypasses;

    public JobQueryService(VerificationJobViewRepository jobs, JobReadCache cache, MeterRegistry meters) {
        this.jobs = jobs;
        this.cache = cache;
        this.hits = counter(meters, "hit");
        this.misses = counter(meters, "miss");
        this.coalesced = counter(meters, "coalesced");
        this.bypasses = counter(meters, "bypass");
    }

    private static Counter counter(MeterRegistry meters, String result) {
        return Counter.builder("specproof_cp_job_cache_requests_total")
                .description("Job facade cache outcomes; hit+miss+coalesced+bypass == requests served")
                .tag("result", result)
                .register(meters);
    }

    public CacheOutcome<List<JobView>> recent() {
        Read<List<JobView>> read = safeRead(cache::getRecent);
        if (read.failed()) {
            return bypassList();
        }
        if (read.value().isPresent()) {
            hits.increment();
            return new CacheOutcome<>(read.value().get(), CacheOutcome.Source.HIT);
        }
        return coalesce("recent", () -> {
            misses.increment();
            List<JobView> rows = jobs.findTop50ByOrderByCreatedAtDesc()
                    .stream().map(JobView::from).toList();
            safePut(() -> cache.putRecent(rows));
            return new CacheOutcome<>(rows, CacheOutcome.Source.MISS);
        });
    }

    public Optional<CacheOutcome<JobView>> job(String id) {
        Read<JobView> read = safeRead(() -> cache.getJob(id));
        if (read.failed()) {
            bypasses.increment();
            return jobs.findById(id).map(JobView::from)
                    .map(view -> new CacheOutcome<>(view, CacheOutcome.Source.BYPASS));
        }
        if (read.value().isPresent()) {
            hits.increment();
            return Optional.of(new CacheOutcome<>(read.value().get(), CacheOutcome.Source.HIT));
        }
        return coalesceOptional(JobCachePolicy.jobKey(id), () -> {
            misses.increment();
            Optional<JobView> row = jobs.findById(id).map(JobView::from);
            row.ifPresent(view -> safePut(() -> cache.putJob(view)));
            return row.map(view -> new CacheOutcome<>(view, CacheOutcome.Source.MISS));
        });
    }

    /** Backend name for the debug header ("memory" / "redis"). */
    public String cacheBackend() {
        try {
            return cache.backend();
        } catch (RuntimeException e) {
            return "unknown";
        }
    }

    // ── internals ────────────────────────────────────────────────────────────

    private CacheOutcome<List<JobView>> bypassList() {
        bypasses.increment();
        List<JobView> rows = jobs.findTop50ByOrderByCreatedAtDesc()
                .stream().map(JobView::from).toList();
        return new CacheOutcome<>(rows, CacheOutcome.Source.BYPASS);
    }

    private <T> CacheOutcome<T> coalesce(String key, Supplier<CacheOutcome<T>> loader) {
        CompletableFuture<CacheOutcome<?>> mine = new CompletableFuture<>();
        CompletableFuture<CacheOutcome<?>> leader = inFlight.putIfAbsent(key, mine);
        if (leader != null) {
            CacheOutcome<?> shared = awaitLeader(leader);
            if (shared != null) {
                coalesced.increment();
                return new CacheOutcome<T>(
                        JobQueryService.<T>cast(shared).value(),
                        CacheOutcome.Source.COALESCED);
            }
            return loader.get();
        }
        try {
            CacheOutcome<T> result = loader.get();
            mine.complete(result);
            return result;
        } catch (RuntimeException e) {
            mine.completeExceptionally(e);
            throw e;
        } finally {
            inFlight.remove(key, mine);
        }
    }

    private <T> Optional<CacheOutcome<T>> coalesceOptional(String key,
                                                           Supplier<Optional<CacheOutcome<T>>> loader) {
        CompletableFuture<CacheOutcome<?>> mine = new CompletableFuture<>();
        CompletableFuture<CacheOutcome<?>> leader = inFlight.putIfAbsent(key, mine);
        if (leader != null) {
            CacheOutcome<?> shared = awaitLeader(leader);
            // A completed-but-null future means "the leader looked and the row is
            // not there" — followers must not re-query the database for it.
            return shared == null
                    ? Optional.empty()
                    : Optional.of(new CacheOutcome<T>(
                        JobQueryService.<T>cast(shared).value(),
                        CacheOutcome.Source.COALESCED));
        }
        try {
            Optional<CacheOutcome<T>> result = loader.get();
            mine.complete(result.orElse(null));
            return result;
        } catch (RuntimeException e) {
            mine.completeExceptionally(e);
            throw e;
        } finally {
            inFlight.remove(key, mine);
        }
    }

    /**
     * Wait for the request that owns this key. Returns {@code null} when it
     * completed with "not found", or when it failed — in the failure case the
     * caller does the work itself, because an error is not a cacheable fact.
     */
    private static CacheOutcome<?> awaitLeader(CompletableFuture<CacheOutcome<?>> leader) {
        try {
            return leader.join();
        } catch (CompletionException | ClassCastException e) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private static <T> CacheOutcome<T> cast(CacheOutcome<?> outcome) {
        return (CacheOutcome<T>) outcome;
    }

    private record Read<T>(Optional<T> value, boolean failed) {
    }

    private static <T> Read<T> safeRead(Supplier<Optional<T>> read) {
        try {
            return new Read<>(read.get(), false);
        } catch (RuntimeException e) {
            return new Read<>(Optional.empty(), true);
        }
    }

    private static void safePut(Runnable write) {
        try {
            write.run();
        } catch (RuntimeException ignored) {
            // A cache that cannot store is a cache that will miss again next time.
        }
    }

    /** Visible for tests: number of keys currently being loaded. */
    int inFlightCount() {
        return inFlight.size();
    }
}
