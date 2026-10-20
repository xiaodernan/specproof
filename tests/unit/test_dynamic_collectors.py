"""Dynamic state collector tests (Phase 3, P3-2/P3-3).

The collectors exist to replace one specific lie: treating "the code
called convertAndSend" (or "the code deletes the token") as proof that
the message was published (or the token was invalidated). These tests pin
the difference:

- an absent key is ABSENT, not an empty value;
- a present key with an empty value is PRESENT — a different state;
- a key that was never observed yields NO_EVIDENCE, not a clean run;
- a publish that RAISED is still recorded (it was attempted);
- a routing key typo with the same count is a DIFFERENT finding from a
  count change;
- the collector never decides the verdict.

No Redis, no RabbitMQ, no Docker: the dependencies are fakes.
"""

from __future__ import annotations

from typing import Any

import pytest

from experiments.collectors import (
    STATUS_AMBIGUOUS,
    STATUS_COMPLIANT,
    STATUS_NO_EVIDENCE,
    KeyState,
    RecordingPublisher,
    RedisStateCollector,
    compare_publish_observations,
)


class FakeRedis:
    """A Redis double: a dict of key → (value, ttl)."""

    def __init__(self, data: dict[str, tuple[str, int]] | None = None) -> None:
        self.data: dict[str, tuple[str, int]] = dict(data or {})
        self.unreadable: set[str] = set()

    def get(self, name: str) -> Any:
        if name in self.unreadable:
            raise RuntimeError("connection reset")
        entry = self.data.get(name)
        if entry is None:
            return None
        return entry[0].encode("utf-8")

    def ttl(self, name: str) -> int:
        entry = self.data.get(name)
        if entry is None:
            return -2
        return entry[1]


# ── Redis: what was observed ───────────────────────────────────────────────


class TestRedisObservation:
    def test_absent_key_is_absent_not_empty(self) -> None:
        collector = RedisStateCollector(FakeRedis())
        states = collector.snapshot(["missing"])
        state = states["missing"]
        assert state.present is False
        assert state.value is None
        assert state.ttl_seconds is None

    def test_present_key_captures_value_and_ttl(self) -> None:
        collector = RedisStateCollector(
            FakeRedis({"session:abc": ("token-value", 300)})
        )
        state = collector.snapshot(["session:abc"])["session:abc"]
        assert state.present is True
        assert state.value == "token-value"
        assert state.ttl_seconds == 300

    def test_present_key_with_empty_value_is_present(self) -> None:
        """'the key exists and holds an empty value' ≠ 'the key is gone'."""
        collector = RedisStateCollector(FakeRedis({"k": ("", 60)}))
        state = collector.snapshot(["k"])["k"]
        assert state.present is True
        assert state.value == ""

    def test_key_without_expiry_reports_no_ttl(self) -> None:
        collector = RedisStateCollector(FakeRedis({"k": ("v", -1)}))
        state = collector.snapshot(["k"])["k"]
        assert state.ttl_seconds is None

    def test_unreadable_key_does_not_abort_the_snapshot(self) -> None:
        redis = FakeRedis({"good": ("v", 10)})
        redis.unreadable.add("bad")
        collector = RedisStateCollector(redis)
        states = collector.snapshot(["good", "bad"])
        assert states["good"].present is True
        assert states["bad"].present is False

    def test_binary_value_is_present_with_a_byte_count(self) -> None:
        class BinaryRedis(FakeRedis):
            def get(self, name: str) -> Any:
                return b"\xff\xfe\x00binary"

        collector = RedisStateCollector(BinaryRedis())
        state = collector.snapshot(["blob"])["blob"]
        assert state.present is True
        assert "binary" in str(state.value)


# ── Redis: the comparison ──────────────────────────────────────────────────


class TestRedisComparison:
    def _collector(self) -> RedisStateCollector:
        return RedisStateCollector(FakeRedis())

    def test_unchanged_state_is_compliant(self) -> None:
        collector = self._collector()
        base = {"k": KeyState("k", True, "v", 10)}
        fragment = collector.fragment("exp-1", base, dict(base))
        assert fragment.status == STATUS_COMPLIANT
        assert fragment.comparison is not None
        assert fragment.comparison["changed_count"] == 0

    def test_disappeared_key_is_reported(self) -> None:
        collector = self._collector()
        base = {"k": KeyState("k", True, "v", 10)}
        head = {"k": KeyState("k", False)}
        comparison = collector.compare(base, head)
        assert comparison["changed_count"] == 1
        assert comparison["changed"][0]["change"] == "disappeared"

    def test_appeared_key_is_reported(self) -> None:
        collector = self._collector()
        base = {"k": KeyState("k", False)}
        head = {"k": KeyState("k", True, "v", 10)}
        comparison = collector.compare(base, head)
        assert comparison["changed"][0]["change"] == "appeared"

    def test_value_change_is_reported(self) -> None:
        collector = self._collector()
        base = {"k": KeyState("k", True, "v1", 10)}
        head = {"k": KeyState("k", True, "v2", 10)}
        comparison = collector.compare(base, head)
        assert comparison["changed"][0]["change"] == "value_changed"

    def test_ttl_change_is_reported_separately(self) -> None:
        """A shorter TTL is a different observation from a different value."""
        collector = self._collector()
        base = {"k": KeyState("k", True, "v", 300)}
        head = {"k": KeyState("k", True, "v", 60)}
        comparison = collector.compare(base, head)
        assert comparison["changed"][0]["change"] == "ttl_changed"

    def test_no_observation_is_no_evidence(self) -> None:
        """Nothing observed on either side is NOT a clean run."""
        collector = self._collector()
        fragment = collector.fragment("exp-1", {}, {})
        assert fragment.status == STATUS_NO_EVIDENCE
        assert fragment.confidence == 0.0
        assert fragment.extension["observed_any_key"] is False

    def test_a_change_is_ambiguous_not_a_verdict(self) -> None:
        """The collector reports the change; it does not decide the severity."""
        collector = self._collector()
        base = {"k": KeyState("k", True, "v", 10)}
        head = {"k": KeyState("k", False)}
        fragment = collector.fragment("exp-1", base, head)
        assert fragment.status == STATUS_AMBIGUOUS
        assert fragment.comparison is not None
        assert fragment.comparison["changed_count"] == 1


# ── RabbitMQ: what was actually published ──────────────────────────────────


class TestPublishObservation:
    def test_publish_is_recorded_with_routing_key_and_digest(self) -> None:
        publisher = RecordingPublisher()
        publisher.publish("email.changed", {"user": "u1"})
        observation = publisher.observation()
        assert observation["publish_count"] == 1
        assert observation["routing_keys"] == ["email.changed"]
        assert observation["payload_digests"][0].startswith("sha256:")

    def test_publish_count_is_ordered(self) -> None:
        publisher = RecordingPublisher()
        publisher.publish("a", {"n": 1})
        publisher.publish("b", {"n": 2})
        records = publisher.observation()["records"]
        assert [r["ordinal"] for r in records] == [1, 2]
        assert [r["routing_key"] for r in records] == ["a", "b"]

    def test_delegate_receives_the_publish(self) -> None:
        seen: list[tuple[str, dict[str, Any], str]] = []

        class Delegate:
            def publish(
                self, routing_key: str, payload: dict[str, Any], exchange: str = ""
            ) -> None:
                seen.append((routing_key, payload, exchange))

        publisher = RecordingPublisher(delegate=Delegate())
        publisher.publish("k", {"x": 1}, "ex")
        assert seen == [("k", {"x": 1}, "ex")]
        assert publisher.records[0].exchange == "ex"

    def test_a_failing_publish_is_recorded_and_reraised(self) -> None:
        """'attempted and failed' is not 'not attempted'."""
        class Failing:
            def publish(
                self, routing_key: str, payload: dict[str, Any], exchange: str = ""
            ) -> None:
                raise RuntimeError("broker down")

        publisher = RecordingPublisher(delegate=Failing())
        with pytest.raises(RuntimeError, match="broker down"):
            publisher.publish("k", {"x": 1})
        assert len(publisher.records) == 1
        assert publisher.observation()["failed_count"] == 1
        assert publisher.observation()["failures"][0]["error"]

    def test_no_publish_is_no_evidence(self) -> None:
        publisher = RecordingPublisher()
        fragment = publisher.fragment("exp-1")
        assert fragment.status == STATUS_NO_EVIDENCE
        assert fragment.confidence == 0.0

    def test_identical_sides_are_compliant(self) -> None:
        publisher = RecordingPublisher()
        publisher.publish("k", {"x": 1})
        fragment = publisher.fragment("exp-1")
        assert fragment.status == STATUS_COMPLIANT
        assert fragment.comparison is not None
        assert fragment.comparison["changed_count"] == 0


# ── RabbitMQ: the comparison ───────────────────────────────────────────────


class TestPublishComparison:
    def test_count_change_is_reported(self) -> None:
        comparison = compare_publish_observations(
            {"publish_count": 1, "routing_keys": ["k"], "payload_digests": ["d"]},
            {"publish_count": 2, "routing_keys": ["k"], "payload_digests": ["d", "d"]},
        )
        changes = [c["change"] for c in comparison["changed"]]
        assert "publish_count_changed" in changes

    def test_routing_key_typo_is_its_own_finding(self) -> None:
        """A typo with the same count is a DIFFERENT regression from a count."""
        comparison = compare_publish_observations(
            {"publish_count": 1, "routing_keys": ["email.changed"],
             "payload_digests": ["d"]},
            {"publish_count": 1, "routing_keys": ["email.change"],
             "payload_digests": ["d"]},
        )
        changes = {c["change"] for c in comparison["changed"]}
        assert "routing_key_missing" in changes
        assert "routing_key_added" in changes
        assert "publish_count_changed" not in changes

    def test_payload_change_is_reported(self) -> None:
        comparison = compare_publish_observations(
            {"publish_count": 1, "routing_keys": ["k"], "payload_digests": ["d1"]},
            {"publish_count": 1, "routing_keys": ["k"], "payload_digests": ["d2"]},
        )
        assert "payload_digests_changed" in {
            c["change"] for c in comparison["changed"]
        }

    def test_base_and_head_sides_are_compared(self) -> None:
        """One publish on base, two identical publishes on head.

        Two changes are reported, and both carry information: the count
        grew, and the payload digest list grew — the duplicate carried
        the SAME payload, which is exactly the shape of a consumer
        idempotency bug.
        """
        base = RecordingPublisher()
        base.publish("k", {"x": 1})
        head = RecordingPublisher()
        head.publish("k", {"x": 1})
        head.publish("k", {"x": 1})
        fragment = head.fragment("exp-1", base=base, head=head)
        assert fragment.comparison is not None
        changes = {c["change"] for c in fragment.comparison["changed"]}
        assert fragment.comparison["changed_count"] == 2
        assert "publish_count_changed" in changes
        assert "payload_digests_changed" in changes
        assert fragment.status == STATUS_AMBIGUOUS
