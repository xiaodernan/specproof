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

#: The key families the profile knows, and the words that NAME them.
#: Both halves come from the profile: the words are what a requirement
#: says, the prefix is what the family is called in this domain. A prefix
#: without the words that introduce it is an address nobody can look up.
_KEY_FAMILIES: tuple[tuple[str, str, str], ...] = (
    # (family name, profile attribute for the prefix, profile attribute
    #  for the words)
    ("token", "user_token_key", "user_token_words"),
    ("cache", "user_cache_key", "user_cache_words"),
)


def declared_key_patterns(contract: dict[str, Any]) -> list[str]:
    """The key families the requirement DECLARES it is about.

    The SYNTAX lives in the spec language
    (``agent.contracts.parser.declared_key_patterns``) — this is the
    adapter that feeds it the contract's own text, for the contracts
    that do not carry the structured field yet.

    A requirement can name them outright ("observes keys: token:user:*").
    That is stronger than any heuristic: it cannot be mis-guessed, and it
    says what a requirement that uses other words ("credentials",
    "session store") could never match.
    """
    from agent.contracts.parser import declared_key_patterns as _declared

    text = " ".join(
        str(contract.get(field) or "")
        for field in ("requirement", "expected_behavior")
    )
    return _declared(text)


def key_family_of_contract(contract_id: str) -> str:
    """The profile key family this contract belongs to ("" when unknown).

    The contract id carries the family in its stem ("CACHE-01" ⇒ cache,
    "TOKEN_INVALIDATION-01" ⇒ token) and the profile says what each
    family is called in this domain. A contract of another family (an
    HTTP or SQL one) belongs to no key family ⇒ "".
    """
    stem = str(contract_id or "").split("-")[0].lower()
    if not stem:
        return ""
    for family, _prefix_attr, _words_attr in _KEY_FAMILIES:
        if stem.startswith(family) or family.startswith(stem):
            return family
    return ""


def key_patterns_for_family(family: str, patterns: list[str]) -> list[str]:
    """The declared patterns that belong to this family.

    A declaration names KEYS; the family that owns them is the one whose
    PROFILE PREFIX matches (the profile says what each family is called
    in this domain — a prefix without the family is an address nobody
    can look up). A pattern that matches no family belongs to no
    contract here: it is not attached to a guess.
    """
    if not family or not patterns:
        return []
    from agent.experiments.profile import DEMO_PROFILE

    prefix = ""
    for name, prefix_attr, _words_attr in _KEY_FAMILIES:
        if name == family:
            prefix = str(getattr(DEMO_PROFILE, prefix_attr, "") or "")
            break
    if not prefix:
        return []
    return [pattern for pattern in patterns if pattern.startswith(prefix)]


def key_patterns_for(
    contract: dict[str, Any], profile: Any | None = None,
) -> list[str]:
    """The Redis key patterns a contract is about.

    Three sources, in order of strength:

    1. the contract's STRUCTURED field (``observes_keys``) — the spec
       language owns that syntax now (#368), and a contract that carries
       the field does not have to say the keys in prose at all;
    2. what the requirement DECLARES in its text ("observes keys: …") —
       the same declaration, read through the spec language for the
       contracts that do not carry the field yet;
    3. otherwise, the family is derived from the contract's own text
       (which names the family) and the profile (which says what that
       family is called in this domain).

    A contract that names no family gets NOTHING observed — an empty
    pattern list, which the collector reports as NO_EVIDENCE. Guessing
    keys for it would be inventing evidence.
    """
    structured = [
        str(pattern) for pattern in (contract.get("observes_keys") or [])
        if str(pattern)
    ]
    if structured:
        return structured
    declared = declared_key_patterns(contract)
    if declared:
        return declared
    if profile is None:
        from agent.experiments.profile import DEMO_PROFILE

        profile = DEMO_PROFILE
    text = " ".join(
        str(contract.get(field) or "")
        for field in ("requirement", "expected_behavior", "forbidden_changes")
    ).lower()
    patterns: list[str] = []
    for _family, prefix_attr, words_attr in _KEY_FAMILIES:
        prefix = getattr(profile, prefix_attr, "") or ""
        words = getattr(profile, words_attr, ()) or ()
        if not prefix or not words:
            continue
        if any(str(word).lower() in text for word in words):
            pattern = f"{prefix}*"
            if pattern not in patterns:
                patterns.append(pattern)
    return patterns


#: The cap on how many keys one family contributes to a snapshot.
#:
#: It is a GUESS, not a measurement: the real distribution of a family's
#: key count is not known here (the same gap as the DEEP execution
#: budget). Two things keep the guess honest: the cap is configurable
#: (an operator with a real distribution can set it), and a truncated
#: observation SAYS it was truncated — a cap that is not announced is a
#: reader believing they saw every key.
DEFAULT_MAX_SCANNED_KEYS = 200

#: The environment variable that overrides the cap.
MAX_SCANNED_KEYS_ENV = "SPECPROOF_REDIS_SCAN_MAX_KEYS"


def max_scanned_keys() -> int:
    """The cap, from the environment when the operator named one."""
    import os

    raw = os.getenv(MAX_SCANNED_KEYS_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_SCANNED_KEYS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_SCANNED_KEYS
    return value if value > 0 else DEFAULT_MAX_SCANNED_KEYS


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
            # No declared default: this reader has no opinion about the
            # password (the URL form carries it when the environment
            # strips it) ⇒ saying "no default" is the truth, and it keeps
            # this knob's readers from declaring two different defaults
            # (#383).
            password = os.getenv("REDIS_PASSWORD")
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
    *,
    max_keys: int | None = None,
    truncated_out: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """One Redis snapshot, as plain dicts.

    An unreachable client yields an EMPTY snapshot — the caller decides
    what that means (nothing was observed), and the empty dict cannot be
    mistaken for "every key is absent".

    ``patterns`` are the key FAMILIES the contracts declared (e.g.
    "token:user:*"); they are scanned, because the ids inside a family
    belong to the domain and cannot be guessed.

    A family with more keys than ``max_keys`` is CAPPED, and the
    pattern is appended to ``truncated_out`` — a cap that is not
    announced is a reader believing they saw every key.
    """
    if client is None:
        return {}
    limit = max_scanned_keys() if max_keys is None else max_keys
    collector = RedisStateCollector(client)
    states = dict(collector.snapshot(keys))
    if patterns:
        for key, state in collector.snapshot_by_pattern(
            patterns, max_keys=limit
        ).items():
            states.setdefault(key, state)
    if truncated_out is not None:
        truncated_out.extend(collector.truncated_patterns)
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
    max_keys: int | None = None,
) -> dict[str, Any]:
    """One snapshot of everything observable outside the workspaces.

    The shape is stable and JSON-safe so it can travel through the
    pipeline state between the differential run and the evidence
    collection:

        {"redis": {key: {...}}, "objects": {ref: {...}}}

    ``truncated_patterns`` says a key family had more keys than the cap
    allowed. A cap that is not announced is a reader believing they saw
    every key — so the truncation travels with the observation, at the
    TOP level (inside the key map it would be mistaken for a key).

    ``redis_observed`` / ``objects_observed`` say whether each store
    could be reached AT ALL (#369). Without them, "we did not look" and
    "we looked and there was nothing" travel as the same empty map —
    and only the first one is a fact about the pipeline.
    """
    limit = max_scanned_keys() if max_keys is None else max_keys
    snapshot: dict[str, Any] = {
        "redis": {},
        "objects": capture_object_state(object_store, object_refs),
        "redis_observed": redis_client is not None,
        "objects_observed": object_store is not None,
    }
    truncated: list[str] = []
    snapshot["redis"] = capture_redis_state(
        redis_client, redis_keys, patterns=redis_patterns,
        max_keys=limit, truncated_out=truncated,
    )
    if truncated:
        # The observation was CAPPED. A cap that is not announced is a
        # reader believing they saw every key of the family — so the
        # truncation travels with the observation, at the TOP level
        # (inside the key map it would be mistaken for a key).
        snapshot["truncated_patterns"] = truncated
    return snapshot


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
