"""Worker -> outbound terminal notification (#65 wiring).

`integrations/notify/` shipped a webhook connector, three payload dialects and
a template suite with green unit tests — and zero production call sites, which
is the exact shape of "looks wired because it is covered". These tests pin the
wiring itself, in the order the product problem actually asks about:

* which verdicts may leave the process (the four the templates can render),
* what happens to a terminal verdict that has no template (explicit skip +
  counter — NOT a swallowed ValueError that would read as "sent"),
* that an unconfigured deployment says so out loud instead of silently
  pretending a notification went out,
* that nothing about delivery can change the durable record.
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

SUMMARY: dict[str, Any] = {
    "verdict": "VERIFIED",
    "contracts_total": 4,
    "matrix_passed": 4,
    "matrix_failed": 0,
    "matrix_unverified": 0,
    "findings": [],
    "capsules": [],
}


class RecordingConnector:
    """A connector that records what reached it instead of posting anywhere."""

    def __init__(
        self,
        status: SendStatus = SendStatus.SENT,
        exc: BaseException | None = None,
    ) -> None:
        self.name = "recording"
        self.capabilities = frozenset()
        self.sent: list[Notification] = []
        self.closed = 0
        self._status = status
        self._exc = exc

    def send(self, notification: Notification) -> SendStatus:
        if self._exc is not None:
            raise self._exc
        self.sent.append(notification)
        return self._status

    def close(self) -> None:
        self.closed += 1


def _send(
    monkeypatch: pytest.MonkeyPatch,
    verdict: str,
    summary: dict[str, Any] | None = None,
    connector: Any | None = None,
) -> tuple[dict, dict, Any]:
    """Run one terminal announcement; return (metrics before, after, connector).

    The connector is patched once, here, so every assertion below reads the
    same instance the worker actually used.
    """
    import integrations.notify as notify_package
    from observability import metrics as metrics_module

    sink = connector if connector is not None else RecordingConnector()
    monkeypatch.setattr(
        notify_package, "webhook_connector_from_env", lambda *a, **kw: sink
    )
    before = metrics_module.snapshot()
    # __new__ skips the bootstrap-heavy __init__; this path needs no store.
    worker_module.Worker.__new__(worker_module.Worker)._maybe_notify_terminal(
        "job-1", {**(summary or SUMMARY), "verdict": verdict}
    )
    return before, metrics_module.snapshot(), sink


def _delta(before: dict, after: dict, name: str) -> float:
    return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)


def _counter(before: dict, after: dict, **values: float) -> None:
    """Assert several notify counters at once, so none is quietly omitted."""
    for name, expected in values.items():
        assert _delta(before, after, name) == expected, name


# --- the four verdicts the templates can actually render ---------------------


@pytest.mark.parametrize(
    "verdict,event_type",
    [
        ("VERIFIED", "verification.verified"),
        ("BLOCKED", "verification.blocked"),
        ("FAILED", "verification.failed"),
        ("NEEDS_REVIEW", "verification.needs_review"),
    ],
)
def test_each_templateable_verdict_sends_one_notification(
    monkeypatch: pytest.MonkeyPatch, verdict: str, event_type: str
) -> None:
    before, after, connector = _send(monkeypatch, verdict)
    (notification,) = connector.sent
    assert notification.event_type == event_type
    assert notification.job_id == "job-1"
    _counter(before, after, notify_sent_total=1.0, notify_skipped_total=0.0)


def test_cli_spelling_of_needs_review_reaches_the_wire_as_one_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"NEEDS REVIEW (verification incomplete)" is the same terminal fact."""
    _before, _after, connector = _send(
        monkeypatch, "NEEDS REVIEW (verification incomplete)"
    )
    (notification,) = connector.sent
    assert notification.event_type == "verification.needs_review"
    assert "Verdict: NEEDS_REVIEW" in notification.text


# --- verdicts with no template: explicit skip, never a swallowed error ------


@pytest.mark.parametrize(
    "verdict", ["CANCELLED", "ERROR", "STALE", "TELEPORTED", ""]
)
def test_a_verdict_without_a_template_is_skipped_loudly(
    monkeypatch: pytest.MonkeyPatch, verdict: str
) -> None:
    """CANCELLED / ERROR / STALE are real terminal rows (storage/mysql.py).

    The templates refuse to invent an event for them (ValueError by design), so
    a bare try/except on the whole body would delete the notification AND the
    fact that it was deleted. The skip has to be a decision with a name and a
    counter, logged with the job it declined.
    """
    before, after, connector = _send(monkeypatch, verdict)
    assert connector.sent == []
    _counter(
        before,
        after,
        notify_skipped_total=1.0,
        notify_sent_total=0.0,
        notify_failed_total=0.0,
        notify_error_total=0.0,
    )


def test_the_skip_says_which_job_and_which_verdict(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import integrations.notify as notify_package

    sink = RecordingConnector()
    monkeypatch.setattr(
        notify_package, "webhook_connector_from_env", lambda *a, **kw: sink
    )
    with caplog.at_level("INFO", logger="agent.worker"):
        worker_module.Worker.__new__(worker_module.Worker)._maybe_notify_terminal(
            "job-9", {**SUMMARY, "verdict": "CANCELLED"}
        )
    assert sink.sent == []
    assert "job-9" in caplog.text
    assert "CANCELLED" in caplog.text


def test_notifiable_predicate_and_templates_cannot_drift_apart() -> None:
    """The gate the worker trusts and the templates it feeds must agree.

    If `notifiable` accepted something the builder then refused, the worker
    would count a send that never happened; if it refused something the
    templates could render, a real terminal event would go unannounced.
    """
    from integrations.notify import TERMINAL_VERDICTS, notifiable

    for verdict in sorted(TERMINAL_VERDICTS):
        assert notifiable(verdict), verdict
        assert notifiable(verdict.lower()), verdict
    assert notifiable("NEEDS REVIEW (verification incomplete)")
    for verdict in ("CANCELLED", "ERROR", "STALE", "RUNNING", "", "  "):
        assert not notifiable(verdict), verdict


# --- unconfigured deployment: the probe for "wired but silent" --------------


def test_unconfigured_deployment_counts_disabled_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """notify_disabled_total is the counter that catches a half-installed box.

    A deployment with no webhook URL is legitimate; one that looks configured
    and delivers nothing is not. The two must stay tellable-after-the-fact, so
    the disabled answer is counted rather than dropped.
    """
    from observability import metrics as metrics_module

    monkeypatch.delenv("SPECPROOF_NOTIFY_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SPECPROOF_NOTIFY_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("SPECPROOF_NOTIFY_WEBHOOK_KIND", raising=False)
    before = metrics_module.snapshot()
    worker_module.Worker.__new__(worker_module.Worker)._maybe_notify_terminal(
        "job-1", SUMMARY
    )
    after = metrics_module.snapshot()
    _counter(
        before, after, notify_disabled_total=1.0, notify_sent_total=0.0
    )


def test_disabled_connector_can_be_closed_like_any_connector() -> None:
    """The worker closes whatever the factory handed back, unconditionally."""
    assert DisabledConnector().close() is None


# --- delivery problems cannot touch the record ------------------------------


def test_a_rejected_send_is_counted_as_failed_not_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before, after, connector = _send(
        monkeypatch, "VERIFIED", connector=RecordingConnector(SendStatus.FAILED)
    )
    assert len(connector.sent) == 1  # it tried; the receiver said no
    _counter(before, after, notify_failed_total=1.0, notify_sent_total=0.0)


def test_a_disabled_send_is_counted_as_disabled_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A no-op connector is a configuration fact, not a delivery failure."""
    before, after, connector = _send(
        monkeypatch, "VERIFIED", connector=RecordingConnector(SendStatus.DISABLED)
    )
    assert len(connector.sent) == 1
    _counter(
        before,
        after,
        notify_disabled_total=1.0,
        notify_failed_total=0.0,
        notify_sent_total=0.0,
    )


def test_a_raising_connector_never_escapes_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An optional integration must not flip a job that already reached its
    honest terminal state — the same envelope the GitHub Check Run lives in."""
    before, after, _connector = _send(
        monkeypatch, "VERIFIED", connector=RecordingConnector(exc=RuntimeError("down"))
    )
    _counter(
        before,
        after,
        notify_error_total=1.0,
        notify_sent_total=0.0,
        notify_failed_total=0.0,
    )


def test_a_misconfigured_factory_never_escapes_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The connector is built per job, so its configuration errors are too."""
    import integrations.notify as notify_package
    from observability import metrics as metrics_module

    def _boom(*_a: Any, **_kw: Any) -> Any:
        raise ValueError("no webhook url")

    monkeypatch.setattr(notify_package, "webhook_connector_from_env", _boom)
    before = metrics_module.snapshot()
    worker_module.Worker.__new__(worker_module.Worker)._maybe_notify_terminal(
        "job-1", SUMMARY
    )
    after = metrics_module.snapshot()
    _counter(before, after, notify_error_total=1.0, notify_sent_total=0.0)


def test_the_connector_is_released_after_every_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker is a long-lived process.

    The factory returns a connector that owns an HTTP client, so a notify path
    that never closed it would leak one client per finished job — invisible in
    a unit test, permanent in production.
    """
    ok = RecordingConnector()
    _send(monkeypatch, "VERIFIED", connector=ok)
    assert ok.closed == 1

    bad = RecordingConnector(exc=RuntimeError("down"))
    _send(monkeypatch, "VERIFIED", connector=bad)
    assert bad.closed == 1


# --- the two outward renderers must agree on one summary --------------------


def test_a_summary_with_no_counts_says_not_counted_out_loud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parity with #64: the notification reads the SAME summary object.

    `_failure_summary` deliberately carries no count keys, so the outbound text
    must report "not counted" instead of the literal zeros this call site used
    to invent for GitHub.
    """
    _before, _after, connector = _send(
        monkeypatch, "FAILED", {"errors": ["boom"]}
    )
    (notification,) = connector.sent
    assert "not counted" in notification.text
    assert "0 total" not in notification.text
    assert "0 passed" not in notification.text


def test_a_counted_summary_travels_into_the_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _before, _after, connector = _send(monkeypatch, "BLOCKED")
    (notification,) = connector.sent
    fields = notification.blocks[1]["fields"]
    texts = [field["text"] for field in fields]
    assert any("*Contracts:* 4" in text for text in texts)
    assert any("4 passed / 0 failed / 0 unverified" in text for text in texts)
