package dev.specproof.gateway.ratelimit;

/**
 * The outcome of one token-bucket admission decision.
 *
 * <p>Immutable and cheap to construct; the reactive filter turns it into either a
 * pass-through to the upstream or a locally-written 429. Two singletons
 * ({@link #ALLOWED}, {@link #DENIED}) cover the Redis-unavailable fallbacks so a
 * downed cache never allocates a fresh object on the hot path.</p>
 */
public final class RateLimitResult {

    /** Redis answered "yes" with nothing else to report; also used for fail-open. */
    public static final RateLimitResult ALLOWED = new RateLimitResult(true, Long.MAX_VALUE, 0L);

    /** Redis answered "no", or the edge decided to deny on a Redis error (fail-closed). */
    public static final RateLimitResult DENIED = new RateLimitResult(false, 0L, 0L);

    private final boolean allowed;
    private final long remaining;
    private final long retryAfterMs;

    public RateLimitResult(boolean allowed, long remaining, long retryAfterMs) {
        this.allowed = allowed;
        this.remaining = remaining;
        this.retryAfterMs = retryAfterMs;
    }

    public boolean isAllowed() {
        return allowed;
    }

    public long getRemaining() {
        return remaining;
    }

    public long getRetryAfterMs() {
        return retryAfterMs;
    }
}
