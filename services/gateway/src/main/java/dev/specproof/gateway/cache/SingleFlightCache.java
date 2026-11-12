package dev.specproof.gateway.cache;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Function;
import java.util.function.LongSupplier;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

/**
 * Single-flight + bounded LRU + TTL cache (#1637, performance leg).
 *
 * <p>Three classic structures/ideas in one place, each picked for an edge
 * concern the brief calls out — 算法 / 数据结构 / 适配硬件:</p>
 *
 * <ul>
 *   <li><b>Single-flight (coalescing)</b> — concurrent callers for the SAME key
 *       share ONE upstream call. Under a spike of identical reads (e.g. every
 *       client polling the same tenant list), the edge collapses them to a single
 *       control-plane hit instead of fanning out N. Implemented with
 *       {@code ConcurrentHashMap.computeIfAbsent} to claim the slot atomically,
 *       and {@code Mono.cache()} so every waiter shares one subscription.</li>
 *   <li><b>Bounded LRU</b> — results are kept in an access-ordered
 *       {@link LinkedHashMap} capped at {@code capacity}. The cap is the
 *       hardware-adaptation knob: memory use is O(capacity), never unbounded, so
 *       a busy edge cannot be driven OOM by its own cache. Eviction is the
 *       least-recently-used entry.</li>
 *   <li><b>TTL</b> — every entry carries an absolute expiry; a stale entry is
 *       treated as a miss and reloaded, so the edge never serves a value older
 *       than the operator's SLA window.</li>
 * </ul>
 *
 * <p>All hot paths are O(1) and the only lock guards a short critical section
 * (a map get/put) — never I/O — so it never parks the Netty event loop. Any
 * failure is contained by the caller (the filter treats a cache error as a
 * normal pass-through). The {@code now} supplier is injectable so expiry can be
 * driven deterministically in tests.</p>
 *
 * @param <K> cache key
 * @param <V> cached value
 */
public final class SingleFlightCache<K, V> {

    private final int capacity;
    private final long ttlMillis;
    private final LongSupplier now;

    private final ConcurrentHashMap<K, Mono<V>> inflight = new ConcurrentHashMap<>();
    private final ReentrantLock lock = new ReentrantLock();
    private final LinkedHashMap<K, CacheEntry<V>> store;

    public SingleFlightCache(int capacity, long ttlMillis) {
        this(capacity, ttlMillis, System::currentTimeMillis);
    }

    public SingleFlightCache(int capacity, long ttlMillis, LongSupplier now) {
        this.capacity = Math.max(1, capacity);
        this.ttlMillis = ttlMillis;
        this.now = now;
        this.store = new LinkedHashMap<K, CacheEntry<V>>(capacity + 1, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<K, CacheEntry<V>> eldest) {
                return size() > SingleFlightCache.this.capacity;
            }
        };
    }

    /**
     * Returns the cached value if present and unexpired, WITHOUT subscribing to
     * any loader. Used by the edge to short-circuit a cache hit synchronously
     * (no reactor hop) before deciding whether to call the upstream at all.
     */
    public Optional<V> getIfPresent(K key) {
        V v = peek(key);
        return v == null ? Optional.empty() : Optional.of(v);
    }

    /**
     * Resolves a value for {@code key}. Order of resolution:
     * <ol>
     *   <li>fresh value in the LRU (TTL-checked) — returned immediately;</li>
     *   <li>an in-flight computation for the same key — the SAME mono is
     *       returned, so concurrent callers coalesce onto one upstream call;</li>
     *   <li>otherwise the loader runs once, its result is stored (LRU + TTL),
     *       and the computation is removed from the in-flight map on terminal.</li>
     * </ol>
     */
    public Mono<V> get(K key, Function<K, Mono<V>> loader) {
        V cached = peek(key);
        if (cached != null) {
            return Mono.just(cached);
        }
        Mono<V> result = inflight.computeIfAbsent(key, k -> loader.apply(k)
                .doOnNext(v -> put(k, v))
                .doFinally(sig -> {
                    if (sig != SignalType.CANCEL) {
                        inflight.remove(k);
                    }
                })
                .cache());
        return result;
    }

    /** Number of values currently retained (for observability/tests). */
    public int size() {
        lock.lock();
        try {
            return store.size();
        } finally {
            lock.unlock();
        }
    }

    private V peek(K key) {
        lock.lock();
        try {
            CacheEntry<V> e = store.get(key);
            if (e == null) {
                return null;
            }
            if (e.expiresAt <= now.getAsLong()) {
                store.remove(key);
                return null;
            }
            return e.value;
        } finally {
            lock.unlock();
        }
    }

    private void put(K key, V value) {
        lock.lock();
        try {
            store.put(key, new CacheEntry<>(value, now.getAsLong() + ttlMillis));
        } finally {
            lock.unlock();
        }
    }

    private static final class CacheEntry<V> {
        private final V value;
        private final long expiresAt;

        CacheEntry(V value, long expiresAt) {
            this.value = value;
            this.expiresAt = expiresAt;
        }
    }
}
