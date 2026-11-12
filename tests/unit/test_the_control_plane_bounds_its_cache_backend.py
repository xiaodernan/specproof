"""The control plane must BOUND its cache backend — and the number it claims
in the source must be the number the deployment sets.

WHY. ``RedisJobReadCache``'s safety argument is written in its own javadoc:
"every Redis call is bounded in time by configuration, not by hope" and "the
worst case is one wasted round trip". The argument names the number it needs:
``spring.data.redis.timeout`` / ``connect-timeout`` set to **50ms**.

That number was NOT set anywhere. Spring's default command timeout is 60
seconds — so the deployment did the exact thing the javadoc warns about: a
dead Redis held every GET for a minute, and the breaker's five consecutive
failures held five request threads for five minutes. The class was right and
the configuration was absent, and nothing said so.

WHAT THIS GATE DOES AND DOES NOT CLAIM. It reads ``application.yml``
statically: it pins that a finite bound is *declared*, and that the declared
number is the number the source claims. It cannot prove the bound is wired
into the request path — that is what the Java leg
(``JobCacheBreakerPressureTest``) measures against a scripted backend.
Both are needed: this one catches the deleted config line, the Java one
catches the config line that does nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTROL_PLANE_YML = (
    ROOT / "services" / "control-plane" / "src" / "main" / "resources"
    / "application.yml"
)
CACHE_SOURCE = (
    ROOT / "services" / "control-plane" / "src" / "main" / "java"
    / "dev" / "specproof" / "controlplane" / "cache" / "RedisJobReadCache.java"
)
PRESSURE_TEST = (
    ROOT / "services" / "control-plane" / "src" / "test" / "java"
    / "dev" / "specproof" / "controlplane" / "cache" / "JobCacheBreakerPressureTest.java"
)

#: The budget the cache's own javadoc states, and the one this gate accepts.
#: A cache read that costs more than this is not worth the round trip it
#: saves, and a bound larger than it turns "the cache is down" into "the API
#: is down" — which is the outage the breaker was added to prevent.
MAX_TIMEOUT_MS = 50

#: Spring's own default when the property is absent: 60 seconds. A gate that
#: only checked "some timeout exists" would pass on a value that holds a
#: request thread for a minute.
SPRING_DEFAULT_TIMEOUT_MS = 60_000


def _duration_ms(raw: object) -> int:
    """Parse Spring's duration spellings: ``50ms``, ``1s``, ``2m``."""
    text = str(raw)
    # ``${ENV:50ms}`` — the deployment may override it, and the DEFAULT is
    # what this gate judges (an operator who overrides it owns that choice).
    match = re.search(r":\s*(\d+)\s*(ms|s|m)\s*\}\s*$", text)
    if match:
        text = match.group(0).lstrip(":").rstrip("} ").strip()
    match = re.fullmatch(r"(\d+)\s*(ms|s|m)", text)
    assert match, f"the timeout is not a duration this gate can read: {raw!r}"
    value, unit = match.groups()
    factor = {"ms": 1, "s": 1000, "m": 60_000}[unit]
    return int(value) * factor


def _redis() -> dict:
    document = yaml.safe_load(CONTROL_PLANE_YML.read_text(encoding="utf-8"))
    spring = document.get("spring") or {}
    data = spring.get("data") or {}
    redis = data.get("redis")
    assert redis is not None, (
        "the control plane declares no spring.data.redis block — the cache's "
        "command timeout falls back to Spring's default, which is 60s, and a "
        "dead Redis then holds every GET for a minute"
    )
    return redis


def test_the_cache_backend_call_is_bounded() -> None:
    raw = _redis().get("timeout")
    assert raw is not None, (
        "no spring.data.redis.timeout — the cache's own javadoc says the "
        "backend call is bounded by configuration, and nothing sets it"
    )
    value = _duration_ms(raw)
    assert value != SPRING_DEFAULT_TIMEOUT_MS, (
        f"the timeout is {value}ms, which is Spring's default — declaring the "
        "default is not declaring a bound"
    )
    assert 0 < value <= MAX_TIMEOUT_MS, (
        f"the command timeout is {value}ms; the budget is {MAX_TIMEOUT_MS}ms — "
        "a cache read that costs more than the database read it saves is not "
        "a cache, it is a second database with worse manners"
    )


def test_the_connection_is_bounded_too() -> None:
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


def test_the_number_the_source_claims_is_the_number_the_deployment_sets() -> None:
    """The javadoc names the bound. The deployment must set THAT number.

    A source comment that says "50ms" while the configuration says 2s (or
    says nothing) is a lie in the one place a reader goes to check. This leg
    reads the claim out of the Java source and compares it with the
    declaration.
    """
    source = CACHE_SOURCE.read_text(encoding="utf-8")
    claim = re.search(
        r"spring\.data\.redis\.timeout.{0,160}?are set to[^0-9]{0,24}(\d+)\s*ms",
        source,
        re.S,
    )
    assert claim, (
        "the cache's javadoc no longer states the bound it depends on — the "
        "claim it makes is what this gate compares with the deployment"
    )
    claimed_ms = int(claim.group(1))
    declared_ms = _duration_ms(_redis().get("timeout"))
    assert claimed_ms == declared_ms, (
        f"the source claims {claimed_ms}ms and the deployment declares "
        f"{declared_ms}ms — one of them is wrong, and a reader who checks "
        "only one of them is misled"
    )


def test_the_java_behaviour_leg_exists() -> None:
    """The static gate catches a deleted line; the Java leg catches a line
    that does nothing. Both, or neither of them means anything."""
    assert PRESSURE_TEST.is_file(), (
        "the control plane's cache pressure measurement is gone — the "
        "declared bound would be an untested claim"
    )
    source = PRESSURE_TEST.read_text(encoding="utf-8")
    assert "JobCacheBreaker" in source, PRESSURE_TEST
