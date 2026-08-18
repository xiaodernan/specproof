"""P1.4 Unit tests: Redis Stream, lease, budget (logic tests)."""


from storage.redis import RedisConfig, RedisStore


class TestRedisConfig:
    def test_defaults(self):
        c = RedisConfig()
        assert c.host == "localhost"
        assert c.port == 6379
        assert c.password == "specproof_pass"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_HOST", "redis.internal")
        monkeypatch.setenv("REDIS_PORT", "6380")
        monkeypatch.setenv("REDIS_PASSWORD", "secret")
        c = RedisConfig.from_env()
        assert c.host == "redis.internal"
        assert c.port == 6380
        assert c.password == "secret"


class TestStreamKeyNaming:
    def test_stream_key_format(self):
        store = RedisStore()
        key = store.stream_key("abc123")
        assert key == "specproof:stream:job:abc123"

    def test_lease_key_format(self):
        store = RedisStore()
        key = store.lease_key("abc123")
        assert key == "specproof:lease:job:abc123"

    def test_budget_key_format(self):
        store = RedisStore()
        key = store.budget_key("abc123")
        assert key == "specproof:budget:job:abc123"


class TestLeaseLogic:
    """Lease lifecycle tests using FakeRedis."""

    def test_acquire_lease_succeeds_when_free(self, monkeypatch):
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return True  # acquired
        store = RedisStore()
        store._client = FakeRedis()
        assert store.acquire_lease("job-1", "worker-A")

    def test_acquire_lease_fails_when_held(self, monkeypatch):
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return False  # already held
        store = RedisStore()
        store._client = FakeRedis()
        assert not store.acquire_lease("job-1", "worker-B")

    def test_renew_lease_succeeds_for_owner(self, monkeypatch):
        class FakeRedis:
            def get(self, key):
                return "worker-A"  # matches
            def expire(self, key, ttl):
                return True
        store = RedisStore()
        store._client = FakeRedis()
        assert store.renew_lease("job-1", "worker-A")

    def test_renew_lease_fails_for_non_owner(self, monkeypatch):
        class FakeRedis:
            def get(self, key):
                return "worker-B"  # different owner
        store = RedisStore()
        store._client = FakeRedis()
        assert not store.renew_lease("job-1", "worker-A")

    def test_release_lease_lua_safety(self, monkeypatch):
        released = []
        class FakeRedis:
            def eval(self, script, numkeys, *args):
                key, owner = args
                released.append((key, owner))
                return 1
        store = RedisStore()
        store._client = FakeRedis()
        store.release_lease("job-1", "worker-A")
        assert ("specproof:lease:job:job-1", "worker-A") in released


class TestBudgetLogic:
    """Token budget tests using FakeRedis."""

    def test_init_budget(self, monkeypatch):
        class FakeRedis:
            def set(self, key, value, ex=None):
                assert value == "100000"
        store = RedisStore()
        store._client = FakeRedis()
        store.init_budget("job-1", 100000)

    def test_consume_budget_success(self, monkeypatch):
        class FakeRedis:
            def decrby(self, key, amount):
                return 99900  # remaining > 0
        store = RedisStore()
        store._client = FakeRedis()
        assert store.consume_budget("job-1", 100)

    def test_consume_budget_exceeded(self, monkeypatch):
        calls = []
        class FakeRedis:
            def decrby(self, key, amount):
                calls.append(("decrby", amount))
                return -10  # exceeded
            def incrby(self, key, amount):
                calls.append(("incrby", amount))
                return 0
        store = RedisStore()
        store._client = FakeRedis()
        assert not store.consume_budget("job-1", 100)
        assert ("decrby", 100) in calls
        assert ("incrby", 100) in calls  # rollback


class TestStreamLogic:
    """Stream progress tests using FakeRedis."""

    def test_xread_progress_returns_events(self, monkeypatch):
        class FakeRedis:
            def xread(self, streams, count=None):
                return [
                    ("specproof:stream:job:test", [
                        ("1638457600000-0", {
                            "node": "compile_contracts",
                            "status": "completed",
                            "at": "2026-07-10T12:00:00Z",
                            "percent": "20.0",
                            "message": "OK",
                        }),
                    ]),
                ]
            def expire(self, key, ttl):
                pass
            def xadd(self, key, data, maxlen=None):
                return "1638457600001-0"
        store = RedisStore()
        store._client = FakeRedis()
        events = store.xread_progress("test", "0", 10)
        assert len(events) == 1
        assert events[0]["node"] == "compile_contracts"
        assert events[0]["status"] == "completed"
        assert events[0]["percent"] == 20.0

    def test_xread_progress_empty_stream(self, monkeypatch):
        class FakeRedis:
            def xread(self, streams, count=None):
                return None
        store = RedisStore()
        store._client = FakeRedis()
        events = store.xread_progress("test", "0")
        assert events == []


class TestIdempotency:
    def test_set_idempotent_first_time(self, monkeypatch):
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return True
        store = RedisStore()
        store._client = FakeRedis()
        assert store.set_idempotent("evt-1")

    def test_set_idempotent_duplicate(self, monkeypatch):
        class FakeRedis:
            def set(self, key, value, nx=False, ex=None):
                return False  # already exists
        store = RedisStore()
        store._client = FakeRedis()
        assert not store.set_idempotent("evt-1")
