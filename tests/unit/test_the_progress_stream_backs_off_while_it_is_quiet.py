"""The progress stream's poll interval follows the stream's own silence.

The stream is a VIEWER of a job: every open tab costs the server one Redis
round trip per poll, and most of a job's life is silence. A fixed 500ms
poll therefore spends two round trips per second per viewer on a job that
has nothing to say for minutes at a time.

The shape this pins:

* the interval starts at the minimum (a job's first events arrive in a
  burst and must not wait),
* while the stream is quiet it backs off, doubling up to a cap,
* when an event arrives the next poll waits the minimum again.

The measurement is of the **requested delays**, not of wall-clock time:
the stream asks for a sleep, the test records what it asked for. A
timing-based test would be flaky exactly where it matters (a loaded
machine), and it would be testing the scheduler instead of the contract.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.routes import jobs as jobs_module  # noqa: E402


class _FakeRedis:
    """Answers with a scripted sequence of batches."""

    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self._batches = list(batches)
        self.calls: list[str] = []

    def xread_progress(
        self, job_id: str, from_id: str = "0", count: int = 100
    ) -> list[dict[str, Any]]:
        self.calls.append(from_id)
        if not self._batches:
            return []
        return self._batches.pop(0)


class _FakeRequest:
    """Disconnects after the given number of polls."""

    def __init__(self, polls_before_disconnect: int) -> None:
        self._left = polls_before_disconnect

    async def is_disconnected(self) -> bool:
        if self._left <= 0:
            return True
        self._left -= 1
        return False


def _event(entry_id: str, stage: str = "compile") -> dict[str, Any]:
    return {
        "id": entry_id,
        "node": stage,
        "status": "running",
        "percentage": 10.0,
        "message": stage,
        "at": "2026-11-12T00:00:00Z",
        "artifacts": [],
    }


@pytest.mark.asyncio
async def test_the_interval_starts_short_backs_off_and_snaps_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def _record(delay: float) -> None:
        delays.append(float(delay))

    monkeypatch.setattr(jobs_module.asyncio, "sleep", _record)

    # history (one event), then four quiet polls, then an event, then quiet
    redis = _FakeRedis(
        [
            [_event("1")],
            [],
            [],
            [],
            [],
            [_event("2")],
            [],
            [],
        ]
    )
    request = _FakeRequest(polls_before_disconnect=12)

    frames = [
        frame
        async for frame in jobs_module._progress_stream(  # noqa: SLF001
            "job-1", request, redis, "0"  # type: ignore[arg-type]
        )
    ]

    assert frames, "the stream must deliver the events it was given"
    assert delays, "the stream must ask for a sleep between polls"
    # it starts at the minimum and never goes below it
    assert delays[0] == jobs_module._SSE_POLL_MIN
    assert min(delays) >= jobs_module._SSE_POLL_MIN
    # it backs off while quiet and never exceeds the cap
    assert max(delays) <= jobs_module._SSE_POLL_MAX
    # and it is not a constant interval any more (the whole point)
    assert len(set(delays)) > 1, f"the interval never moved: {delays}"
    # after an event arrives the next poll waits the minimum again: the
    # backoff must not be a one-way street, or a job that goes quiet and
    # then speaks again would keep the slow interval.
    capped = delays.index(jobs_module._SSE_POLL_MAX)
    assert jobs_module._SSE_POLL_MIN in delays[capped:], (
        f"the interval did not snap back after an event: {delays}"
    )


@pytest.mark.asyncio
async def test_a_quiet_stream_costs_fewer_polls_than_a_fixed_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backoff has to actually buy something, not just move numbers."""

    delays: list[float] = []

    async def _record(delay: float) -> None:
        delays.append(float(delay))

    monkeypatch.setattr(jobs_module.asyncio, "sleep", _record)

    redis = _FakeRedis([[]] + [[] for _ in range(12)])
    request = _FakeRequest(polls_before_disconnect=12)

    async for _ in jobs_module._progress_stream(  # noqa: SLF001
        "job-2", request, redis, "0"  # type: ignore[arg-type]
    ):
        pass

    assert len(delays) >= 12, f"the stream stopped polling: {delays}"

    # The point of the backoff is the OTHER direction: inside a fixed wall
    # clock, a backing-off stream polls LESS often. At a fixed 500ms, six
    # seconds buy twelve polls; with the backoff the same six seconds buy
    # far fewer — that is the round trips the quiet tail of a job stops
    # costing.
    budget = 6.0
    spent = 0.0
    polls = 0
    for delay in delays:
        if spent + delay > budget:
            break
        spent += delay
        polls += 1
    assert polls < 12 / 2, (
        f"in {budget}s the backing-off stream still polled {polls} times "
        f"(a fixed 500ms interval would poll 12): {delays}"
    )
