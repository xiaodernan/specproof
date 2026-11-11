package dev.specproof.controlplane.cache;

import java.time.Duration;
import java.util.Set;

/**
 * Keys, and how long a cached row may be wrong.
 *
 * <h2>Why a TTL policy instead of invalidation</h2>
 * This control plane is a READ-ONLY projection of {@code verification_jobs}: the
 * table is written by the Python agent runtime, not by this process (see
 * {@code VerificationJobView}). There is therefore no write path here that could
 * push an invalidation, and pretending otherwise — e.g. invalidating on a local
 * write that never happens — would be a cache that lies about its freshness
 * budget. What this process CAN do is bound the lie: every entry carries an
 * expiry, and the expiry is chosen from the mutability class of the row.
 *
 * <h2>The two mutability classes</h2>
 * <ul>
 *   <li><b>Terminal</b> ({@link #TERMINAL_STATUSES}): a job that has reached one
 *       of these never changes again in this projection. Caching it for
 *       {@link #TERMINAL_TTL} costs nothing in correctness — the only waste is
 *       one Redis key.</li>
 *   <li><b>In flight</b> (anything else, including an unknown status): the runtime
 *       advances stages as the pipeline walks its nodes, so a cached copy is
 *       stale the moment it is written. {@link #IN_FLIGHT_TTL} is deliberately
 *       short (seconds, not minutes) — long enough to collapse the SPA's polling
 *       fan-out, short enough that an operator watching a stage advance does not
 *       see a frozen row.</li>
 * </ul>
 *
 * <p>Unknown statuses fall into the in-flight class on purpose: a status this
 * version has never heard of is a status this version cannot prove is final.</p>
 *
 * <h2>Why the key carries a version</h2>
 * The value is JSON of {@link JobView}. Add a field to that record and every old
 * value deserializes with the new field {@code null} — a silent lie rather than an
 * error. Bumping {@link #KEY_PREFIX} to {@code v2} orphans the old keys, which
 * then expire on their own. Cheap, and it makes the break explicit.
 */
public final class JobCachePolicy {

    /** Bump when {@link JobView} changes shape. Old keys expire; no migration. */
    public static final String KEY_PREFIX = "cp:jobcache:v1:";

    /** Terminal rows cannot change in this projection; keep them a while. */
    public static final Duration TERMINAL_TTL = Duration.ofMinutes(5);

    /**
     * In-flight rows change as the runtime walks the pipeline. Five seconds is
     * the outermost bound: the SPA polls every 2s, so a 5s entry still collapses
     * the fan-out of concurrent tabs while keeping a visible staleness ceiling.
     */
    public static final Duration IN_FLIGHT_TTL = Duration.ofSeconds(5);

    /** The recent-50 list can contain in-flight rows, so it inherits their bound. */
    public static final Duration RECENT_TTL = IN_FLIGHT_TTL;

    /**
     * Statuses after which this projection never changes again. Kept lowercase
     * comparison-safe in {@link #isTerminal(String)}; the values are the ones the
     * runtime writes (see the Job state machine in
     * {@code docs/architecture/domain-model.md}).
     */
    public static final Set<String> TERMINAL_STATUSES = Set.of(
            "VERIFIED", "BLOCKED", "FAILED", "CANCELLED", "EXPIRED", "STALE");

    private JobCachePolicy() {
    }

    public static String jobKey(String id) {
        return KEY_PREFIX + "job:" + id;
    }

    public static String recentKey() {
        return KEY_PREFIX + "jobs:recent";
    }

    public static boolean isTerminal(String status) {
        return status != null && TERMINAL_STATUSES.contains(status.trim().toUpperCase());
    }

    public static Duration ttlForStatus(String status) {
        return isTerminal(status) ? TERMINAL_TTL : IN_FLIGHT_TTL;
    }
}
