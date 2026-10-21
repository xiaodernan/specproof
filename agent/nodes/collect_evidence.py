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

    # The two moments. The differential run captured the external world
    # AFTER the Base run and AFTER the Head run — the only two moments
    # that make a base/head comparison mean anything. A snapshot taken
    # once and compared with itself always says "nothing changed".
    #
    # The KEYS and OBJECTS to look at are the differential run's
    # business (it knows what the run touched); this node only reads
    # what was captured. One source of truth for "what to look at".
    base_snapshot = raw_state.get("external_state_base") or {}
    head_snapshot = raw_state.get("external_state_head") or {}
    separated = bool(base_snapshot) and bool(head_snapshot)

    fragments: list[Any] = []
    collected = 0

    # Redis
    try:
        if separated:
            from experiments.collectors import redis_fragment_from_snapshots
            from experiments.external_state import redis_states_from_dicts

            base_states = redis_states_from_dicts(base_snapshot)
            head_states = redis_states_from_dicts(head_snapshot)
            fragments.append(redis_fragment_from_snapshots(
                experiment_id=raw_state.get("job_id", "unknown"),
                base=base_states,
                head=head_states,
            ))
            collected += 1
        else:
            # The store could not be reached, or the differential run did
            # not capture the two moments. That is a DIFFERENT fact from
            # "the collector ran and found nothing" — a run that could
            # not look must not look like a run that looked.
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
        # The capsule coordinates are the pipeline's OWN objects — the
        # capsules the run produced (#342). The differential run's
        # snapshots cannot contain them (the capsules are made AFTER the
        # differential run), so the HEAD side of the object comparison is
        # taken NOW: "before the run there was no capsule object; after
        # it there is". The BASE side stays the differential's base
        # moment — a truthful empty-at-that-time view.
        capsule_refs = [
            str(ref) for ref in (raw_state.get("capsule_refs") or []) if ref
        ]
        if separated or capsule_refs:
            from experiments.collectors import object_fragment_from_snapshots
            from experiments.external_state import (
                build_object_store,
                capture_object_state,
                object_states_from_dicts,
            )

            base_states = object_states_from_dicts(base_snapshot)
            head_states = object_states_from_dicts(head_snapshot)
            if capsule_refs:
                store = build_object_store()
                fresh = capture_object_state(store, capsule_refs)
                # The freshly captured snapshot is plain dicts; the
                # states from the differential run are typed. Merging
                # the two shapes would produce a mapping whose values
                # are sometimes dicts and sometimes states — and the
                # first `.present` would raise.
                head_states = {
                    **head_states,
                    **object_states_from_dicts({"objects": fresh}),
                }
            fragments.append(object_fragment_from_snapshots(
                experiment_id=raw_state.get("job_id", "unknown"),
                base=base_states,
                head=head_states,
            ))
            collected += 1
        else:
            incr("collect_evidence_object_unavailable_total")
    except Exception:  # noqa: BLE001
        incr("collect_evidence_object_failed_total")
        pass

    # Assemble and persist the evidence pack.
    #
    # The pack is filed per CONTRACT: the collection carries a unique
    # index on (job_id, contract_id), and a pack is "the evidence for
    # this contract".
    #
    # WHICH fragments bear on a contract is decided by the contract's
    # own checker family: a contract checked by the redis checker is
    # about the redis state, so the redis fragment belongs in its pack
    # and the rabbitmq fragment does not. The OBJECT fragment is in
    # every pack: the capsule coordinates are the artifact that
    # contract's evidence was filed into.
    if fragments:
        contracts = [
            c for c in (raw_state.get("contracts") or [])
            if isinstance(c, dict) and c.get("id")
        ]
        if not contracts:
            incr("collect_evidence_no_fragments_total")
            return {
                "evidence_pack_saved": False,
                "evidence_pack_error": (
                    "no contract to file the pack under — a pack is keyed by "
                    "(job_id, contract_id)"
                ),
                "fragments_collected": collected,
            }
        if not raw_state.get("write_evidence_pack", True):
            # The pack was observed but NOT written. The audit trail
            # belongs to real verification jobs; a measurement's packs
            # would be junk nobody can delete by job id. The fragments
            # are still counted, so the run says what it observed.
            incr("collect_evidence_pack_not_written_total")
            return {
                "evidence_pack_saved": False,
                "evidence_pack_error": (
                    "not written: this run may not write the audit trail "
                    "(the caller opted out)"
                ),
                "fragments_collected": collected,
            }
        from datetime import UTC, datetime

        from storage.mongodb import MongoDBStore

        mongo = MongoDBStore()
        saved = 0
        failure = ""
        for contract in contracts:
            contract_id = str(contract.get("id"))
            relevant = _fragments_for(contract, fragments)
            pack = {
                "job_id": raw_state.get("job_id", ""),
                "contract_id": contract_id,
                "created_at": datetime.now(UTC).isoformat(),
                "fragments": [f.to_dict() for f in relevant],
            }
            try:
                mongo.save_evidence_pack(pack)
                saved += 1
            except Exception as exc:  # noqa: BLE001 — reported, not swallowed
                failure = f"mongo save: {exc}"
                break
        if saved:
            incr("collect_evidence_pack_saved_total")
            return {
                "evidence_pack_saved": True,
                "evidence_pack_error": failure or None,
                "fragments_collected": collected,
            }
        incr("collect_evidence_pack_failed_total")
        return {
            "evidence_pack_saved": False,
            "evidence_pack_error": failure or "no pack was written",
            "fragments_collected": collected,
        }
    else:
        incr("collect_evidence_no_fragments_total")
        return {
            "evidence_pack_saved": False,
            "evidence_pack_error": "no fragments collected",
            "fragments_collected": 0,
        }


#: The contract's checker family -> the observation surface that bears on
#: it. A contract checked by the redis checker is about the redis state;
#: the rabbitmq observation says nothing about it.
_SURFACE_BY_CHECKER: dict[str, str] = {
    "redis": "redis",
    "rabbitmq": "mq",
}

#: The object fragment belongs to EVERY pack: the capsule coordinates are
#: the artifact the contract's evidence was filed into.
_ALWAYS_RELEVANT = ("object",)


def _fragments_for(contract: dict[str, Any], fragments: list[Any]) -> list[Any]:
    """The fragments that bear on this contract.

    A pack is "the evidence for this contract" — so it carries what was
    observed about THAT contract's surface, not everything the run
    happened to observe. The object fragment is in every pack (the
    capsule coordinates are where this contract's evidence was filed);
    the rest is selected by the contract's own checker family.

    A contract whose family names no surface keeps the object fragment
    only — not "everything", because a pack full of unrelated
    observations is how a reader ends up believing the wrong thing was
    checked.
    """
    surface = _SURFACE_BY_CHECKER.get(str(contract.get("checker_type") or ""))
    keep: list[Any] = []
    for fragment in fragments:
        kind = str(getattr(fragment, "fragment_type", "") or "")
        if kind in _ALWAYS_RELEVANT or (surface and kind == surface):
            keep.append(fragment)
    return keep


def _derive_redis_keys(state: dict[str, Any]) -> list[str]:
    """The Redis keys the collector looks at.

    The differential run is what CAPTURES the snapshots now, and it
    uses the same default set from `experiments.external_state` — one
    source of truth for "what to look at".
    """
    from experiments.external_state import DEFAULT_REDIS_KEYS

    return list(DEFAULT_REDIS_KEYS)


def _derive_mq_routing_keys(state: dict[str, Any]) -> list[str]:
    """Derive RabbitMQ routing keys to observe from contract specs."""
    # order.created and email.changed are the known ones
    from experiments.external_state import DEFAULT_MQ_ROUTING_KEYS

    return list(DEFAULT_MQ_ROUTING_KEYS)
