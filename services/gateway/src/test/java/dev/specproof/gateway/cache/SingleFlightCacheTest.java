package dev.specproof.gateway.cache;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;

/**
 * The three guarantees the edge relies on: single-flight coalescing, bounded LRU
 * eviction, and TTL expiry.
 */
class SingleFlightCacheTest {

    @Test
    void concurrentCallersForTheSameKeyCollapseToOneLoaderRun() {
        AtomicInteger runs = new AtomicInteger();
        AtomicLong clock = new AtomicLong(0);
        SingleFlightCache<String, String> cache = new SingleFlightCache<>(16, 10_000, clock::get);

        Mono<String> a = cache.get("k", k -> Mono.fromCallable(() -> {
            runs.incrementAndGet();
            return "v";
        }).delayElement(java.time.Duration.ofMillis(20)));
        Mono<String> b = cache.get("k", k -> Mono.fromCallable(() -> {
            runs.incrementAndGet();
            return "v";
        }).delayElement(java.time.Duration.ofMillis(20)));

        Mono.when(a, b).block();
        // Both subscribers share the SAME in-flight mono, so the loader runs once.
        assertThat(runs.get()).isEqualTo(1);
        assertThat(cache.getIfPresent("k")).contains("v");
    }

    @Test
    void lruEvictsTheLeastRecentlyUsedWhenOverCapacity() {
        AtomicLong clock = new AtomicLong(0);
        SingleFlightCache<String, String> cache = new SingleFlightCache<>(2, 10_000, clock::get);

        cache.get("a", k -> Mono.just("A")).block();
        cache.get("b", k -> Mono.just("B")).block();
        cache.get("c", k -> Mono.just("C")).block();

        assertThat(cache.size()).isEqualTo(2);
        // 'a' is the least recently used -> evicted; 'c' is the newest -> kept.
        assertThat(cache.getIfPresent("a")).isEmpty();
        assertThat(cache.getIfPresent("c")).contains("C");
    }

    @Test
    void expiredEntriesAreTreatedAsMisses() {
        AtomicInteger runs = new AtomicInteger();
        AtomicLong clock = new AtomicLong(1_000);
        SingleFlightCache<String, String> cache = new SingleFlightCache<>(8, 50, clock::get);

        cache.get("a", k -> Mono.fromCallable(() -> "v" + runs.incrementAndGet())).block();
        assertThat(cache.getIfPresent("a")).contains("v1");

        // Advance past the 50ms TTL.
        clock.addAndGet(100);
        assertThat(cache.getIfPresent("a")).isEmpty();

        // Next resolve reloads from the loader (runs again).
        cache.get("a", k -> Mono.fromCallable(() -> "v" + runs.incrementAndGet())).block();
        assertThat(runs.get()).isEqualTo(2);
    }

    @Test
    void getIfPresentReturnsEmptyWhenAbsent() {
        SingleFlightCache<String, String> cache = new SingleFlightCache<>(8, 10_000);
        assertThat(cache.getIfPresent("missing")).isEmpty();
    }
}
