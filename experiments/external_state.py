"""External state capture — the observable world outside the two workspaces.

The Base and Head workspaces are two directories, but they talk to the
SAME Redis / MinIO / RabbitMQ. A differential run therefore leaves a
trace in the shared services, and the two traces differ exactly when the
Head code behaves differently from the Base code.

That difference can only be observed by taking a snapshot at TWO
moments: after the Base run and after the Head run. A snapshot taken
once and compared against itself always says "nothing changed" — the
collector would be honest and useless at the same time.

This module owns:
- building the clients (from the environment), so every caller asks
  for the same world;
- taking one snapshot, in a form that survives being carried through
  the pipeline state (plain dicts, not live client handles).

The snapshot is OBSERVATION only. Absence is recorded as absence, and
an unreachable service yields an empty snapshot — never an invented one.
"""

from __future__ import annotations

import os
from typing import Any

from experiments.collectors import (
    ObjectState,
    ObjectStoreLike,
    RedisLike,
    RedisStateCollector,
)

#: The Redis keys the demo's cache-aside user reads use. The full
#: wiring derives these from the compiled contracts; until then this is
#: the known set, and the ledger says so.
DEFAULT_REDIS_KEYS: tuple[str, ...] = ("user:cache:1", "user:cache:2")

#: The routing keys the demo publishes on.
DEFAULT_MQ_ROUTING_KEYS: tuple[str, ...] = ("order.created", "email.changed")

#: The profile's key families and the words that NAME them in a
#: requirement. A contract's own text says which family of keys it is
#: about ("session tokens ... invalidated in Redis"), and the PROFILE
#: says what that family is called in this domain ("token:user:").
#:
#: The two halves must meet: the text names a family, the profile gives
#: its address. A contract that names neither is observed on NOTHING —
#: which is honest, and reports NO_EVIDENCE. Guessing keys for it would
#: be inventing evidence.
_KEY_FAMILY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("token", ("token", "session")),
    ("cache", ("cache",)),
)


def key_patterns_for(
    contract: dict[str, Any], profile: Any | None = None,
) -> list[str]:
    """The Redis key patterns a contract is about.

    Derived from TWO facts that already exist: the contract's own text
    (which names the family) and the profile (which says what that
    family is called in this domain).
    """
    if profile is None:
        from agent.experiments.profile import DEMO_PROFILE

        profile = DEMO_PROFILE
    prefixes = {
        "token": getattr(profile, "user_token_key", ""),
        "cache": getattr(profile, "user_cache_key", ""),
    }
    text = " ".join(
        str(contract.get(field) or "")
        for field in ("requirement", "expected_behavior", "forbidden_changes")
    ).lower()
    patterns: list[str] = []
    for family, words in _KEY_FAMILY_WORDS:
        prefix = prefixes.get(family) or ""
        if not prefix:
            continue
        if any(word in text for word in words):
            pattern = f"{prefix}*"
            if pattern not in patterns:
                patterns.append(pattern)
    return patterns


def build_redis_client() -> Any | None:
    """Build a Redis client from the environment. None when unreachable.

    Two forms are accepted, and the URL one comes FIRST because it is
    the only form that survives a test harness that strips credentials
    from the environment (the repo's conftest removes REDIS_PASSWORD on
    purpose, so an integration leg has to carry the credential in a URL
    the way MYSQL_URL does):

    - ``REDIS_URL`` — a full ``redis://[:password@]host:port/db`` URL;
    - ``REDIS_HOST`` / ``REDIS_PORT`` / ``REDIS_PASSWORD`` — the parts.

    A client that cannot be built is a fact about the world ("we could
    not look"), and it is reported as such by the caller — never as an
    empty-but-present observation.
    """
    try:
        import redis
    except Exception:  # noqa: BLE001 — the driver is optional
        return None
    try:
        url = os.getenv("REDIS_URL", "").strip()
        if url:
            client = redis.Redis.from_url(
                url,
                socket_connect_timeout=2,
                socket_timeout=2,
                decode_responses=True,
            )
        else:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            password = os.getenv("REDIS_PASSWORD", None)
            client = redis.Redis(
                host=host, port=port, password=password,
                socket_connect_timeout=2, socket_timeout=2,
                decode_responses=True,
            )
        client.ping()
        return client
    except Exception:  # noqa: BLE001 — unreachable is a fact, not a crash
        return None


def build_object_store() -> Any | None:
    """Build the object-store client from the environment. None when unreachable.

    The client is the PRODUCTION one (``storage.minio.MinIOClient``), and
    the configuration comes from ``storage.minio.MinIOConfig`` — the SAME
    source the product uses. Two sets of environment variable names for
    "how do I reach the object store" would be two truths, and the second
    one would silently point somewhere else. A raw ``Minio`` handle would
    also be the wrong SHAPE: the collector speaks
    ``object_exists``/``object_stat``, which only the wrapper speaks.
    """
    try:
        from storage.minio import MinIOClient
    except Exception:  # noqa: BLE001 — the driver is optional
        return None
    try:
        client = MinIOClient()
        if not client.is_ready():
            return None
        return client
    except Exception:  # noqa: BLE001 — unreachable is a fact, not a crash
        return None


def capture_redis_state(
    client: RedisLike | None,
    keys: tuple[str, ...] | list[str] = DEFAULT_REDIS_KEYS,
    patterns: tuple[str, ...] | list[str] = (),
) -> dict[str, dict[str, Any]]:
    """One Redis snapshot, as plain dicts.

    An unreachable client yields an EMPTY snapshot — the caller decides
    what that means (nothing was observed), and the empty dict cannot be
    mistaken for "every key is absent".

    ``patterns`` are the key FAMILIES the contracts declared (e.g.
    "token:user:*"); they are scanned, because the ids inside a family
    belong to the domain and cannot be guessed.
    """
    if client is None:
        return {}
    collector = RedisStateCollector(client)
    states = dict(collector.snapshot(keys))
    if patterns:
        for key, state in collector.snapshot_by_pattern(patterns).items():
            states.setdefault(key, state)
    return {key: state.to_dict() for key, state in states.items()}


def capture_object_state(
    store: ObjectStoreLike | None,
    refs: tuple[str, ...] | list[str] = (),
) -> dict[str, dict[str, Any]]:
    """One object-store snapshot, as plain dicts."""
    if store is None:
        return {}
    from experiments.collectors import ObjectStateCollector

    collector = ObjectStateCollector(store)
    return {
        ref: state.to_dict() for ref, state in collector.snapshot(refs).items()
    }


def capture_external_state(
    *,
    redis_client: Any | None = None,
    object_store: Any | None = None,
    redis_keys: tuple[str, ...] | list[str] = DEFAULT_REDIS_KEYS,
    object_refs: tuple[str, ...] | list[str] = (),
    redis_patterns: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    """One snapshot of everything observable outside the workspaces.

    The shape is stable and JSON-safe so it can travel through the
    pipeline state between the differential run and the evidence
    collection:

        {"redis": {key: {...}}, "objects": {ref: {...}}}
    """
    return {
        "redis": capture_redis_state(
            redis_client, redis_keys, patterns=redis_patterns
        ),
        "objects": capture_object_state(object_store, object_refs),
    }


def redis_states_from_dicts(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Rebuild the typed key states a fragment needs from a stored snapshot."""
    if not snapshot:
        return {}
    from experiments.collectors import KeyState

    states: dict[str, Any] = {}
    for key, raw in (snapshot.get("redis") or {}).items():
        data = dict(raw)
        states[key] = KeyState(
            key=str(data.get("key") or key),
            present=bool(data.get("present")),
            value=data.get("value"),
            ttl_seconds=data.get("ttl_seconds"),
        )
    return states


def object_states_from_dicts(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """Rebuild the typed object states a fragment needs."""
    if not snapshot:
        return {}
    states: dict[str, Any] = {}
    for ref, raw in (snapshot.get("objects") or {}).items():
        data = dict(raw)
        states[ref] = ObjectState(
            bucket=str(data.get("bucket") or ""),
            object_name=str(data.get("object_name") or ""),
            present=bool(data.get("present")),
            size_bytes=int(data.get("size_bytes") or 0),
            content_type=str(data.get("content_type") or ""),
            sha256=str(data.get("sha256") or ""),
            version=str(data.get("version") or ""),
        )
    return states


__all__ = [
    "DEFAULT_MQ_ROUTING_KEYS",
    "DEFAULT_REDIS_KEYS",
    "build_object_store",
    "build_redis_client",
    "capture_external_state",
    "capture_object_state",
    "capture_redis_state",
    "object_states_from_dicts",
    "redis_states_from_dicts",
]
