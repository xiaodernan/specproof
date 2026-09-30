"""Worker outbox lane — the durable notification promise (#16.6-1).

The direct send (best-effort, in-process) loses the announcement when the
process dies between the accepted terminal write and the HTTP POST. The
outbox lane (SPECPROOF_NOTIFY_OUTBOX=1) instead persists the BUILT
notification in notify_outbox for storage.notify_relay to deliver
at-least-once. These tests pin the lane contract:

* the flag is OFF by default — the historical direct path is untouched;
* the lane ENQUEUES the built payload and never builds a connector
  (delivery is the relay's business, not this process's);
* an enqueue failure falls back to the direct send — losing the durable
  promise must not ALSO lose the immediate attempt;
* the notifiable filter runs BEFORE the lane decision (a verdict without
  a template is skipped on both lanes, with the same counter).
"""

from __future__ import annotations

from typing import Any

import pytest

import agent.worker as worker_module
from integrations.notify.protocol import (
    DisabledConnector,
    Notification,
    SendStatus,
)

from tests.unit.test_worker_notify_terminal import SUMMARY, RecordingConnector


class RecordingNotifyStore:
    """Records enqueued intents; raises on demand (enqueue failure path)."""

    def __init__(self, exc: BaseException | None = None) -> None:
        self.enqueued: list[tuple[str, str, dict[str, Any]]] = []
        self._exc = exc

    def enqueue_notify_intent(
        self, job_id: str, verdict: str, payload: dict[str, Any]
    ) -> None:
        if self._exc is not None:
            raise self._exc
        self.enqueued.append((job_id, verdict, payload))


def _announce(
    monkeypatch: pytest.MonkeyPatch,
    *,
    flag: bool,
    store: RecordingNotifyStore,
    connector: Any | None = None,
) -> tuple[dict, dict]:
    """Run one terminal announcement on the given lane."""
    import integrations.notify as notify_package
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    sink = connector if connector is not None else RecordingConnector()
    monkeypatch.setattr(
        notify_package, "webhook_connector_from_env", lambda: sink
    )
    if flag:
        monkeypatch.setenv("SPECPROOF_NOTIFY_OUTBOX", "1")
    worker = worker_module.Worker.__new__(worker_module.Worker)
    worker.mysql = store
    worker.worker_id = "w-outbox"
    worker._maybe_notify_terminal("job-ob", SUMMARY)
    return before, metrics_module.snapshot()


def _counter_delta(after: dict, before: dict, name: str) -> float:
    return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)


def test_lane_is_off_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No flag, no outbox row, direct send exactly as before."""
    from storage.notify_relay import notify_outbox_lane_enabled

    assert notify_outbox_lane_enabled() is False


def test_outbox_lane_enqueues_the_built_payload_and_never_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Delivery is the relay's business: the lane persists the payload the
    template suite built and builds NO connector on this process."""
    store = RecordingNotifyStore()
    before, after = _announce(monkeypatch, flag=True, store=store)

    assert len(store.enqueued) == 1
    job_id, verdict, payload = store.enqueued[0]
    assert job_id == "job-ob"
    assert verdict == "VERIFIED"
    assert payload["event_type"] == "verification.verified"
    assert payload["job_id"] == "job-ob"
    assert payload["text"]
    assert _counter_delta(after, before, "notify_outbox_enqueued_total") == 1.0
    assert _counter_delta(after, before, "notify_sent_total") == 0.0


def test_enqueue_failure_falls_back_to_direct_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing the durable promise must not ALSO lose the announcement."""
    store = RecordingNotifyStore(exc=RuntimeError("mysql down"))
    connector = RecordingConnector()
    before, after = _announce(
        monkeypatch, flag=True, store=store, connector=connector,
    )

    assert store.enqueued == []
    assert len(connector.sent) == 1
    assert _counter_delta(
        after, before, "notify_outbox_enqueue_failed_total"
    ) == 1.0
    assert _counter_delta(after, before, "notify_sent_total") == 1.0


def test_notifiable_filter_runs_before_the_lane_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verdict without a template is skipped on both lanes, loudly."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    store = RecordingNotifyStore()
    worker = worker_module.Worker.__new__(worker_module.Worker)
    worker.mysql = store
    worker.worker_id = "w-outbox"
    monkeypatch.setenv("SPECPROOF_NOTIFY_OUTBOX", "1")
    worker._maybe_notify_terminal("job-ob", {**SUMMARY, "verdict": "CANCELLED"})
    after = metrics_module.snapshot()

    assert store.enqueued == []
    assert _counter_delta(after, before, "notify_skipped_total") == 1.0


def test_unconfigured_receiver_on_the_outbox_lane_still_enqueues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No webhook configured: the intent is still durable — the relay will
    dead-letter it honestly instead of the enqueue pretending nothing was
    owed. (The relay's DISABLED handling is pinned in test_notify_relay.py.)"""
    store = RecordingNotifyStore()
    before, after = _announce(
        monkeypatch, flag=True, store=store,
        connector=DisabledConnector(),
    )

    assert len(store.enqueued) == 1
    assert _counter_delta(after, before, "notify_outbox_enqueued_total") == 1.0
