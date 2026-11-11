"""Unit tests for the worker lease max-hold cap (§14.2).

The fake client executes the three lease scripts by their marker comment
(``-- specproof:acquire-lease`` / ``-- specproof:renew-lease`` / the
compare-and-delete release), so this file stays a *logic* test: it answers
"what do the lease rules say", not "does Redis run Lua" — the latter is
answered against a real server in
``tests/unit/test_redis_lease_atomicity.py``.
"""

from __future__ import annotations

from storage.redis import RedisStore


class FakeRedis:
    """Minimal dict-backed client for lease semantics."""

    def __init__(self) -> None:
        self.data: dict[str, tuple[str, float]] = {}
        self.now = 1000.0

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        ttl = self.now + ex if ex else None
        self.data[key] = (str(value), ttl)
        return True

    def get(self, key):
        entry = self.data.get(key)
        if entry is None:
            return None
        value, ttl = entry
        if ttl is not None and self.now >= ttl:
            del self.data[key]
            return None
        return value  # decode_responses=True: strings, not bytes

    def exists(self, key):
        return 1 if self.get(key) is not None else 0

    def expire(self, key, ttl):
        if key in self.data:
            value, _ttl = self.data[key]
            self.data[key] = (value, self.now + ttl)
        return 1

    def eval(self, script, numkeys, *args):
        keys = list(args[:numkeys])
        argv = list(args[numkeys:])
        if "specproof:acquire-lease" in script:
            return self._acquire(keys, argv)
        if "specproof:renew-lease" in script:
            return self._renew(keys, argv)
        if self.get(keys[0]) is not None and self.get(keys[0]) == argv[-1]:
            for k in keys:
                self.data.pop(k, None)
            return 1
        return 0

    def _acquire(self, keys, argv) -> int:
        worker_id, ttl, max_hold = argv[0], int(argv[1]), argv[2]
        if not self.set(keys[0], worker_id, nx=True, ex=ttl):
            return 0
        if max_hold != "":
            self.set(keys[1], "1")
            self.set(keys[2], worker_id, ex=int(max_hold))
        return 1

    def _renew(self, keys, argv) -> int:
        worker_id, ttl = argv[0], int(argv[1])
        if self.get(keys[0]) != worker_id:
            return 0
        if self.exists(keys[1]) == 1 and self.exists(keys[2]) == 0:
            return 0
        self.expire(keys[0], ttl)
        return 1


def _store() -> RedisStore:
    store = RedisStore()
    store._client = None
    fake = FakeRedis()

    # Bypass lazy connection: monkeypatch the client property at instance level.

    class _Store(RedisStore):
        @property
        def client(self):
            return fake

    return _Store(), fake


def test_legacy_acquire_renew_unlimited() -> None:
    store, fake = _store()
    assert store.acquire_lease("j1", "w1", ttl=30)
    for _ in range(5):
        assert store.renew_lease("j1", "w1", ttl=30)
    assert store.get_lease_owner("j1") == "w1"


def test_capped_lease_renews_within_window() -> None:
    store, fake = _store()
    assert store.acquire_lease("j1", "w1", ttl=30, max_hold_seconds=300)
    assert store.renew_lease("j1", "w1", ttl=30)
    assert store.get_lease_owner("j1") == "w1"


def test_capped_lease_refuses_renewal_after_max_hold() -> None:
    store, fake = _store()
    assert store.acquire_lease("j1", "w1", ttl=30, max_hold_seconds=300)
    fake.now += 301  # max-hold window expired
    assert store.renew_lease("j1", "w1", ttl=30) is False
    # The lease itself lapses on its own TTL shortly after — a wedged
    # worker can no longer extend it forever.


def test_release_cleans_marker_keys() -> None:
    store, fake = _store()
    assert store.acquire_lease("j1", "w1", ttl=30, max_hold_seconds=300)
    store.release_lease("j1", "w1")
    assert store.get_lease_owner("j1") is None
    assert fake.exists(store.lease_start_key("j1")) == 0
    assert fake.exists(store.lease_cap_flag_key("j1")) == 0


def test_other_worker_cannot_renew() -> None:
    store, fake = _store()
    assert store.acquire_lease("j1", "w1", ttl=30, max_hold_seconds=300)
    assert store.renew_lease("j1", "w2", ttl=30) is False


def test_acquire_writes_the_cap_markers_in_the_same_step() -> None:
    """The cap markers exist the moment the lease does.

    The pre-atomic shape wrote them in two follow-up round trips, so a crash
    between them left a lease whose cap marker was missing — and a lease
    without a cap marker is renewed forever (the max-hold guarantee gone
    exactly when the worker was unhealthy).
    """
    store, fake = _store()
    assert store.acquire_lease("j1", "w1", ttl=30, max_hold_seconds=300)
    assert fake.exists(store.lease_key("j1")) == 1
    assert fake.exists(store.lease_cap_flag_key("j1")) == 1
    assert fake.exists(store.lease_start_key("j1")) == 1
