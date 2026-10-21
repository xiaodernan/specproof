"""The external observation — computed once, read by everyone.

Two readers want the SAME comparison: the evidence pack files it as a
fragment, and the matrix row has to disclose what that comparison could
not see. Two implementations of one comparison drift, and then the
reader holds two versions of the truth — so the comparison lives here
and both readers call it.

Nothing in this module talks to a store. The two moments come from the
differential run (``external_state_base`` / ``external_state_head``) and
the key family comes from the contract's own declaration, so the
observation is a pure function of the state. That is what lets the
verdict layer read it without waiting for the evidence pack: the pack is
filed after the capsules, and the capsules come after the matrix.

What the observation CAN and CANNOT say is stated by the collectors (in
the fragment's ``extension``). This module only turns those facts into
the prose the verdict layer shows on the row — it never decides
anything, and it never invents an observation that was not made.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from typing import Any

#: The disclosure vocabulary. These are NOT verdict reasons: they never
#: change a row's ``result`` and the verdict layer never quotes them
#: outward (see evidence/verdict.py — the verdict quotes only controlled
#: codes). They are the row's own prose about the LIMITS of what was
#: observed on the outside of the JVM.
LIMIT_NOT_OBSERVED = (
    "外部存储答了, 但这一族里什么也没有"
    "——本行的判定只来自测试自身的断言"
)
LIMIT_STORE_UNREACHABLE = (
    "外部存储不可达: 这一面**没有去看**"
    "——「没看」不等于「看了没有」"
)
LIMIT_MOMENTS_NOT_COMPARABLE = (
    "两个时刻不可比: 两次运行之间没有把外部世界放回去,"
    "Base 那一跑造出来的键会读成「未变化」"
)
LIMIT_VALUE_LEVEL_LEFTOVERS = (
    "值层面无法区分: {count} 个键仍带着 Base 那一跑的值"
    "——对这些键, 比较只能说键是否存在与 TTL, 不能说值是否变了"
)
LIMIT_TRUNCATED = (
    "观测被截断: {count} 个键族超过了扫描上限——不是每个键都被看到了"
)
LIMIT_MQ_BROKER_SIDE = (
    "broker 那一面观测不到: 发布发生在测试自己的 JVM 里"
    "(surefire 进程内), 片段里记的是**测试自己的报告**"
    "(它数到的 routing key 与发布次数), 不是 broker 侧的视图"
)
LIMIT_MQ_ONE_SIDE = (
    "只有一侧报告了自己的发布: 另一侧没有报告行"
    "——比较跨的不是两个时刻, 而是一侧与「什么都没说」"
)

#: The contract's checker family -> the surface its observation lives on.
_SURFACE_BY_CHECKER: dict[str, str] = {
    "redis": "redis",
    "rabbitmq": "mq",
}


def observations(
    state: Mapping[str, Any],
    contracts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """The per-contract observations, keyed by contract id.

    A contract with no observation is simply absent from the mapping —
    the caller can tell "observed" from "not observed" without reading
    a status word.

    The snapshots are read ONCE, not once per contract: the key states
    are rebuilt from them a single time, so a matrix with a hundred
    contracts does not rebuild the same hundred keys a hundred times.
    """
    from experiments.external_state import redis_states_from_dicts

    base_snapshot = state.get("external_state_base") or {}
    head_snapshot = state.get("external_state_head") or {}
    # The two moments, or nothing: a run whose snapshots were never
    # captured did not LOOK, and must not carry an observation that
    # reads like it looked and saw nothing.
    separated = bool(base_snapshot) and bool(head_snapshot)
    base_states = (
        redis_states_from_dicts(dict(base_snapshot)) if base_snapshot else {}
    )
    head_states = (
        redis_states_from_dicts(dict(head_snapshot)) if head_snapshot else {}
    )
    truncated = _truncated_patterns(base_snapshot, head_snapshot)
    # Whether the collector could reach the store when it took those
    # moments (#369). A snapshot taken while the store was down carries
    # the flag; a snapshot without it predates the flag and is treated
    # as "we looked" (the old behaviour).
    store_reachable = bool(base_snapshot.get("redis_observed", True))

    observations_by_contract: dict[str, Any] = {}
    chosen = state.get("contracts") if contracts is None else contracts
    for contract in chosen or []:
        if not isinstance(contract, Mapping):
            continue
        contract_id = str(contract.get("id") or "").strip()
        if not contract_id:
            continue
        observation = _observe(
            state, contract, base_states, head_states, truncated, separated,
            store_reachable,
        )
        if observation is not None:
            observations_by_contract[contract_id] = observation
    return observations_by_contract


def observation_for(
    state: Mapping[str, Any], contract: Mapping[str, Any],
) -> Any | None:
    """The observation for ONE contract, or None when there is none.

    None means "there was nothing to observe for this contract" — not
    "the collector ran and found nothing". A contract that names no key
    family gets None (guessing keys for it would be inventing
    evidence), and so does a run whose two moments were never captured
    (the store was unreachable, or the differential never ran).
    """
    contract_id = str(contract.get("id") or "").strip()
    return observations(state, contracts=[contract]).get(contract_id)


def _observe(
    state: Mapping[str, Any],
    contract: Mapping[str, Any],
    base_states: Mapping[str, Any],
    head_states: Mapping[str, Any],
    truncated: list[str],
    separated: bool,
    store_reachable: bool,
) -> Any | None:
    """The observation for one contract, on the surface it is about."""
    surface = _SURFACE_BY_CHECKER.get(str(contract.get("checker_type") or ""))
    if surface == "redis":
        if not separated:
            # The two moments were never captured: this run did not LOOK,
            # and an observation that reads like it looked and saw nothing
            # would be a different fact.
            return None
        return _redis_observation(
            state, contract, base_states, head_states, truncated,
            store_reachable,
        )
    if surface == "mq":
        return _mq_observation(state, contract)
    return None


def _redis_observation(
    state: Mapping[str, Any],
    contract: Mapping[str, Any],
    base_states: Mapping[str, Any],
    head_states: Mapping[str, Any],
    truncated: list[str],
    store_reachable: bool = True,
) -> Any | None:
    """The redis observation: the two moments, on this contract's family."""
    from experiments.external_state import key_patterns_for

    patterns = key_patterns_for(dict(contract))
    if not patterns:
        return None

    from experiments.collectors import redis_fragment_from_snapshots

    return redis_fragment_from_snapshots(
        experiment_id=str(state.get("job_id") or "unknown"),
        base=_states_matching(base_states, patterns),
        head=_states_matching(head_states, patterns),
        truncated_patterns=[
            pattern for pattern in truncated
            if any(fnmatch.fnmatch(pattern, family) for family in patterns)
        ],
        world_reset=state.get("external_reset") or {},
        # Whether the collector could reach the store at all (#369): a
        # snapshot taken while the store was down carries the flag, and
        # the fragment then says "we did not look" instead of "the
        # family was empty".
        store_reachable=store_reachable,
    )


def _mq_observation(
    state: Mapping[str, Any], contract: Mapping[str, Any],
) -> Any | None:
    """The MQ observation: what the TEST reported about its own publishes.

    The broker side of a publish cannot be observed from out here (#354):
    the generated test runs in-process (Maven surefire), so the publish
    happens inside the test's JVM. What the pipeline CAN read is the
    test's own report — the line the generated test prints with the
    routing key and the count it asserted — which the differential
    captured with the run's output.

    So the fragment records the test's report and says, in its
    extension, that this is the test's report and not a broker-side
    view. It does not pretend the broker was observed.
    """
    from datetime import UTC, datetime

    from evidence.fragments import MqObservation
    from experiments.collectors import (
        STATUS_AMBIGUOUS,
        STATUS_COMPLIANT,
        STATUS_NO_EVIDENCE,
        compare_publish_observations,
    )
    from experiments.mq_report import parse_mq_observations

    contract_id = str(contract.get("id") or "").strip()
    diff = _diff_for(state, contract_id)
    base = parse_mq_observations(str(diff.get("base_output") or ""))
    head = parse_mq_observations(str(diff.get("head_output") or ""))
    comparison = compare_publish_observations(base, head)
    observed = bool(base.get("observed") or head.get("observed"))
    both = bool(base.get("observed") and head.get("observed"))
    if not observed:
        status = STATUS_NO_EVIDENCE
    elif comparison["changed_count"] == 0:
        status = STATUS_COMPLIANT
    else:
        status = STATUS_AMBIGUOUS
    return MqObservation(
        experiment_id=str(state.get("job_id") or "unknown"),
        fragment_type="mq",
        collector_version="1.0.0",
        collected_at=datetime.now(UTC).isoformat(),
        base=base,
        head=head,
        normalization={
            "publish_count": (
                "the number of publish invocations the generated test counted "
                "and reported (its SPECPROOF_MQ line) — the test runs "
                "IN-PROCESS (Maven surefire), so the publish happens inside "
                "the test's JVM: this is the TEST's own report, not a "
                "broker-side view"
            ),
            "routing_keys": "the routing keys the test reported publishing to",
            "payload_digests": (
                "empty: the test reports the routing key and the count, not "
                "the payload's bytes — so the payload dimension of the "
                "comparison says nothing, rather than pretending they matched"
            ),
        },
        comparison=comparison,
        status=status,
        confidence=1.0 if observed else 0.0,
        evidence_ref=None,
        reproducibility="reproducible",
        extension={
            "observed_any_publish": observed,
            "base_observed": bool(base.get("observed")),
            "head_observed": bool(head.get("observed")),
            "both_sides_observed": both,
            "observed_via": (
                "the test's own report — the generated test prints what it "
                "counted (SPECPROOF_MQ ...) and the pipeline reads that line "
                "out of the captured test output"
            ),
            "not_observable_reason": (
                "the broker side cannot be observed from out here: the "
                "generated test runs in-process (Maven surefire), so the "
                "publish happens inside the test's JVM"
            ),
        },
    )


def observation_limits(observation: Any | None) -> list[str]:
    """What the observation could NOT say, in the reader's language.

    An empty list means "the observation had no limits to declare" —
    which is NOT the same as "there was no observation": that case is
    ``None`` and the caller says so separately.
    """
    if observation is None:
        return []
    from experiments.collectors import STATUS_NO_EVIDENCE

    extension = getattr(observation, "extension", {}) or {}
    kind = str(getattr(observation, "fragment_type", "") or "")
    limits: list[str] = []
    if kind == "mq":
        limits.append(LIMIT_MQ_BROKER_SIDE)
        if not extension.get("both_sides_observed", True):
            limits.append(LIMIT_MQ_ONE_SIDE)
        return limits
    if str(getattr(observation, "status", "") or "") == STATUS_NO_EVIDENCE:
        if extension.get("store_reachable", True):
            limits.append(LIMIT_NOT_OBSERVED)
        else:
            # The store was unreachable: we did not look. Saying "the
            # family was empty" here would be a claim we cannot make
            # (#369).
            limits.append(LIMIT_STORE_UNREACHABLE)
    if not extension.get("moments_comparable", True):
        limits.append(LIMIT_MOMENTS_NOT_COMPARABLE)
    leftover_count = int(extension.get("value_level_leftover_count") or 0)
    if leftover_count > 0:
        limits.append(LIMIT_VALUE_LEVEL_LEFTOVERS.format(count=leftover_count))
    truncated = list(extension.get("truncated_patterns") or [])
    if truncated:
        limits.append(LIMIT_TRUNCATED.format(count=len(truncated)))
    return limits


def observation_status(observation: Any | None) -> str:
    """The observation's status word, or "" when there was no observation."""
    if observation is None:
        return ""
    return str(getattr(observation, "status", "") or "")


def _diff_for(
    state: Mapping[str, Any], contract_id: str,
) -> Mapping[str, Any]:
    """The differential's entry for this contract, or an empty mapping."""
    for diff in state.get("diff_results") or []:
        if not isinstance(diff, Mapping):
            continue
        if str(diff.get("contract_id") or "") == contract_id:
            return diff
    return {}


def _truncated_patterns(*snapshots: Any) -> list[str]:
    """The key families whose scan hit the cap, across the snapshots."""
    patterns: list[str] = []
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        for pattern in snapshot.get("truncated_patterns") or []:
            text = str(pattern)
            if text and text not in patterns:
                patterns.append(text)
    return patterns


def _states_matching(
    states: Mapping[str, Any], patterns: list[str],
) -> dict[str, Any]:
    """The states whose key matches one of the patterns.

    Redis' MATCH is a glob: "token:user:*" means "that family". The
    comparison here is the same idea, done on the key we already have.
    """
    if not patterns:
        return {}
    return {
        key: state
        for key, state in states.items()
        if any(fnmatch.fnmatch(key, pattern) for pattern in patterns)
    }


__all__ = [
    "LIMIT_MOMENTS_NOT_COMPARABLE",
    "LIMIT_MQ_BROKER_SIDE",
    "LIMIT_MQ_ONE_SIDE",
    "LIMIT_NOT_OBSERVED",
    "LIMIT_TRUNCATED",
    "LIMIT_VALUE_LEVEL_LEFTOVERS",
    "observation_for",
    "observation_limits",
    "observation_status",
    "observations",
]
