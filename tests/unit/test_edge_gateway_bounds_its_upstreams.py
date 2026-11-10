"""The edge must bound how long it will wait for its upstreams.

WHY. Spring Cloud Gateway has **no** default for
``spring.cloud.gateway.httpclient.response-timeout``. An agent runtime that
accepts the connection and never answers would therefore wait forever while
the browser is already gone — and the circuit breaker cannot see that case
(it counts *failures*; a hang is not one until it errors). The transport
layer has to bound the wait on its own, and this gate goes red when the
bound disappears from the edge's configuration.

WHAT THIS TEST DOES NOT CLAIM. It reads ``application.yml`` statically: it
pins that a finite bound is *declared*. It cannot prove the bound is wired
into the request path — that is what the Java behaviour leg
(``GatewayUpstreamTimeoutTests``) measures, against a real hanging upstream.
Both are needed: this one catches the deleted config line, the Java one
catches the config line that does nothing.

The connect timeout is bounded to 10 s because the planes live on the same
network; anything longer is a typo, not a budget.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "services" / "gateway" / "src" / "main" / "resources" / "application.yml"
JAVA_TEST = (
    ROOT
    / "services"
    / "gateway"
    / "src"
    / "test"
    / "java"
    / "dev"
    / "specproof"
    / "gateway"
    / "GatewayUpstreamTimeoutTests.java"
)

#: An upstream on the same network that takes longer than this to answer is
#: not "slow", it is dead. 10 s is the budget; anything longer is not one.
MAX_CONNECT_TIMEOUT_MS = 10_000


def _httpclient() -> dict:
    document = yaml.safe_load(TABLE.read_text(encoding="utf-8"))
    httpclient = document["spring"]["cloud"]["gateway"].get("httpclient")
    assert httpclient is not None, (
        "the edge declares no httpclient block — an unset response-timeout "
        "means the edge waits for a hung upstream forever"
    )
    return httpclient


def _duration_ms(raw: object) -> int:
    """Parse Spring's duration spellings: ``30s``, ``500ms``, ``1m``."""
    match = re.fullmatch(r"\s*(\d+)\s*(ms|s|m)\s*", str(raw))
    assert match, f"response-timeout is not a duration this gate can read: {raw!r}"
    value, unit = match.groups()
    factor = {"ms": 1, "s": 1000, "m": 60_000}[unit]
    return int(value) * factor


def test_the_edge_declares_a_bounded_connect_timeout() -> None:
    raw = _httpclient().get("connect-timeout")
    assert raw is not None, "no connect-timeout — a dead plane costs the caller forever"
    value = int(raw)
    assert 0 < value <= MAX_CONNECT_TIMEOUT_MS, (
        f"connect-timeout {value} ms is not a budget this stack can live with"
    )


def test_the_edge_declares_a_bounded_response_timeout() -> None:
    raw = _httpclient().get("response-timeout")
    assert raw is not None, (
        "no response-timeout — Spring Cloud Gateway waits forever on a hung "
        "upstream, and the circuit breaker cannot see a hang until it errors"
    )
    value = _duration_ms(raw)
    assert value >= 1000, (
        f"response-timeout {raw!r} is under one second — the edge would refuse "
        "legitimate answers that merely take a moment"
    )
    assert value <= 120_000, (
        f"response-timeout {raw!r} is two minutes — long enough that a hung "
        "upstream still holds the caller's request hostage"
    )


def test_the_java_behaviour_leg_exists_and_pins_the_timeout() -> None:
    """The proof this gate does not carry lives next to the config."""
    source = JAVA_TEST.read_text(encoding="utf-8")
    assert "response-timeout" in source, (
        "the Java behaviour leg no longer pins a response-timeout — the "
        "config line may now be decoration"
    )
    assert "Thread.sleep" in source, (
        "the Java behaviour leg no longer has a hanging upstream — it is not "
        "measuring the timeout anymore"
    )
