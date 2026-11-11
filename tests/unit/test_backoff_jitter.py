"""The backoff is jittered: the herd is spread, the cap is not moved.

WHY. #1615 changed the exponential fallback of the shared retry contract
(``contracts/retry_after.py``) and of the notify relay's defer
(``storage/notify_relay.py``) from "exactly 2^n seconds" to "somewhere in
[2^n/2, 2^n]". The reason is a networking one: a backoff every client
computes identically is a synchronization point, so the clients that were
refused together come back together and the provider sees the burst it was
trying to shed.

These legs measure the properties that make the change worth anything:

* the wait lands inside the cap (the cap is the contract; the jitter only
  decides where inside it),
* repeated waits for the SAME attempt differ (the herd is actually spread),
* the distribution is centred (not a jitter that hides near the cap or
  clusters at zero),
* the gateway's own ``Retry-After`` is still honored exactly -- jittering an
  instruction would retry earlier than the server asked, which is a
  correctness bug, not a tuning knob,
* both call sites route through the ONE jitter policy (a second
  implementation would drift, which is how #517 happened).
"""

from __future__ import annotations

import ast
import random
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from tenacity import RetryCallState

from contracts.retry_after import (
    MAX_EXPONENTIAL_WAIT_SECONDS,
    jittered_wait_seconds,
    retry_after_seconds,
    wait_retry_after_or_exponential,
)

REPO = Path(__file__).resolve().parents[2]


class _Headers:
    def __init__(self, raw: str) -> None:
        self._raw = raw

    def get(self, key: str) -> str | None:
        return self._raw if key == "retry-after" else None


class _Response:
    def __init__(self, raw: str) -> None:
        self.headers = _Headers(raw)


class _GatewayError(Exception):
    def __init__(self, response: object) -> None:
        super().__init__("gateway error")
        self.response = response


def _state(attempt: int, header: str | None = None) -> RetryCallState:
    response = None if header is None else _Response(header)
    return cast(
        "RetryCallState",
        SimpleNamespace(
            outcome=SimpleNamespace(exception=lambda: _GatewayError(response)),
            attempt_number=attempt,
        ),
    )


def test_the_wait_lands_inside_the_cap_and_never_above_it() -> None:
    rng = random.Random(1615)
    for cap in (1.0, 2.0, 4.0, 8.0, 60.0):
        for _ in range(200):
            wait = jittered_wait_seconds(cap, rng=rng)
            assert cap / 2 <= wait <= cap, (cap, wait)


def test_repeated_waits_for_the_same_attempt_differ() -> None:
    """The herd is spread: two clients refused at the same second must not
    pick the same wake-up."""
    rng = random.Random(1615)
    waits = {jittered_wait_seconds(8.0, rng=rng) for _ in range(50)}
    assert len(waits) >= 25, f"only {len(waits)} distinct waits in 50 samples"


def test_the_distribution_is_centred_inside_the_cap() -> None:
    """Equal jitter: half fixed, half random -- so the mean sits at ~3/4 of
    the cap, not at the cap and not at zero."""
    rng = random.Random(1615)
    cap = 8.0
    samples = [jittered_wait_seconds(cap, rng=rng) for _ in range(2000)]
    mean = sum(samples) / len(samples)
    assert 0.65 * cap <= mean <= 0.85 * cap, mean


def test_the_servers_retry_after_is_honored_exactly() -> None:
    """The header is an instruction. Jittering it would retry EARLIER than
    the server asked -- a correctness bug, not a tuning knob."""
    assert wait_retry_after_or_exponential(_state(1, "9")) == 9.0
    assert wait_retry_after_or_exponential(_state(7, "90")) == 90.0
    assert wait_retry_after_or_exponential(_state(3, "0")) == 0.0
    # and the parser still answers the same number the two consumers used
    assert retry_after_seconds(_GatewayError(_Response("12"))) == 12.0


def test_the_cap_of_the_exponential_curve_is_unchanged() -> None:
    assert MAX_EXPONENTIAL_WAIT_SECONDS == 60.0
    state = _state(7)
    for _ in range(50):
        assert wait_retry_after_or_exponential(state) <= 60.0


def test_both_call_sites_route_through_the_one_jitter_policy() -> None:
    """A second implementation would drift -- that is how the two-copy
    divergence of #517 happened.

    Checked on the AST: the LLM path calls the shared wait, and the notify
    relay's defer calls the shared jitter.
    """
    producer = ast.parse((REPO / "contracts" / "retry_after.py").read_text(encoding="utf-8"))
    names = {
        node.func.id
        for node in ast.walk(producer)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "jittered_wait_seconds" in names

    relay = ast.parse((REPO / "storage" / "notify_relay.py").read_text(encoding="utf-8"))
    relay_calls = {
        node.func.id
        for node in ast.walk(relay)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "jittered_wait_seconds" in relay_calls, (
        "the notify relay no longer routes its defer through the shared jitter"
    )


@pytest.mark.parametrize("attempt", [1, 2, 3, 7])
def test_the_exponential_curve_still_doubles_before_the_cap(attempt: int) -> None:
    """The CURVE is unchanged (2^n capped at 60): only the landing point
    inside it is spread. The cap for an attempt is 2**(attempt-1), capped."""
    cap = min(60.0, float(2 ** (attempt - 1)))
    rng = random.Random(attempt)
    wait = jittered_wait_seconds(cap, rng=rng)
    assert cap / 2 <= wait <= cap
