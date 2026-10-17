"""#275 — the outbox relay's metrics refresh has to speak when it stops answering.

``run_forever`` wrapped ``self.refresh_metrics()`` in ``contextlib.suppress(Exception)``.
Measured on this host before the change (``.scratch/probe274_pre.py`` →
``.scratch/m274_probe.txt``): four cycles ran, the two healthy refreshes moved
``specproof_outbox_pending`` 999 → 3 → 9, the two failing ones left it at 9, and the log
carried nothing but "started" and "stopped". A deployed critical rule reads exactly that
series (``infra/prometheus/alerts-slo.yml``: ``specproof_outbox_pending > 50``), and
Prometheus cannot tell a stale gauge from a healthy one — so the defect is not the frozen
number, it is that nobody is told.

These legs drive the loop itself. Before this file nothing in the repository ever called
either relay's ``run_forever``; ``tests/unit/test_storage_governance.py`` calls
``refresh_metrics`` directly and passes, which is precisely why the freeze stayed
invisible — the unit path answers, only the loop swallowed.

One design decision is charged here too. ``storage/notify_relay.py`` discloses the same
failure, but its loop puts ``drain_pending`` and ``refresh_metrics`` in ONE try and sleeps
``MAX_BACKOFF`` on any exception, so a metrics blip stalls delivery there. The outbox
relay deliberately keeps the narrower guard: disclose, keep the cadence (L07), and let
anything else still escape the loop (L10).

L11 belongs to #284 and charges the other half of the same loop: the startup bind. The
metrics endpoint used to accept a port another process was already answering (Windows
``SO_REUSEADDR``), so a host-run relay could deliver while its alert-carrier gauges were
unreadable and Prometheus still saw a healthy ``outbox-relay:9101``.
"""

from __future__ import annotations

import errno
import logging
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from observability import metrics_http
from observability.metrics import set_gauge, snapshot
from storage import outbox_relay as relay_module
from storage.outbox_relay import (
    METRIC_DEAD_LETTERS,
    METRIC_PENDING,
    OutboxRelay,
)

ROOT = Path(__file__).resolve().parents[2]
PROM_YML = ROOT / "infra" / "prometheus" / "prometheus.yml"

FIXED_NOW = 1_800_000_000.0

#: No code path produces this number, so a gauge still showing it was never written.
SENTINEL_PENDING = 999.0

#: The charged spelling of the disclosure. Absence legs forbid this phrase, not the
#: bare words "outbox" or "metrics" — those appear in the loop's ordinary INFO lines.
FREEZE_CLAIM = "metrics refresh failed"


def _stub_server(seen: list[int]) -> Callable[..., None]:
    """A stand-in metrics server that records the port it was asked to open."""

    def _serve(host: str | None = None, port: int = 9100) -> None:
        seen.append(int(port))

    return _serve


class LoopMySQL:
    """Answers ``outbox_stats`` from a script: dict entries return, exceptions raise.

    The script is consumed in call order and its last entry repeats, so a leg that
    wants "healthy, healthy, then gone away" writes three entries and drives three
    cycles. The event list is SHARED with the rabbit fake, because the ordering legs
    ask about topology, drain and refresh as one sequence.
    """

    def __init__(self, events: list[tuple[Any, ...]], replies: list[Any]) -> None:
        self.replies = replies
        self.stats_calls = 0
        self.events = events

    def fetch_pending_outbox_rows(self, limit: int) -> list[dict[str, Any]]:
        self.events.append(("fetch", limit))
        return []

    def outbox_stats(self) -> dict[str, Any]:
        self.stats_calls += 1
        self.events.append(("stats",))
        reply = self.replies[min(self.stats_calls, len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return dict(reply)


class LoopRabbit:
    """Records topology arming; publishes nothing because these legs drain no rows."""

    def __init__(
        self,
        events: list[tuple[Any, ...]],
        topology_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.topology_error = topology_error

    def ensure_topology(self) -> None:
        if self.topology_error is not None:
            raise self.topology_error
        self.events.append(("topology",))

    def publish(self, routing_key: str, payload: dict[str, Any]) -> None:
        raise AssertionError("these legs drain no outbox rows")


def _relay(
    replies: list[Any],
    *,
    poll_interval: float = 0.5,
    topology_error: Exception | None = None,
) -> tuple[OutboxRelay, LoopMySQL, list[tuple[Any, ...]]]:
    events: list[tuple[Any, ...]] = []
    mysql = LoopMySQL(events, replies)
    rabbit = LoopRabbit(events, topology_error)
    relay = OutboxRelay(
        mysql=mysql,  # type: ignore[arg-type]  # fake duck-types MySQLStore
        rabbitmq=rabbit,  # type: ignore[arg-type]  # fake duck-types RabbitMQClient
        poll_interval=poll_interval,
        now_fn=lambda: FIXED_NOW,
    )
    return relay, mysql, events


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Swap the relay module's clock handle so the loop records sleeps instead of doing them."""
    durations: list[float] = []

    def _sleep(seconds: float) -> None:
        durations.append(float(seconds))

    monkeypatch.setattr(relay_module, "time", SimpleNamespace(sleep=_sleep, time=time.time))
    return durations


def _drive(relay: OutboxRelay, cycles: int) -> int:
    """Run ``run_forever`` for exactly ``cycles`` loop bodies; return how many ran.

    ``drain_pending`` is the first thing each body does and the loop stops when
    ``_running`` flips, so stopping from inside the drain makes the drive
    deterministic — no killer thread, no reliance on a wall-clock timeout.
    """
    attempts: list[int] = []
    real_drain = relay.drain_pending

    def _drain() -> int:
        attempts.append(1)
        if len(attempts) >= cycles:
            relay.stop()
        return real_drain()

    relay.drain_pending = _drain  # type: ignore[method-assign]
    relay.run_forever()
    return len(attempts)


def _stats(pending: int, dead_letters: int = 1) -> dict[str, Any]:
    return {
        "pending": pending,
        "dead_letters": dead_letters,
        "retries": 0,
        "oldest_created_at": None,
        "last_success": None,
    }


def _freeze_claims(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [rec for rec in caplog.records if FREEZE_CLAIM in rec.getMessage()]


def _roster_port() -> int:
    """The port the DEPLOYED scrape roster asks ``outbox-relay`` for.

    Derived from the roster file rather than typed here: the claim is "the process
    answers where Prometheus asks", and a hand-copied literal would stay green while
    both halves moved. Floored at the six jobs the roster declares so a parse that
    matched nothing cannot be reported as "one target, no mismatch".
    """
    configs = yaml.safe_load(PROM_YML.read_text("utf-8", "replace"))["scrape_configs"]
    jobs: dict[str, list[str]] = {}
    for entry in configs:
        targets: list[str] = []
        for static in entry.get("static_configs", []) or []:
            targets.extend(str(target) for target in static["targets"])
        jobs[str(entry["job_name"])] = targets
    assert len(jobs) >= 6, f"roster parse collapsed to {sorted(jobs)}"
    targets = jobs.get("outbox-relay", [])
    assert len(targets) == 1, (
        f"L03 needs exactly one roster target for job outbox-relay, got {targets} — "
        f"the parse read the wrong population"
    )
    host, _, port = targets[0].rpartition(":")
    assert host == "outbox-relay", f"unexpected roster target {targets[0]!r}"
    return int(port)


def test_L01_the_loop_arms_topology_once_before_it_drains_or_measures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    _record_sleeps(monkeypatch)
    relay, mysql, events = _relay([_stats(0)])

    assert _drive(relay, 3) == 3
    assert events[0] == ("topology",), f"the loop must arm topology first, saw {events[:3]}"
    assert sum(1 for event in events if event[0] == "topology") == 1, (
        f"ensure_topology ran once per cycle in {events}: the relay would re-declare the "
        f"exchange every poll instead of once per process"
    )
    assert events[1] == ("fetch", relay.batch_size), (
        f"the first drain must claim a batch, saw {events[1]}"
    )
    assert mysql.stats_calls == 3, (
        f"one metrics refresh per cycle expected, got {mysql.stats_calls}"
    )


def test_L02_the_injected_knob_port_reaches_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server(seen))
    monkeypatch.setenv("OUTBOX_RELAY_METRICS_PORT", "9555")
    _record_sleeps(monkeypatch)
    relay, _mysql, _events = _relay([_stats(0)])

    assert _drive(relay, 2) == 2
    assert seen == [9555], (
        f"the loop opened {seen}: the operator's OUTBOX_RELAY_METRICS_PORT must reach the "
        f"server exactly once, and not once per cycle"
    )


def test_L03_the_default_port_is_the_one_the_roster_scrapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server(seen))
    monkeypatch.delenv("OUTBOX_RELAY_METRICS_PORT", raising=False)
    _record_sleeps(monkeypatch)
    relay, _mysql, _events = _relay([_stats(0)])

    declared = _roster_port()
    _drive(relay, 1)
    assert seen == [declared], (
        f"with no env set the process binds {seen} while infra/prometheus/prometheus.yml "
        f"scrapes outbox-relay:{declared} — a relay started outside compose answers on a "
        f"port nobody asks"
    )


def test_L04_a_healthy_cycle_moves_the_backlog_gauge(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    _record_sleeps(monkeypatch)
    set_gauge(METRIC_PENDING, SENTINEL_PENDING)
    relay, _mysql, _events = _relay([_stats(7)])

    _drive(relay, 1)
    gauges = snapshot()["gauges"]
    assert gauges[METRIC_PENDING] == 7.0, (
        f"the loop never published the backlog it just read: gauge is {gauges[METRIC_PENDING]}"
    )
    assert _freeze_claims(caplog) == [], "a healthy refresh must not claim a freeze"


def test_L05_a_stats_blip_is_disclosed_with_the_cause_and_the_consequence(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    _record_sleeps(monkeypatch)
    blip = ConnectionError("mysql gone away (blip)")
    relay, _mysql, _events = _relay([_stats(3), blip])

    assert _drive(relay, 2) == 2, "losing the stats query must not end the relay"
    claims = _freeze_claims(caplog)
    assert len(claims) == 1, f"expected one disclosure for one failed refresh, got {len(claims)}"
    record = claims[0]
    assert record.levelno == logging.ERROR, (
        f"a frozen gauge a critical alert reads is not a {record.levelname} event"
    )
    message = record.getMessage()
    assert "last good values" in message, (
        f"the sentence names the failure but not what it costs: {message!r} — an operator "
        f"must learn the series they are watching keeps its old number"
    )
    assert "specproof_outbox_" in message, (
        f"the disclosure must name the gauge family it freezes, saw {message!r}"
    )
    assert record.exc_info is not None and record.exc_info[1] is blip, (
        f"the cause must ride the record, not a bare sentence: exc_info={record.exc_info}"
    )


def test_L06_the_frozen_gauge_and_its_disclosure_travel_together(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    _record_sleeps(monkeypatch)
    blip = ConnectionError("mysql gone away (blip)")
    set_gauge(METRIC_PENDING, SENTINEL_PENDING)
    relay, _mysql, _events = _relay([_stats(3), _stats(9), blip, blip])

    assert _drive(relay, 4) == 4
    gauges = snapshot()["gauges"]
    assert gauges[METRIC_PENDING] == 9.0, (
        f"the backlog series must stay at its last good value across failed refreshes, "
        f"got {gauges[METRIC_PENDING]} — anything else means a failed refresh wrote a "
        f"invented zero, which a > 50 alert would read as a cleared queue"
    )
    assert gauges[METRIC_DEAD_LETTERS] == 1.0, (
        f"dead letters froze too, expected 1.0, got {gauges[METRIC_DEAD_LETTERS]}"
    )
    claims = _freeze_claims(caplog)
    assert len(claims) == 2, (
        f"two failed refreshes froze the family and must say so twice, got {len(claims)} — "
        f"one claim for two freezes is a disclosure that stops counting"
    )


def test_L07_a_metrics_blip_does_not_put_delivery_on_max_backoff(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    durations = _record_sleeps(monkeypatch)
    blip = ConnectionError("mysql gone away (blip)")
    relay, mysql, _events = _relay([_stats(1), blip, blip], poll_interval=0.5)

    attempts = _drive(relay, 3)
    assert attempts == 3 and mysql.stats_calls == 3
    assert durations == [0.5, 0.5, 0.5], (
        f"a refresh failure changed the loop's cadence: slept {durations} instead of "
        f"poll_interval {relay.poll_interval} each cycle. notify_relay pays exactly this "
        f"price by sharing one try between draining and metrics; the outbox relay must "
        f"keep delivering while its gauges are blind."
    )
    assert OutboxRelay.MAX_BACKOFF not in durations, (
        f"MAX_BACKOFF appeared in {durations}: delivery stalled on a metrics-only blip"
    )


def test_L08_a_defect_that_is_not_an_os_refusal_is_still_disclosed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    _record_sleeps(monkeypatch)
    broken = RuntimeError("stats row came back with a key nobody mapped")
    relay, _mysql, _events = _relay([_stats(3), broken])

    assert _drive(relay, 2) == 2, (
        "the guard narrowed to an OS error class: a programming error in the refresh "
        "ended the relay instead of being disclosed"
    )
    claims = _freeze_claims(caplog)
    assert len(claims) == 1 and isinstance(claims[0].exc_info[1], RuntimeError), (
        f"expected one ERROR record carrying the RuntimeError, got {claims}"
    )


def test_L09_the_freeze_claim_stays_absent_while_stats_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    _record_sleeps(monkeypatch)
    relay, _mysql, _events = _relay([_stats(2)])

    _drive(relay, 3)
    assert _freeze_claims(caplog) == [], (
        "the disclosure fires on a healthy loop, so it stops meaning the gauge is stale "
        "and every operator learns to ignore it"
    )


def test_L10_an_error_before_the_loop_still_escapes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    seen: list[int] = []
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server(seen))
    _record_sleeps(monkeypatch)
    relay, mysql, _events = _relay(
        [_stats(1)], topology_error=ConnectionError("broker down at boot")
    )

    with pytest.raises(ConnectionError):
        relay.run_forever()
    assert seen == [], (
        f"topology failed yet the scrape server opened on {seen}: run_forever arms topology "
        f"BEFORE it advertises a scrape target, and either swallowing the boot error or "
        f"moving that arming after the bind breaks the order"
    )
    assert mysql.stats_calls == 0 and _freeze_claims(caplog) == []


def test_L11_the_loop_never_starts_while_another_process_holds_its_scrape_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#284 — a squatted metrics port is a reason not to run, not a silent boot.

    ``outbox-relay:9101`` is a DEPLOYED scrape target, and
    ``infra/prometheus/alerts-slo.yml`` reads ``specproof_outbox_pending`` off it.
    Before #284 the bind used Windows' ``SO_REUSEADDR`` meaning ("may share this
    address"): on a host run — ``scripts/start_local.ps1`` starts this relay — the
    second relay booted, drained, and its gauges went into a registry nobody could
    scrape, while Prometheus kept reading the first owner and saw a healthy target.
    That is the one failure mode an alert carrier must not have.

    The container plane (Linux) already refused the bind and killed the boot, so
    this leg is parity with what production does, not a new policy: the refusal
    escapes ``run_forever`` before a single row is claimed. The invoice cron is
    deliberately the opposite shape — its port is in no roster and its work is
    idempotent per closed month, so it discloses "NOT serving" and keeps going.

    The loop is entered through ``_drive``, not a bare ``run_forever()``: if the
    bind ever stops refusing, the loop must terminate after one body so this leg
    reads RED, not HUNG.
    """
    owner = metrics_http.serve_metrics_in_thread(host="127.0.0.1", port=0)
    held = int(owner.server_address[1])
    try:
        monkeypatch.setenv("OUTBOX_RELAY_METRICS_PORT", str(held))
        _record_sleeps(monkeypatch)
        relay, mysql, events = _relay([_stats(0)])

        with pytest.raises(OSError) as refused:
            _drive(relay, 1)
        code = int(getattr(refused.value, "winerror", None) or refused.value.errno or 0)
        assert code == errno.EADDRINUSE, (
            f"the relay did boot and then died of something else on port {held}: "
            f"{type(refused.value).__name__} code={code}, expected EADDRINUSE "
            f"({errno.EADDRINUSE})"
        )
        assert not any(event[0] in {"fetch", "stats"} for event in events), (
            f"the loop started draining while its scrape port belonged to another "
            f"process: {events}. A relay that delivers blind cannot be alerted on."
        )
        assert mysql.stats_calls == 0, (
            f"gauges were refreshed on a port nobody can scrape: {mysql.stats_calls} calls"
        )
    finally:
        owner.shutdown()
        owner.server_close()

