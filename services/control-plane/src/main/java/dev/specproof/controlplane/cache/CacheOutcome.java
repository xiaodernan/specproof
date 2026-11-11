package dev.specproof.controlplane.cache;

/**
 * A read result plus where it came from — the answer to "may I trust this for
 * the next two seconds?", which a bare DTO cannot answer.
 *
 * <p>The source is surfaced to clients as the {@code X-SpecProof-Cache} response
 * header. That is not decoration: an operator debugging "the dashboard shows
 * PREPARING but the CLI says VERIFIED" needs to know whether they are looking at
 * the database or at a five-second-old copy. Without the header the honest
 * answer ("it may be up to 5s stale") is invisible and the only remaining
 * explanation is "the product is wrong".</p>
 */
public record CacheOutcome<T>(T value, Source source) {

    public enum Source {
        /** Served from the cache; may be as stale as the TTL of that row's class. */
        HIT,
        /** Loaded from the database after a miss, and written back. */
        MISS,
        /** A concurrent request was already loading this key; this one shared its result. */
        COALESCED,
        /** The cache was unavailable; the database answered. Correct, just slower. */
        BYPASS
    }

    public String headerValue() {
        return source.name().toLowerCase(java.util.Locale.ROOT);
    }
}
