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

L12–L18 belong to #295 and charge the series that makes the freeze readable. ``refresh_metrics``
leaves the six §14.2 gauges at their last good values when the stats read fails (L06), and on
``/metrics`` a flat ``specproof_outbox_pending`` was indistinguishable from a queue that is
simply empty. The seventh gauge ages those readings. Two things about it are not obvious and
are therefore pinned twice — once by driving the loop (L12–L15) and once by reading the source
(L16–L17): the emit must sit OUTSIDE the guard that swallows refresh failures (a meter only a
successful refresh can move freezes at its last small value in exactly the state it exists to
reveal), and the anchor may only advance when a refresh reaches the end of its own writes (a
partial one already rewrote ``pending``, and must not then claim the family is current). L18
charges the other half of the deliverable — the panel line that puts the age next to the
backlog it ages.
"""

from __future__ import annotations

import ast
import errno
import json
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from observability import metrics_http
from observability.metrics import render_text, set_gauge, snapshot
from storage import outbox_relay as relay_module
from storage.outbox_relay import (
    METRIC_DEAD_LETTERS,
    METRIC_PENDING,
    METRIC_PENDING_FRESHNESS,
    OutboxRelay,
)

ROOT = Path(__file__).resolve().parents[2]
PROM_YML = ROOT / "infra" / "prometheus" / "prometheus.yml"
RELAY_PY = ROOT / "storage" / "outbox_relay.py"
DASH_JSON = ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json"
DOC_CARRIERS = (
    ROOT / "docs" / "operations" / "OBSERVABILITY.md",
    ROOT / "docs" / "operations" / "RUNBOOK.md",
)

FIXED_NOW = 1_800_000_000.0

#: No code path produces this number, so a gauge still showing it was never written.
SENTINEL_PENDING = 999.0

#: The charged spelling of the disclosure. Absence legs forbid this phrase, not the
#: bare words "outbox" or "metrics" — those appear in the loop's ordinary INFO lines.
FREEZE_CLAIM = "metrics refresh failed"

#: The backlog series, spelled so that the age cannot satisfy it by itself:
#: ``specproof_outbox_pending_freshness`` starts with the backlog name, so a plain
#: substring test would make every "names both" claim true of any block that mentions
#: the age alone.
BACKLOG_RE = re.compile(r"specproof_outbox_pending(?!_freshness)")


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
    now_fn: Callable[[], float] | None = None,
) -> tuple[OutboxRelay, LoopMySQL, list[tuple[Any, ...]]]:
    events: list[tuple[Any, ...]] = []
    mysql = LoopMySQL(events, replies)
    rabbit = LoopRabbit(events, topology_error)
    relay = OutboxRelay(
        mysql=mysql,  # type: ignore[arg-type]  # fake duck-types MySQLStore
        rabbitmq=rabbit,  # type: ignore[arg-type]  # fake duck-types RabbitMQClient
        poll_interval=poll_interval,
        # A pinned clock keeps L01–L11 reading the same way they did before #295.
        # The freshness legs pass a Clock so that loop time is scripted.
        now_fn=now_fn or (lambda: FIXED_NOW),
    )
    return relay, mysql, events


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Swap the relay module's clock handle so the loop records sleeps instead of doing them."""
    durations: list[float] = []

    def _sleep(seconds: float) -> None:
        durations.append(float(seconds))

    monkeypatch.setattr(relay_module, "time", SimpleNamespace(sleep=_sleep, time=time.time))
    return durations


class Clock:
    """A loop clock that the fake sleep advances, so loop time is scripted, not waited."""

    def __init__(self, start: float = FIXED_NOW) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t


def _arm_sentinels() -> None:
    """Stamp both series a freshness leg reads with a number no code path produces.

    ``observability.metrics`` is a process-global registry with no reset, so reading
    ``snapshot()`` alone cannot tell "this cycle wrote it" from "some earlier leg wrote
    it". A 999 in either slot means nobody wrote it during this leg.
    """
    set_gauge(METRIC_PENDING, SENTINEL_PENDING)
    set_gauge(METRIC_PENDING_FRESHNESS, SENTINEL_PENDING)


def _advance_and_scrape(
    monkeypatch: pytest.MonkeyPatch, clock: Clock
) -> tuple[list[float], list[tuple[float, float]]]:
    """Fake ``time.sleep`` that moves the clock and then reads the gauges.

    A real Prometheus scrape lands while the relay sleeps — after the loop body has
    finished writing. Sampling at that instant is what makes the emit/sleep ORDER
    observable here: an emit moved below ``time.sleep`` leaves the first scrape reading
    the sentinel and every later one exactly a cycle behind.

    Returns the slept durations and one ``(pending, age)`` pair per cycle.
    """
    durations: list[float] = []
    scrapes: list[tuple[float, float]] = []

    def _sleep(seconds: float) -> None:
        durations.append(float(seconds))
        clock.t += float(seconds)
        gauges = snapshot()["gauges"]
        scrapes.append((gauges[METRIC_PENDING], gauges[METRIC_PENDING_FRESHNESS]))

    monkeypatch.setattr(relay_module, "time", SimpleNamespace(sleep=_sleep, time=time.time))
    return durations, scrapes


def _drive(
    relay: OutboxRelay, cycles: int, *, drain_error_at: int | None = None
) -> int:
    """Run ``run_forever`` for exactly ``cycles`` loop bodies; return how many ran.

    ``drain_pending`` is the first thing each body does and the loop stops when
    ``_running`` flips, so stopping from inside the drain makes the drive
    deterministic — no killer thread, no reliance on a wall-clock timeout.

    ``drain_error_at`` makes that numbered body's drain raise before it claims
    anything, which is how a leg reaches the loop's own drain guard without
    giving the fakes a second job.
    """
    attempts: list[int] = []
    real_drain = relay.drain_pending

    def _drain() -> int:
        attempts.append(1)
        if len(attempts) >= cycles:
            relay.stop()
        if drain_error_at is not None and len(attempts) == drain_error_at:
            raise OSError("broker refused the publish (leg-injected drain error)")
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


# ───────────────────────────────────────────── #295 ─────────────────────────────────────────────
# The legs above prove the six §14.2 gauges keep their last good values and say so in the
# log. They also leave a hole open: a flat series is what BOTH a frozen relay and an empty
# queue look like from /metrics. L12–L18 charge the seventh gauge that closes it.


def test_L12_a_drain_error_does_not_skip_the_freshness_emit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The meter is not allowed to depend on the drain succeeding.

    Sequence: a healthy refresh, a refresh that fails, then a cycle whose drain raises
    while its refresh answers again. On that third cycle the gauges ARE current again, so
    the age must go back to zero. If the emit sat inside the drain guard — the shape an
    earlier relay in this repository uses — the cycle would end having published nothing
    and the scrape would still read 0.5s: an alarm of a frozen backlog printed over a
    relay that just refreshed successfully.
    """
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    clock = Clock()
    durations, scrapes = _advance_and_scrape(monkeypatch, clock)
    _arm_sentinels()
    blip = ConnectionError("mysql gone away (blip)")
    relay, _mysql, _events = _relay([_stats(3), blip, _stats(9)], now_fn=clock)

    assert _drive(relay, 3, drain_error_at=3) == 3
    assert any(
        "drain cycle error" in rec.getMessage() for rec in caplog.records
    ), "the leg's injected drain error never reached the loop's own guard — nothing was tested"
    assert durations == [0.5, 0.5, 0.5], (
        f"loop time did not advance one poll per cycle: {durations}"
    )
    assert scrapes == [
        (3.0, 0.0),
        (3.0, 0.5),
        (9.0, 0.0),
    ], (
        f"expected (pending, age) of (3, 0) then the blip's (3, 0.5) then a successful "
        f"refresh resetting the age on a cycle whose drain raised — got {scrapes}. "
        f"(9.0, 0.5) means the emit is gated behind something other than the loop body; "
        f"(9.0, 999.0) means it never ran at all."
    )


def test_L13_a_frozen_backlog_ages_while_a_quiet_one_does_not(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """#295's reason to exist: three failed refreshes must not read as an empty queue.

    Before this gauge the scrape surface offered ``(3, 3, 3, 3)`` for a relay whose stats
    query has been failing for a minute and the identical ``(3, 3, 3, 3)`` — no, worse,
    ``(0, 0, 0, 0)`` — for a queue that is genuinely quiet, with nothing on /metrics to
    tell the two apart. The age is the discriminator, and it must grow by exactly one
    poll interval per failed cycle: growing faster would mean the anchor never moves
    even on success, and not growing means the meter itself froze with the gauges.
    """
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    clock = Clock()
    durations, scrapes = _advance_and_scrape(monkeypatch, clock)
    _arm_sentinels()
    blip = ConnectionError("mysql gone away (blip)")
    relay, mysql, _events = _relay([_stats(3), blip], now_fn=clock)

    assert _drive(relay, 4) == 4
    assert mysql.stats_calls == 4 and len(_freeze_claims(caplog)) == 3, (
        f"the leg's premise is three failed refreshes behind one good reading; got "
        f"{mysql.stats_calls} stats calls and {len(_freeze_claims(caplog))} disclosures"
    )
    assert [pending for pending, _age in scrapes] == [3.0, 3.0, 3.0, 3.0], (
        f"a failed refresh invented a new backlog reading instead of keeping the last good "
        f"one: {[p for p, _ in scrapes]}"
    )
    assert [age for _pending, age in scrapes] == [0.0, 0.5, 1.0, 1.5], (
        f"the freeze is not ageing one poll interval per cycle: {durations} slept, ages "
        f"{[a for _, a in scrapes]}. A flat age over three disclosed refresh failures is "
        f"the defect #295 was opened for — it is what an empty queue looks like."
    )
    exposition = render_text()
    assert f"specproof_{METRIC_PENDING_FRESHNESS} {scrapes[-1][1]}" in exposition, (
        f"the aged reading is not on the scrape surface with the value the loop last "
        f"published ({scrapes[-1][1]}); the exposition is:\n{exposition}"
    )


def test_L14_a_healthy_loop_keeps_the_age_at_zero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The other side of the discriminator: a quiet queue must not alarm.

    Four cycles, every refresh answering, two of them reading the same pending value 3.
    The backlog is flat across those cycles exactly as it is in L13 — so if the age also
    grew here, the two states would still be indistinguishable and the signal would be a
    false alarm machine instead. A healthy loop must publish zero.
    """
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    clock = Clock()
    _durations, scrapes = _advance_and_scrape(monkeypatch, clock)
    _arm_sentinels()
    relay, _mysql, _events = _relay([_stats(3), _stats(3), _stats(9)], now_fn=clock)

    assert _drive(relay, 4) == 4
    assert _freeze_claims(caplog) == [], "a healthy loop disclosed a freeze"
    assert [age for _pending, age in scrapes] == [0.0, 0.0, 0.0, 0.0], (
        f"a successful refresh left the age at {[a for _, a in scrapes]}: the meter would "
        f"age a healthy relay and every reader learns to ignore it, exactly like a log "
        f"line that fires on a healthy loop (L09)"
    )
    assert [pending for pending, _age in scrapes] == [3.0, 3.0, 9.0, 9.0], (
        f"the pending series this leg compares against L13 moved on its own: {scrapes}"
    )


def test_L15_a_half_finished_refresh_does_not_claim_its_gauges_are_current(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The anchor moves only when the refresh reaches the end of its own writes.

    ``refresh_metrics`` writes ``pending`` first and the failure-rate gauge several
    statements later. Patching ``failure_rate`` to raise on the second call therefore
    produces the nastiest state in the family: ``specproof_outbox_pending`` really was
    rewritten to 9 — so no value is frozen — while the rest of the gauges are still
    whatever an earlier cycle wrote. Advancing the age's anchor at the top of the
    refresh (the obvious implementation) makes the meter report 0 here and the reader
    trusts a half-written family.
    """
    caplog.set_level(logging.DEBUG, logger="storage.outbox_relay")
    monkeypatch.setattr(metrics_http, "serve_metrics_in_thread", _stub_server([]))
    clock = Clock()
    _durations, scrapes = _advance_and_scrape(monkeypatch, clock)
    _arm_sentinels()
    relay, _mysql, _events = _relay([_stats(3), _stats(9)], now_fn=clock)

    real_rate = relay.failure_rate
    rate_calls: list[int] = []

    def _rate() -> float:
        rate_calls.append(1)
        if len(rate_calls) == 2:
            raise RuntimeError("stats row came back with a key nobody mapped")
        return real_rate()

    relay.failure_rate = _rate  # type: ignore[method-assign]

    assert _drive(relay, 3) == 3
    assert len(rate_calls) == 3, f"the injected partial write never happened: {rate_calls} calls"
    claims = _freeze_claims(caplog)
    assert len(claims) == 1, f"one interrupted refresh must be disclosed once, got {len(claims)}"
    assert scrapes[0] == (3.0, 0.0), f"cycle 1 is the healthy baseline, got {scrapes[0]}"
    assert scrapes[1] == (9.0, 0.5), (
        f"cycle 2 rewrote pending to 9 and then died mid-refresh: expected the family to "
        f"stay claimed-stale at age 0.5, got {scrapes[1]}. A 0.0 there means the anchor "
        f"advanced before the writes finished."
    )
    assert scrapes[2] == (9.0, 0.0), (
        f"a fully successful third cycle must reset the age, got {scrapes[2]}"
    )


def _relay_tree() -> tuple[str, ast.Module]:
    text = RELAY_PY.read_text("utf-8", "replace")
    return text, ast.parse(text)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{RELAY_PY.name} declares no {name}() — the subject of this leg is gone")


def _call_names(node: ast.AST) -> set[str]:
    """Every callee reached inside ``node``: ``self.refresh_metrics()`` contributes the leaf."""
    found: set[str] = set()
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        if isinstance(call.func, ast.Attribute):
            found.add(call.func.attr)
        elif isinstance(call.func, ast.Name):
            found.add(call.func.id)
    return found


def _is_emit(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "emit_metrics_freshness"
    )


def _segment(text: str, node: ast.AST) -> str:
    source = ast.get_source_segment(text, node)
    assert source is not None, (
        f"{type(node).__name__} at line {getattr(node, 'lineno', 0)} has no source segment — "
        f"this leg cannot read the code it is charging"
    )
    return source


def test_L16_the_freshness_emit_sits_outside_every_guard_it_must_survive() -> None:
    """Placement is the whole design, so it is charged from the source as well as the loop.

    L12 can only show one skipped cycle; the AST pins the three orderings the runtime
    cannot separate from an equally-shaped accident: the emit is a DIRECT statement of the
    loop body (not nested in the drain guard or in the refresh guard), it comes after the
    guard that swallows refresh failures, and it comes before the sleep that lets a scrape
    land. The refresh guard is identified by the disclosure sentence it writes, so moving
    the emit into a different try does not hide it from this leg.
    """
    text, tree = _relay_tree()
    body = None
    for node in ast.walk(_function(tree, "run_forever")):
        if isinstance(node, ast.While):
            assert body is None, f"run_forever has more than one loop; this leg reads {node.lineno}"
            body = node.body
    assert body is not None, "run_forever contains no while loop — the relay stopped looping"
    assert len(body) >= 4, f"the loop body collapsed to {len(body)} statements; nothing to order"

    def _index(kind: str) -> int:
        hits = [i for i, stmt in enumerate(body) if kind in _call_names(stmt)]
        assert len(hits) == 1, f"expected exactly one loop statement involving {kind}, got {hits}"
        return hits[0]

    drain_idx = _index("drain_pending")
    refresh_idx = _index("refresh_metrics")
    sleep_idx = _index("sleep")
    emit_idx = [i for i, stmt in enumerate(body) if _is_emit(stmt)]
    assert len(emit_idx) == 1, (
        f"the loop body must carry exactly one direct emit_metrics_freshness() statement, "
        f"found {emit_idx} in {[type(s).__name__ for s in body]}"
    )
    assert [drain_idx, refresh_idx, emit_idx[0], sleep_idx] == sorted(
        [drain_idx, refresh_idx, emit_idx[0], sleep_idx]
    ), (
        f"loop order must be drain -> refresh -> emit -> sleep, got "
        f"drain={drain_idx} refresh={refresh_idx} emit={emit_idx[0]} sleep={sleep_idx}. "
        f"An emit after the sleep is a scrape that always reads last cycle's age."
    )

    refresh_stmt = body[refresh_idx]
    assert isinstance(refresh_stmt, ast.Try), (
        f"the refresh is no longer guarded at {refresh_idx}: the stats query now ends the relay"
    )
    assert FREEZE_CLAIM in _segment(text, refresh_stmt), (
        f"the try at {refresh_idx} swallows something other than the refresh failure; "
        f"this leg identified the guard by its disclosure sentence"
    )
    assert emit_idx[0] > refresh_idx, (
        f"the emit at {emit_idx[0]} precedes the guard that can swallow a refresh at "
        f"{refresh_idx}: it would publish an age computed before the write it ages"
    )
    for stmt in body:
        for try_node in (n for n in ast.walk(stmt) if isinstance(n, ast.Try)):
            assert "emit_metrics_freshness" not in _call_names(try_node), (
                f"emit_metrics_freshness() is nested inside the guard at line "
                f"{try_node.lineno}: whatever that guard swallows now also skips the meter, "
                f"which is the one state the meter exists to report"
            )


def test_L17_the_age_is_computed_from_a_bound_only_a_complete_refresh_moves() -> None:
    """The two halves of the mechanism, read where they are written.

    ``refresh_metrics`` ending with the anchor assignment is what makes L15's half-written
    family read as stale; the emit reading ``now - bound`` rather than the bound itself is
    what makes the series an age in seconds. Either half moved and L13's numbers stay
    plausible while the meaning flips — a raw timestamp reads as a growing age and would
    sail through the dashboard until someone compared it to a poll interval.
    """
    text, tree = _relay_tree()
    refresh = _function(tree, "refresh_metrics")
    anchors = [
        stmt
        for stmt in refresh.body
        if isinstance(stmt, ast.Assign)
        and any(
            isinstance(target, ast.Attribute) and target.attr == "_last_metrics_ts"
            for target in stmt.targets
        )
    ]
    assert len(anchors) == 1, f"expected one anchor write in refresh_metrics, got {len(anchors)}"
    assert refresh.body[-1] is anchors[0], (
        f"the anchor is at statement {refresh.body.index(anchors[0])} of "
        f"{len(refresh.body)}: a refresh that dies after it would still claim freshness"
    )
    assert "self._now()" in _segment(text, anchors[0].value), (
        f"the anchor holds something other than the loop clock: {_segment(text, anchors[0].value)}"
    )
    freshness_writes = [
        call
        for call in ast.walk(refresh)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "set_gauge"
        and call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "METRIC_PENDING_FRESHNESS"
    ]
    assert not freshness_writes, (
        f"refresh_metrics writes the freshness gauge itself at line "
        f"{freshness_writes[0].lineno}: a refresh that fails can no longer move the meter "
        f"that reports it failed — the trap #279 measured before anything was written"
    )
    assert "emit_metrics_freshness" not in _call_names(refresh), (
        "the loop's emit was folded into refresh_metrics, so the guard swallows the meter too"
    )

    emit = _function(tree, "emit_metrics_freshness")
    sets = [
        call
        for call in ast.walk(emit)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "set_gauge"
    ]
    assert len(sets) == 1, f"the emit should publish one gauge, found {len(sets)} set_gauge calls"
    key, value = sets[0].args
    assert isinstance(key, ast.Name) and key.id == "METRIC_PENDING_FRESHNESS", (
        f"the emit publishes {getattr(key, 'id', key)} instead of the constant the "
        f"docs and dashboard name"
    )
    literals = {
        target.id: stmt.value.value
        for stmt in tree.body
        if isinstance(stmt, ast.Assign)
        for target in stmt.targets
        if isinstance(target, ast.Name) and isinstance(stmt.value, ast.Constant)
    }
    assert literals.get("METRIC_PENDING_FRESHNESS") == METRIC_PENDING_FRESHNESS, (
        f"the module's constant reads {literals.get('METRIC_PENDING_FRESHNESS')!r} while this "
        f"process imported {METRIC_PENDING_FRESHNESS!r}"
    )
    value_src = _segment(text, value)
    assert "self._now()" in value_src and "self._last_metrics_ts" in value_src, (
        f"the gauge is not an age against the loop clock: {value_src}"
    )


def _panels(dash: dict[str, Any]) -> list[dict[str, Any]]:
    panels = dash.get("panels")
    assert isinstance(panels, list) and len(panels) >= 20, (
        f"{DASH_JSON.name} parsed to {0 if not panels else len(panels)} panels — the read "
        f"nothing case cannot be reported as 'no panel draws this series'"
    )
    return panels


def _draws(panel: dict[str, Any], expr: str) -> bool:
    return any(
        str(target.get("expr", "")).strip() == expr for target in panel.get("targets", []) or []
    )


def test_L18_the_backlog_panel_draws_the_age_on_its_own_axis() -> None:
    """The signal reaches the reader only through the panel that already carries the backlog.

    #279 chose the emission-plus-one-line shape, so the panel is the deliverable: the age
    must be on the SAME panel as ``specproof_outbox_pending``, or the reading rule ("flat
    pending + growing age = frozen") cannot be applied where the alert carrier is drawn.
    Both halves are charged: the name is derived from the module's own constant, and the
    override that gives it seconds and a right axis is matched to the target's own
    legendFormat — a legend renamed without the override silently plots seconds on the
    count axis with ``unit: short``.

    The headline stat card draws the same backlog without the age, and that boundary is
    pinned rather than left as an oversight: its background colour comes from the COUNT
    thresholds, so an ageing seconds series plotted through them would turn the card red at
    50s and be read as a 50-event backlog.
    """
    dash = json.loads(DASH_JSON.read_text("utf-8", "replace"))
    pending = "specproof_outbox_pending"
    fresh = f"specproof_{METRIC_PENDING_FRESHNESS}"
    assert fresh != pending, "the gauge key and the backlog key collapsed to one series name"

    aged = [panel for panel in _panels(dash) if _draws(panel, fresh)]
    assert len(aged) == 1, (
        f"the age is drawn by {len(aged)} panels — exactly one, or a reader has to work out "
        f"which copy of the discriminator to trust"
    )
    panel = aged[0]
    assert _draws(panel, pending), (
        f"panel {panel.get('id')} ages a series it does not draw: the reading rule needs "
        f"both lines on one panel"
    )
    targets = panel.get("targets", [])
    exprs = {str(target.get("expr", "")).strip() for target in targets}
    assert exprs == {pending, fresh}, (
        f"panel {panel.get('id')} must draw the backlog and its age and nothing else, "
        f"got {sorted(exprs)}"
    )
    assert len(targets) == 2, f"expected two targets, got {len(targets)}"
    assert all(target.get("range") is True for target in targets), (
        f"a target without range:true plots one instant point: "
        f"{[t.get('refId') for t in targets]} — an age that is a dot cannot show '逐轮增长'"
    )

    age_target = next(target for target in targets if str(target.get("expr", "")).strip() == fresh)
    legend = str(age_target.get("legendFormat", ""))
    assert legend, "the age target carries no legendFormat for the override to match"

    overrides = panel["fieldConfig"]["overrides"]
    by_name = [o for o in overrides if o.get("id") == "byName"]
    assert len(by_name) == 1 and str(by_name[0].get("options")) == legend, (
        f"the age's axis settings must be attached to its own legendFormat {legend!r}; "
        f"found {[(o.get('id'), o.get('options')) for o in overrides]}"
    )
    props = {str(p.get("id")): p.get("value") for p in by_name[0]["properties"]}
    assert props.get("unit") == "s", f"an age in seconds needs the seconds unit, got {props}"
    assert props.get("custom.axisPlacement") == "right", (
        f"plotting a 0–90s age on the same axis as a backlog count hides whichever series "
        f"is smaller: {props}"
    )
    defaults = panel["fieldConfig"]["defaults"]
    assert defaults.get("unit") != "s", (
        "the panel default became seconds, so the pending count is drawn as an age too"
    )
    assert defaults["custom"].get("axisPlacement") != "right", (
        "the backlog series was moved to the seconds axis by the default"
    )

    unaged = [
        panel for panel in _panels(dash) if _draws(panel, pending) and not _draws(panel, fresh)
    ]
    assert len(unaged) == 1, (
        f"{len(unaged)} panels present the backlog without its age: "
        f"{sorted(panel.get('id') for panel in unaged)}. Each one can show a frozen count as "
        f"if it were current, so this list is where the discriminator is still missing."
    )
    card = unaged[0]
    card_defaults = card["fieldConfig"]["defaults"]
    assert card["type"] == "stat" and card_defaults["color"]["mode"] == "thresholds", (
        f"panel {card.get('id')} is the headline count card by construction; it changed shape, "
        f"so this boundary has to be re-read instead of passing"
    )
    bands = [
        step["value"]
        for step in card_defaults["thresholds"]["steps"]
        if step.get("value") is not None
    ]
    assert bands, (
        f"panel {card.get('id')} no longer carries the count bands that keep the age off it — "
        f"giving it its own thresholds is the prerequisite for drawing the age there"
    )


def test_L19_the_reading_rule_reaches_the_two_ops_carriers() -> None:
    """A series nobody can look up is a signal that shipped only to the wire.

    Both carriers are charged with the same three things, because all three are needed to
    use the gauge at 3am: its name (derived from the module constant, so a renamed key is a
    red doc rather than a doc about a series that no longer exists), the backlog it ages
    (a name documented in isolation teaches nobody what to compare it against), and the
    unit (an unlabelled age invites reading it as a timestamp — the shape the worker's
    ``specproof_worker_reclaim_last_ok_timestamp_seconds`` really does have).

    The dashboard is not in this list because L18 already reads it from its own bytes;
    these two are prose, and prose is where a half-written disclosure survives a green
    metrics test.
    """
    fresh = f"specproof_{METRIC_PENDING_FRESHNESS}"
    for carrier in DOC_CARRIERS:
        text = carrier.read_text("utf-8", "replace")
        blocks = [block for block in re.split(r"\n[ \t]*\n", text) if fresh in block]
        assert blocks, (
            f"{carrier.relative_to(ROOT).as_posix()} never names {fresh}: the gauge is "
            f"scrapeable but not documented, so only whoever wrote #295 can read it"
        )
        paired = [block for block in blocks if BACKLOG_RE.search(block) and "秒" in block]
        assert paired, (
            f"{carrier.relative_to(ROOT).as_posix()} mentions {fresh} in "
            f"{len(blocks)} block(s) and not one of them also names the backlog series it "
            f"ages together with its unit: {[block[:60] for block in blocks]}"
        )




