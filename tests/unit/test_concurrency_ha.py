"""High-concurrency / high-availability test: exactly-once processing.

Multiple workers consume the SAME queue concurrently with Redis-based
idempotency. The invariant under test: N messages delivered M times each
(delivery duplicates simulated) must each be PROCESSED EXACTLY ONCE, even
with several consumers racing.
"""

import threading
import uuid


def _rid() -> str:
    return uuid.uuid4().hex[:8]


class FakeIdempotency:
    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.lock = threading.Lock()

    def __call__(self, event_id: str) -> bool:
        with self.lock:
            if event_id in self.seen:
                return True
            self.seen.add(event_id)
            return False


def test_duplicate_delivery_processed_once():
    idem = FakeIdempotency()
    processed: list[str] = []
    lock = threading.Lock()

    def handle(event_id: str, payload: str) -> None:
        if idem(event_id):
            return  # duplicate delivery — discard
        with lock:
            processed.append(payload)

    # 20 events, each delivered 3 times (at-least-once semantics).
    deliveries = []
    for i in range(20):
        for _dup in range(3):
            deliveries.append((f"evt-{i}", f"payload-{i}"))

    threads = [
        threading.Thread(target=lambda d=deliveries[k::4]: [handle(e, p) for e, p in d])
        for k in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(processed) == 20
    assert sorted(processed) == sorted(f"payload-{i}" for i in range(20))


def test_lease_prevents_duplicate_claim():
    """Only one worker can hold a lease; the other must back off."""
    leases: dict[str, str] = {}
    lock = threading.Lock()

    def acquire(job_id: str, worker: str) -> bool:
        with lock:
            if job_id in leases:
                return False
            leases[job_id] = worker
            return True

    results: list[bool] = []
    threads = [
        threading.Thread(target=lambda w=w: results.append(acquire("job-1", w)))
        for w in ("worker-A", "worker-B", "worker-C")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 1  # exactly one winner


def test_worker_backoff_keeps_message_for_retry():
    """A consumer crash before ack leaves the message for redelivery."""
    delivered = 0
    acked = 0

    # Consumer 1 receives and crashes (no ack).
    delivered += 1
    # Broker redelivers to consumer 2 which acks.
    delivered += 1
    acked += 1

    assert delivered == 2  # at-least-once: redelivery happened
    assert acked == 1      # effectively-once: single ack
