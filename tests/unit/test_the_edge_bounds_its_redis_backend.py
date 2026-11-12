"""The edge must BOUND its Redis calls — the ones it makes in the REQUEST PATH.

WHY. The edge's Redis-backed features are not a side channel: the distributed
token bucket (#1634) decides **every request's admission**, and the response
cache reads on the way through. Both promise to fall back rather than stall
("a bucket that points at a dead Redis resolves to the configured fallback
and never blocks the event loop").

That promise is only true while the call itself is BOUNDED. Spring's default
Redis command timeout is **60 seconds** — so an unbounded edge would hold a
request for a minute whenever Redis is slow, and the fallback would arrive
long after the caller gave up. The edge's own upstream budget is measured in
seconds (connect 10s, response up to 120s); a cache-side decision that may
outlive the caller is not a cache, it is an outage with extra steps.

This gate pins the DECLARATION (the configuration line). What it cannot
prove is that the bound is honoured on the request path — that is the Java
side's job (the gateway's own tests), and the gate at least says which
number it expects to find there.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_YML = (
    ROOT / "services" / "gateway" / "src" / "main" / "resources" / "application.yml"
)

#: The edge's budget for a Redis decision. It is made on the way through, so
#: it has to be cheaper than the request it is protecting: the upstream
#: connect budget is 10s, and this must not be a large fraction of it.
MAX_TIMEOUT_MS = 50

#: Spring's own default when the property is absent.
SPRING_DEFAULT_TIMEOUT_MS = 60_000


def _duration_ms(raw: object) -> int:
    """Parse Spring's duration spellings: ``50ms``, ``1s``, ``2m``."""
    text = str(raw)
    # ``${ENV:50ms}`` — the operator may override it; the DEFAULT is what
    # this gate judges (an override is the operator's own choice).
    match = re.search(r":\s*(\d+)\s*(ms|s|m)\s*\}\s*$", text)
    if match:
        text = match.group(0).lstrip(":").rstrip("} ").strip()
    match = re.fullmatch(r"(\d+)\s*(ms|s|m)", text)
    assert match, f"the timeout is not a duration this gate can read: {raw!r}"
    value, unit = match.groups()
    factor = {"ms": 1, "s": 1000, "m": 60_000}[unit]
    return int(value) * factor


def _redis() -> dict:
    document = yaml.safe_load(GATEWAY_YML.read_text(encoding="utf-8"))
    spring = document.get("spring") or {}
    data = spring.get("data") or {}
    redis = data.get("redis")
    assert redis is not None, (
        "the edge declares no spring.data.redis block — every Redis call it "
        "makes in the request path then runs with Spring's 60s default, and "
        "the 'never blocks' fallback arrives a minute late"
    )
    return redis


def test_the_edge_declares_a_bounded_command_timeout() -> None:
    raw = _redis().get("timeout")
    assert raw is not None, (
        "no spring.data.redis.timeout — the edge's in-path Redis calls are "
        "then bounded by Spring's default (60s), not by this stack's budget"
    )
    value = _duration_ms(raw)
    assert value != SPRING_DEFAULT_TIMEOUT_MS, (
        f"the timeout is {value}ms, which is Spring's default — declaring the "
        "default is not declaring a bound"
    )
    assert 0 < value <= MAX_TIMEOUT_MS, (
        f"the command timeout is {value}ms; the budget is {MAX_TIMEOUT_MS}ms — "
        "a decision made on the way through a request may not cost more than "
        "the request it protects"
    )


def test_the_edge_declares_a_bounded_connect_timeout() -> None:
    raw = _redis().get("connect-timeout")
    assert raw is not None, (
        "no spring.data.redis.connect-timeout — a Redis that accepts the "
        "socket and never answers would hold the caller for the connect "
        "default instead of the budget"
    )
    value = _duration_ms(raw)
    assert 0 < value <= MAX_TIMEOUT_MS, (
        f"the connect timeout is {value}ms; the budget is {MAX_TIMEOUT_MS}ms"
    )


def test_the_edge_route_table_still_parses_with_the_new_block() -> None:
    """A YAML edit that breaks the file is a broken edge. Read it again."""
    document = yaml.safe_load(GATEWAY_YML.read_text(encoding="utf-8"))
    assert "spring" in document
    assert document["spring"]["application"]["name"] == "specproof-gateway"
