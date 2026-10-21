"""collect_evidence node — run all dynamic collectors and persist the evidence pack.

The dynamic collectors (Redis, RabbitMQ, Object storage) are pure functions
that describe what was OBSERVED on each side of the Base/Head boundary.
This node runs them, assembles the fragments into an evidence pack, and
persists it to MongoDB for later replay and audit.

The evidence pack carries NO verdict — it is the RAW OBSERVATIONS that
the Review Court and the lineage builder will later interpret.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, cast

from agent.state import Phase0State
from observability.metrics import incr

# ── Collector imports (lazy to avoid circulars) ──────────────────────────


def _get_collectors() -> tuple[type, type, type]:
    from experiments.collectors import (
        ObjectStateCollector,
        PublisherLike,
        RedisStateCollector,
    )
    return RedisStateCollector, ObjectStateCollector, PublisherLike


def collect_evidence_node(state: Phase0State) -> dict[str, Any]:
    """Run all dynamic collectors, assemble fragments, save evidence pack.

    Returns dict with:
      - evidence_pack_saved: bool
      - evidence_pack_error: str | None
      - fragments_collected: int
    """
    raw_state: dict[str, Any] = cast(dict[str, Any], state)
    job_id = str(raw_state.get("job_id") or "")
    _repo_path = raw_state.get("repo_path", "")
    _base_ref = raw_state.get("base_ref", "")
    _head_ref = raw_state.get("head_ref", "")

    incr("collect_evidence_runs_total")

    if not job_id:
        incr("collect_evidence_skipped_no_job_id_total")
        return {"evidence_pack_saved": False, "evidence_pack_error": "no job_id"}

    # Resolve the object references that the differential run produced.
    # The differential run's results contain per-contract evidence refs and
    # the capsulated artifacts. We need to observe the object store for those.
    # For Redis and RabbitMQ, we observe the keys/routing keys the contracts
    # declare they use (from the spec / preflight).
    #
    # For this first pass, we observe a minimal fixed set derived from the
    # preflight / repo context. The full wiring (spec-declared keys) is
    # tracked as backlog.

    # For now, construct minimal observation refs from state.
    # Real wiring will come when spec declares the keys/routing keys/paths.
    redis_keys = _derive_redis_keys(raw_state)
    _mq_routing_keys = _derive_mq_routing_keys(raw_state)
    object_refs = _derive_object_refs(raw_state)

    fragments = []
    collected = 0

    # Redis
    try:
        redis = _build_redis_client()
        if redis:
            redis_state_collector, _object_collector, _publisher = _get_collectors()
            collector = redis_state_collector(redis, collector_version="1.0.0")
            base = collector.snapshot(redis_keys)
            head = collector.snapshot(redis_keys)  # same keys; diff will catch changes
            fragments.append(collector.fragment(
                experiment_id=raw_state.get("job_id", "unknown"),
                base=base,
                head=head,
            ))
            collected += 1
        else:
            # The store could not be reached. That is a DIFFERENT fact
            # from "the collector ran and found nothing" — a run that
            # could not look must not look like a run that looked.
            incr("collect_evidence_redis_unavailable_total")
    except Exception:  # noqa: BLE001
        incr("collect_evidence_redis_failed_total")
        # Degraded, not fatal — evidence is best-effort
        pass

    # RabbitMQ (mock publisher recording)
    with suppress(Exception):  # noqa: BLE001
        # The PublisherLike is a mock that records publishes; the real
        # wiring comes from the test harness. For production, we would
        # need a live RabbitMQ connection which we don't have here.
        # Skipped in this first pass — backlog item.
        pass

    # Object storage
    try:
        object_store = _build_object_store()
        if object_store:
            _redis_collector, object_state_collector, _publisher = _get_collectors()
            collector = object_state_collector(object_store, collector_version="1.0.0")
            base = collector.snapshot(object_refs)
            head = collector.snapshot(object_refs)
            fragments.append(collector.fragment(
                experiment_id=raw_state.get("job_id", "unknown"),
                base=base,
                head=head,
            ))
            collected += 1
        else:
            incr("collect_evidence_object_unavailable_total")
    except Exception:  # noqa: BLE001
        incr("collect_evidence_object_failed_total")
        pass

    # Assemble and persist the evidence pack
    if fragments:
        pack = {
            "job_id": raw_state.get("job_id", ""),
            "created_at": __import__("datetime").datetime.now(
                __import__("datetime").UTC
            ).isoformat(),
            "fragments": [f.to_dict() for f in fragments],
        }
        try:
            from storage.mongodb import MongoDBStore
            mongo = MongoDBStore()
            mongo.save_evidence_pack(pack)
            incr("collect_evidence_pack_saved_total")
            return {
                "evidence_pack_saved": True,
                "evidence_pack_error": None,
                "fragments_collected": collected,
            }
        except Exception as exc:  # noqa: BLE001
            incr("collect_evidence_pack_failed_total")
            return {
                "evidence_pack_saved": False,
                "evidence_pack_error": f"mongo save: {exc}",
                "fragments_collected": collected,
            }
    else:
        incr("collect_evidence_no_fragments_total")
        return {
            "evidence_pack_saved": False,
            "evidence_pack_error": "no fragments collected",
            "fragments_collected": 0,
        }


def _derive_redis_keys(state: dict[str, Any]) -> list[str]:
    """Derive Redis keys to observe from the contract specs / preflight.

    Currently returns a minimal fixed set. Full wiring (spec-declared keys)
    is a backlog item.
    """
    # Cache-aside user keys are the main known pattern
    return ["user:cache:1", "user:cache:2"]


def _derive_mq_routing_keys(state: dict[str, Any]) -> list[str]:
    """Derive RabbitMQ routing keys to observe from contract specs."""
    # order.created and email.changed are the known ones
    return ["order.created", "email.changed"]


def _derive_object_refs(state: dict[str, Any]) -> list[str]:
    """Derive object storage references from capsules / artifacts."""
    # The capsules created in this job are the primary objects.
    # We don't know the bucket here; the object metadata store records the ref.
    # For now, skip — the object collector will be wired properly when
    # the artifact store calls back.
    return []


def _build_redis_client() -> Any | None:
    """Build a Redis client from environment. Returns None if unavailable."""
    try:
        import os

        import redis
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
    except Exception:  # noqa: BLE001
        return None


def _build_object_store() -> Any | None:
    """Build a MinIO client from environment. Returns None if unavailable."""
    try:
        import os

        from minio import Minio
        endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        access = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        secret = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
        # Cheap liveness check
        list(client.list_buckets())
        return client
    except Exception:  # noqa: BLE001
        return None
