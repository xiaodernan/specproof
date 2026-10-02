"""Worker outbox lane — the durable notification promise (#16.6-1).

The direct send (best-effort, in-process) loses the announcement when the
process dies between the accepted terminal write and the HTTP POST. On the
outbox lane (SPECPROOF_NOTIFY_OUTBOX=1) the BUILT notification rides the
terminal write itself via ``transition_job_status_with_notify`` — "the
verdict was accepted" and "this announcement is owed" become one durable
fact (K closure of §16.6-1). These tests pin the lane contract end to end:

* the flag is OFF by default — the historical direct path is untouched;
* the lane carries the built payload INSIDE the terminal transition and
  never builds a connector on this process (delivery is the relay's);
* the notifiable filter runs BEFORE the lane decision, counted once;
* a template/build failure on the lane degrades to a lost announcement
  (notify_error_total) without blocking the honest terminal write.
"""

from __future__ import annotations

import pytest

import agent.worker as worker_module
from integrations.notify.protocol import SendStatus
from tests.unit.test_worker_cancel_points import (
    _FakeGraph,
    _FakeMysql,
    _FakeRedis,
    _final_state,
    _make_worker,
)
from tests.unit.test_worker_notify_terminal import SUMMARY, RecordingConnector


def _delta(after: dict, before: dict, name: str) -> float:
    return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)


def _run_success(
    monkeypatch: pytest.MonkeyPatch, *, flag: bool,
) -> tuple[_FakeMysql, RecordingConnector | None, dict, dict]:
    """One full success run (VERIFIED).

    flag=True patches the connector factory with a tripwire: the outbox lane
    must never build a connector on this process. flag=False hands a
    recording connector so the direct lane's send is observable."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    mysql = _FakeMysql(status="RUNNING")
    graph = _FakeGraph(
        ["intake", "prepare_base", "publish_report"], _final_state(),
    )
    redis = _FakeRedis(lease_ok=True)
    worker = _make_worker(mysql, redis, graph, monkeypatch)
    connector: RecordingConnector | None = None
    import integrations.notify as notify_package

    if flag:
        monkeypatch.setenv("SPECPROOF_NOTIFY_OUTBOX", "1")

        def never_connector():  # pragma: no cover — asserted not called
            raise AssertionError("the outbox lane must not build a connector")

        monkeypatch.setattr(
            notify_package, "webhook_connector_from_env", never_connector
        )
    else:
        connector = RecordingConnector()
        monkeypatch.setattr(
            notify_package, "webhook_connector_from_env", lambda: connector
        )
    worker._handle_job_impl("job-ob", {"repo_path": "/r", "spec_path": "/s"})
    after = metrics_module.snapshot()
    return mysql, connector, before, after


def test_outbox_lane_rides_the_terminal_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mysql, connector, before, after = _run_success(monkeypatch, flag=True)
    assert connector is None

    terminal = [kw for t, kw in mysql.transitions if t == "VERIFIED"]
    assert len(terminal) == 1
    payload = terminal[0].get("notify_payload")
    assert payload is not None, "the intent must ride the terminal write"
    assert payload["event_type"] == "verification.verified"
    assert payload["job_id"] == "job-ob"
    # The enqueue counter lives in the REAL store method (the fake here only
    # records the ride-along) — asserted in test_job_state_machine.py.
    # The relay owns delivery; this process announced nothing directly.
    assert _delta(after, before, "notify_sent_total") == 0.0


def test_lane_off_keeps_the_direct_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mysql, connector, before, after = _run_success(monkeypatch, flag=False)
    assert connector is not None and len(connector.sent) == 1

    terminal = [kw for t, kw in mysql.transitions if t == "VERIFIED"]
    assert terminal[0].get("notify_payload", "absent") in (None, "absent")
    assert _delta(after, before, "notify_sent_total") == 1.0


def test_not_notifiable_skips_once_on_the_outbox_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CANCELLED has no template: the skip is counted ONCE (by the intent
    decider) and the caller must not run the direct lane on top of it."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    worker = worker_module.Worker.__new__(worker_module.Worker)
    worker.mysql = _FakeMysql(status="RUNNING")
    worker.worker_id = "w-ob"
    monkeypatch.setenv("SPECPROOF_NOTIFY_OUTBOX", "1")

    payload, handled = worker._notify_intent_for(
        "job-ob", "CANCELLED", {**SUMMARY, "verdict": "CANCELLED"}
    )
    after = metrics_module.snapshot()

    assert payload is None and handled is True
    assert _delta(after, before, "notify_skipped_total") == 1.0


def test_template_failure_degrades_to_lost_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A template/build failure on the lane is not transient: the intent
    degrades to a lost announcement (counted) and handled=True keeps the
    caller from double-announcing via the direct lane."""
    import integrations.notify as notify_package
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    monkeypatch.setenv("SPECPROOF_NOTIFY_OUTBOX", "1")
    monkeypatch.setattr(
        notify_package, "build_terminal_notification",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("template bug")),
    )
    worker = worker_module.Worker.__new__(worker_module.Worker)
    worker.mysql = _FakeMysql(status="RUNNING")
    worker.worker_id = "w-ob"

    payload, handled = worker._notify_intent_for(
        "job-ob", "VERIFIED", SUMMARY
    )
    after = metrics_module.snapshot()

    assert payload is None and handled is True
    assert _delta(after, before, "notify_error_total") == 1.0


def test_direct_lane_still_sends_through_the_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The direct lane keeps its own honest send accounting (#65 semantics):
    the connector's status feeds notify_<status>_total, nothing else."""
    import integrations.notify as notify_package
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    connector = RecordingConnector(SendStatus.SENT)
    monkeypatch.setattr(
        notify_package, "webhook_connector_from_env", lambda: connector,
    )
    worker = worker_module.Worker.__new__(worker_module.Worker)
    worker.mysql = _FakeMysql(status="RUNNING")
    worker.worker_id = "w-ob"
    worker._maybe_notify_terminal("job-ob", SUMMARY)
    after = metrics_module.snapshot()

    assert len(connector.sent) == 1
    assert _delta(after, before, "notify_sent_total") == 1.0
    assert _delta(after, before, "notify_error_total") == 0.0


def test_verdict_family_still_counts_on_the_outbox_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The outbox lane changes WHERE the announcement lives, not whether the
    run's verdict is counted: one terminal write still feeds the family."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()
    mysql, _never, _b2, after = _run_success(monkeypatch, flag=True)
    assert _delta(after, before, "jobs_verified_total") == 1.0
    assert any(t == "VERIFIED" for t, _kw in mysql.transitions)
