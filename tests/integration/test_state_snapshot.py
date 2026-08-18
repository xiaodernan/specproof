"""P3 Differential Lab tests — full-stack state snapshots (live infra, skip-safe)."""

import uuid

import pytest

from experiments.state_snapshot import (
    capture_full_stack,
    capture_redis_state,
    diff_states,
    render_diff_report,
)
from storage.mysql import MySQLStore
from storage.rabbitmq import RabbitMQClient
from storage.redis import RedisStore


@pytest.fixture()
def infra():
    mysql = MySQLStore()
    redis = RedisStore()
    rabbitmq = RabbitMQClient()
    try:
        mysql.ensure_tables()
        redis.is_ready()
    except Exception:
        pytest.skip("infrastructure not available")
    return mysql, redis, rabbitmq


def test_redis_snapshot_captures_keys_and_ttl(infra):
    _mysql, redis, _rmq = infra
    key = "specproof:snapshot-test:" + uuid.uuid4().hex[:8]
    redis.client.set(key, "v1", ex=60)
    snap = capture_redis_state(redis, pattern=key)
    assert key in snap["keys"]
    assert snap["keys"][key]["value"] == "v1"
    assert 0 < snap["keys"][key]["ttl"] <= 60
    redis.client.delete(key)


def test_redis_diff_detects_change_and_expiry(infra):
    _mysql, redis, _rmq = infra
    key = "specproof:snapshot-test:" + uuid.uuid4().hex[:8]
    redis.client.set(key, "before", ex=60)
    base = capture_redis_state(redis, pattern=key)
    redis.client.set(key, "after", ex=60)
    head = capture_redis_state(redis, pattern=key)
    diff = diff_states(
        {"mysql": {}, "redis": base, "rabbitmq": {}},
        {"mysql": {}, "redis": head, "rabbitmq": {}},
    )
    changed = diff["redis"]["changed"]
    assert any(c["key"] == key and c["to"]["value"] == "after" for c in changed)
    redis.client.delete(key)


def test_full_stack_snapshot_and_report(infra):
    mysql, redis, rabbitmq = infra
    snap = capture_full_stack(
        mysql, redis, rabbitmq,
        mysql_tables=["verification_jobs"],
        redis_pattern="specproof:snapshot-*",
        rabbit_queues=["q.p1.verify.job"],
    )
    assert "mysql" in snap and "redis" in snap and "rabbitmq" in snap
    report = render_diff_report(diff_states(snap, snap))
    assert "Full-Stack Differential Report" in report


def test_diff_marks_incomplete_subsystem():
    base = {"mysql": {}, "redis": {"error": "down"}, "rabbitmq": {"_connection_error": "x"}}
    head = {"mysql": {}, "redis": {"error": "down"}, "rabbitmq": {"_connection_error": "x"}}
    diff = diff_states(base, head)
    assert "redis" in diff["incomplete"]
    assert "rabbitmq" in diff["incomplete"]
