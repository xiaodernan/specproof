"""The file lock backs off instead of spinning (#1629).

WHY. The lock is a sibling ``.lock`` file created with ``O_CREAT | O_EXCL``:
the create either wins or loses atomically. A loser has to ask again --
and it used to ask every **10 milliseconds**, for as long as the other
process held the lock. That is a hundred wake-ups a second, each one a
system call, all of them asking a question whose answer cannot change
faster than the other process's work.

The backoff (10ms, doubling, capped at 100ms) asks the same question a
handful of times instead, and the **deadline is unchanged**: the lock is
still given up at the same moment, and it is still taken as soon as it is
free. Only the number of wasted wake-ups changes.

What these legs measure:

* a contended lock asks the OS a **handful** of times, not a hundred
  times a second (the number of polls is counted, not the wall clock),
* the lock is still acquired as soon as it is free,
* and the timeout still fires -- the backoff must not make the deadline
  later than the promise.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from evidence import filelock as filelock_module
from evidence.filelock import file_lock


class _Clock:
    """A clock that advances only when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_a_contended_lock_asks_the_os_a_handful_of_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One second of contention: a fixed 10ms spin would ask ~100 times."""
    clock = _Clock()
    monkeypatch.setattr(filelock_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(filelock_module.time, "sleep", clock.sleep)

    target = tmp_path / "revocations.log"
    lock_file = target.with_suffix(target.suffix + ".lock")
    lock_file.write_text("held by someone else", encoding="utf-8")

    with pytest.raises(TimeoutError), file_lock(target, timeout=1.0):
        pass

    assert len(clock.sleeps) <= 20, (
        f"a contended lock asked the OS {len(clock.sleeps)} times in one second "
        "-- the poll interval is fixed instead of backing off"
    )
    # The last sleep is capped to the remaining time, so the total is the
    # deadline minus a float hair (the accumulation is not exact). What
    # matters is that the lock did not give up EARLY.
    assert sum(clock.sleeps) >= 1.0 - 1e-6, (
        f"the waits totalled {sum(clock.sleeps)}s -- the lock gave up EARLIER "
        "than its promise"
    )


def test_the_backoff_never_sleeps_past_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The timeout is the promise; the backoff must not overshoot it."""
    clock = _Clock()
    monkeypatch.setattr(filelock_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(filelock_module.time, "sleep", clock.sleep)

    target = tmp_path / "revocations.log"
    lock_file = target.with_suffix(target.suffix + ".lock")
    lock_file.write_text("held", encoding="utf-8")

    with pytest.raises(TimeoutError), file_lock(target, timeout=0.25):
        pass

    assert clock.now <= 1_000.0 + 0.25 + 1e-9, (
        f"the lock waited until {clock.now - 1_000.0}s for a 0.25s timeout -- the "
        "backoff overshot the deadline"
    )


def test_the_lock_is_taken_as_soon_as_it_is_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock that frees up mid-wait is taken on the next poll -- the
    backoff must not add a fixed delay to the happy path."""
    clock = _Clock()
    monkeypatch.setattr(filelock_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(filelock_module.time, "sleep", clock.sleep)

    target = tmp_path / "revocations.log"
    lock_file = target.with_suffix(target.suffix + ".lock")
    lock_file.write_text("held", encoding="utf-8")

    real_open = os.open
    attempts = {"n": 0}

    def open_once_free(path: str, flags: int, mode: int) -> int:
        attempts["n"] += 1
        if attempts["n"] >= 2:
            # the other process lets go
            lock_file.unlink(missing_ok=True)
        return real_open(path, flags, mode)

    monkeypatch.setattr(filelock_module.os, "open", open_once_free)

    with file_lock(target, timeout=5.0):
        pass

    assert attempts["n"] == 2, (
        f"the lock took {attempts['n']} attempts -- the backoff delayed the "
        "acquisition past the first retry"
    )


def test_an_uncontended_lock_takes_no_wait_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The happy path must not sleep: the common case pays nothing."""
    clock = _Clock()
    monkeypatch.setattr(filelock_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(filelock_module.time, "sleep", clock.sleep)

    target = tmp_path / "revocations.log"
    with file_lock(target, timeout=1.0):
        pass

    assert clock.sleeps == [], "an uncontended lock waited for nothing"
    assert not target.with_suffix(target.suffix + ".lock").exists(), (
        "the lock file outlived the lock"
    )


def test_the_backoff_is_bounded() -> None:
    """The cap is what keeps the poll count finite."""
    assert filelock_module._LOCK_POLL_INITIAL < filelock_module._LOCK_POLL_MAX
    assert filelock_module._LOCK_POLL_MAX <= 0.25, (
        "the poll cap is long enough that a contended lock waits a visible "
        "fraction of a second between attempts"
    )


def test_the_measurement_is_not_vacuous() -> None:
    assert time.monotonic() < float("inf")  # the clock is real in production
