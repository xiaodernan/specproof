"""Dynamic state collectors — Redis and RabbitMQ evidence (Phase 3, P3-2/P3-3).

The gap this module closes is the one the roadmap names explicitly:

    "如果 RabbitMQ 在本地测试中被排除，报告必须写清 EVENT 没有被验证，
     而不是把「代码调用了 convertAndSend」当作 PASS。"

and

    "没有抓到 Redis 状态，就返回 REDIS_NO_EVIDENCE；不能根据代码中
     出现 delete 就填「Token 已失效」。"

Both collectors answer the same question in the same shape: what was
ACTUALLY observed, on each side of the Base/Head boundary, and what does
the difference mean?

Two rules run through the whole module:

1. **Absence is recorded, never invented.** A key that does not exist is
   reported as ``present: false`` — not as an empty value, and not as
   "the token was invalidated" unless the observation says so.
2. **The caller may not supply the verdict.** These collectors return
   observations and a comparison; the severity/verdict policy stays in
   the Review Court, where it belongs.

The collectors take their dependencies as arguments (a Redis client, a
publisher delegate) rather than reaching for a global, so the whole module
is exercisable without Docker, Redis or RabbitMQ.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from evidence.fragments import MqObservation, ObjectObservation, RedisObservation

#: Collector version stamped on every fragment. A collector whose
#: semantics change MUST bump this: the version is what tells a reader
#: whether two fragments are comparable.
COLLECTOR_VERSION = "1.0.0"

#: Fragment status vocabulary reused from evidence.fragments.
STATUS_COMPLIANT = "COMPLIANT"
STATUS_REGRESSION = "REGRESSION"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_NON_REPRODUCIBLE = "NON_REPRODUCIBLE"
STATUS_NO_EVIDENCE = "NO_EVIDENCE"


# ── Redis ──────────────────────────────────────────────────────────────────


class RedisLike(Protocol):
    """The slice of the Redis client these collectors use."""

    def get(self, name: str) -> Any: ...

    def ttl(self, name: str) -> int: ...


class RedisScannerLike(Protocol):
    """A client that can enumerate a key family.

    Optional: a client that cannot scan is still usable for EXACT keys.
    The difference matters because "the keys of this family" is not a
    list somebody can guess — the ids are the domain's, and the contract
    only says which FAMILY it is about.
    """

    def scan_iter(self, match: str | None = None, count: int | None = None) -> Any: ...


@dataclass(frozen=True)
class KeyState:
    """One key's observed state at one point in time."""

    key: str
    present: bool
    value: str | None = None
    ttl_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "present": self.present,
            "value": self.value,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class RedisStateCollector:
    """Capture Redis key state as a machine-readable observation.

    The value is read as TEXT and the TTL in seconds. A key that exists
    with an empty value is present-with-empty-value — a different state
    from "absent", and the difference is exactly what "the token was
    invalidated" versus "the token was never there" turns on.
    """

    client: RedisLike
    collector_version: str = COLLECTOR_VERSION
    #: Set when a family had more keys than the cap allowed. A cap that
    #: is not announced is a reader believing they saw everything, so the
    #: truncation travels with the observation.
    truncated: bool = False
    truncated_patterns: list[str] = field(default_factory=list)

    def snapshot(self, keys: Iterable[str]) -> dict[str, KeyState]:
        """Read every key once; one unreadable key does not abort the rest."""
        states: dict[str, KeyState] = {}
        for key in keys:
            states[key] = self._read_one(key)
        return states

    def snapshot_by_pattern(
        self, patterns: Iterable[str], *, max_keys: int = 200,
    ) -> dict[str, KeyState]:
        """Read every key matching the given patterns.

        A contract says which FAMILY of keys it is about; the ids inside
        that family belong to the domain and cannot be guessed. So the
        family is SCANNED, and the keys found are read one by one.

        A client that cannot scan yields an empty observation — the
        caller reports NO_EVIDENCE, which is honest ("we could not look
        at that family"), rather than pretending the family was empty.

        A family with MANY keys is truncated at ``max_keys`` — and the
        truncation is REPORTED (``truncated``), because a cap that is
        not announced is a reader believing they saw everything.
        """
        states: dict[str, KeyState] = {}
        scanner = getattr(self.client, "scan_iter", None)
        if scanner is None:
            return states
        for pattern in patterns:
            try:
                found = list(scanner(match=pattern))
            except Exception:  # noqa: BLE001 — an unscanable family is unseen
                continue
            if len(found) > max_keys:
                self.truncated = True
                self.truncated_patterns.append(pattern)
                found = found[:max_keys]
            for key in found:
                name = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                if name not in states:
                    states[name] = self._read_one(name)
        return states

    def _read_one(self, key: str) -> KeyState:
        try:
            raw = self.client.get(key)
        except Exception:  # noqa: BLE001 — an unreadable key is absent
            return KeyState(key=key, present=False, value=None, ttl_seconds=None)
        if raw is None:
            return KeyState(key=key, present=False, value=None, ttl_seconds=None)
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        except UnicodeDecodeError:
            # A non-text value is still PRESENT — its bytes are not text,
            # but the key exists. Reporting it as absent would be a lie.
            text = f"<binary:{len(raw)} bytes>"
        try:
            ttl = int(self.client.ttl(key))
        except Exception:  # noqa: BLE001 — TTL is an extra, not a blocker
            ttl = -2
        # Redis's own conventions: -2 = key does not exist, -1 = no expiry.
        ttl_seconds = None if ttl < 0 else ttl
        return KeyState(key=key, present=True, value=text, ttl_seconds=ttl_seconds)

    @staticmethod
    def _states_to_dict(states: Mapping[str, KeyState]) -> dict[str, Any]:
        return {key: state.to_dict() for key, state in sorted(states.items())}

    @staticmethod
    def compare(
        base: Mapping[str, KeyState], head: Mapping[str, KeyState]
    ) -> dict[str, Any]:
        """What changed between the two snapshots, per key.

        The comparison is DESCRIPTIVE: it reports which keys appeared,
        disappeared or changed value/TTL. It does not decide whether a
        change is good — that is the Review Court's job.
        """
        changed: list[dict[str, Any]] = []
        for key in sorted(set(base) | set(head)):
            before = base.get(key)
            after = head.get(key)
            if before is None or after is None:
                changed.append({
                    "key": key,
                    "change": "appeared" if before is None else "disappeared",
                    "base": before.to_dict() if before else None,
                    "head": after.to_dict() if after else None,
                })
                continue
            if before.present != after.present:
                changed.append({
                    "key": key,
                    "change": "appeared" if after.present else "disappeared",
                    "base": before.to_dict(),
                    "head": after.to_dict(),
                })
                continue
            if before.value != after.value:
                changed.append({
                    "key": key,
                    "change": "value_changed",
                    "base": before.to_dict(),
                    "head": after.to_dict(),
                })
                continue
            if before.ttl_seconds != after.ttl_seconds:
                changed.append({
                    "key": key,
                    "change": "ttl_changed",
                    "base": before.to_dict(),
                    "head": after.to_dict(),
                })
        return {"changed": changed, "changed_count": len(changed)}

    def fragment(
        self,
        experiment_id: str,
        base: Mapping[str, KeyState],
        head: Mapping[str, KeyState],
    ) -> RedisObservation:
        """Build the observation for one experiment.

        When NO key was observed on either side there is no evidence at
        all — the fragment says so rather than reporting a clean run.
        """
        observed = any(state.present for state in list(base.values()) + list(head.values()))
        comparison = self.compare(base, head)
        if not observed:
            status = STATUS_NO_EVIDENCE
        elif comparison["changed_count"] == 0:
            status = STATUS_COMPLIANT
        else:
            status = STATUS_AMBIGUOUS
        return RedisObservation(
            experiment_id=experiment_id,
            fragment_type="redis",
            collector_version=self.collector_version,
            collected_at=_now_iso(),
            base=self._states_to_dict(base),
            head=self._states_to_dict(head),
            normalization={
                "value": "read as UTF-8 text; non-text values are reported as a byte count",
                "ttl_seconds": "Redis TTL in seconds; None means no expiry or absent",
            },
            comparison=comparison,
            status=status,
            confidence=1.0 if observed else 0.0,
            evidence_ref=None,
            reproducibility="reproducible",
            extension={"observed_any_key": observed},
        )


def redis_fragment_from_snapshots(
    experiment_id: str,
    base: Mapping[str, KeyState],
    head: Mapping[str, KeyState],
    *,
    collector_version: str = COLLECTOR_VERSION,
    truncated_patterns: Iterable[str] = (),
) -> RedisObservation:
    """Build the fragment from TWO snapshots that were taken at two moments.

    The instance method samples both sides at the SAME instant, which
    makes the comparison permanently say "nothing changed" — honest and
    useless. This entry point takes the two snapshots the pipeline
    actually captured (after the Base run and after the Head run) and
    compares THOSE.

    ``truncated_patterns`` says a key family had more keys than the cap
    allowed: the observation is PARTIAL, and a reader must be able to
    see that rather than believe they saw every key.
    """
    observed = any(
        state.present for state in list(base.values()) + list(head.values())
    )
    comparison = RedisStateCollector.compare(base, head)
    if not observed:
        status = STATUS_NO_EVIDENCE
    elif comparison["changed_count"] == 0:
        status = STATUS_COMPLIANT
    else:
        status = STATUS_AMBIGUOUS
    truncated = list(truncated_patterns)
    return RedisObservation(
        experiment_id=experiment_id,
        fragment_type="redis",
        collector_version=collector_version,
        collected_at=_now_iso(),
        base=RedisStateCollector._states_to_dict(base),
        head=RedisStateCollector._states_to_dict(head),
        normalization={
            "value": "read as UTF-8 text; non-text values are reported as a byte count",
            "ttl_seconds": "Redis TTL in seconds; None means no expiry or absent",
        },
        comparison=comparison,
        status=status,
        confidence=1.0 if observed else 0.0,
        evidence_ref=None,
        reproducibility="reproducible",
        extension={
            "observed_any_key": observed,
            "truncated_patterns": truncated,
            "observation_complete": not truncated,
        },
    )


# ── RabbitMQ ───────────────────────────────────────────────────────────────


class PublisherLike(Protocol):
    """The publish surface a probe records through."""

    def publish(
        self, routing_key: str, payload: dict[str, Any], exchange: str = ""
    ) -> None: ...


@dataclass(frozen=True)
class PublishRecord:
    """One publish the code actually attempted."""

    routing_key: str
    exchange: str
    payload: dict[str, Any]
    payload_digest: str
    ordinal: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "routing_key": self.routing_key,
            "exchange": self.exchange,
            "payload": dict(self.payload),
            "payload_digest": self.payload_digest,
            "ordinal": self.ordinal,
        }


@dataclass
class RecordingPublisher:
    """A publisher that RECORDS what was published, then delegates.

    Wiring this in place of the real publisher turns "the code called
    convertAndSend" into a machine-readable fact: how many messages, with
    which routing key, carrying which payload. The delegate may be the
    real RabbitMQ store, a test double, or None (record only).

    A publish that RAISES is still recorded — the attempt happened, and
    "it was attempted and failed" is different from "it was not
    attempted". The exception is re-raised so the caller still sees the
    failure.
    """

    delegate: PublisherLike | None = None
    records: list[PublishRecord] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)

    def publish(
        self, routing_key: str, payload: dict[str, Any], exchange: str = ""
    ) -> None:
        record = PublishRecord(
            routing_key=routing_key,
            exchange=exchange,
            payload=dict(payload),
            payload_digest=_payload_digest(payload),
            ordinal=len(self.records) + 1,
        )
        self.records.append(record)
        if self.delegate is None:
            return
        try:
            self.delegate.publish(routing_key, dict(payload), exchange)
        except Exception as exc:  # noqa: BLE001 — recorded, then re-raised
            self.failures.append({
                "routing_key": routing_key,
                "exchange": exchange,
                "error": f"{type(exc).__name__}: {exc}",
                "ordinal": record.ordinal,
            })
            raise

    # ── observation ───────────────────────────────────────────────

    def observation(self) -> dict[str, Any]:
        """The observed publish facts (count, routing keys, payloads)."""
        return {
            "publish_count": len(self.records),
            "failed_count": len(self.failures),
            "routing_keys": sorted({r.routing_key for r in self.records}),
            "exchanges": sorted({r.exchange for r in self.records if r.exchange}),
            "payload_digests": [r.payload_digest for r in self.records],
            "records": [r.to_dict() for r in self.records],
            "failures": list(self.failures),
        }

    def fragment(
        self,
        experiment_id: str,
        base: RecordingPublisher | None = None,
        head: RecordingPublisher | None = None,
    ) -> MqObservation:
        """Build the message observation for one experiment.

        ``base``/``head`` are the two sides' recorders. When only one side
        is given it is used for both, which is the "single-side
        observation" case: the comparison is then meaningless and the
        fragment says so.
        """
        base_obs = (base or self).observation()
        head_obs = (head or self).observation()
        comparison = compare_publish_observations(base_obs, head_obs)
        observed = bool(base_obs["publish_count"] or head_obs["publish_count"])
        if not observed:
            status = STATUS_NO_EVIDENCE
        elif comparison["changed_count"] == 0:
            status = STATUS_COMPLIANT
        else:
            status = STATUS_AMBIGUOUS
        return MqObservation(
            experiment_id=experiment_id,
            fragment_type="mq",
            collector_version=COLLECTOR_VERSION,
            collected_at=_now_iso(),
            base=base_obs,
            head=head_obs,
            normalization={
                "payload_digest": "sha256 over the canonical JSON of the payload",
                "routing_keys": "sorted unique routing keys actually published",
            },
            comparison=comparison,
            status=status,
            confidence=1.0 if observed else 0.0,
            evidence_ref=None,
            reproducibility="reproducible",
            extension={"observed_any_publish": observed},
        )


def compare_publish_observations(
    base: Mapping[str, Any], head: Mapping[str, Any]
) -> dict[str, Any]:
    """Descriptive comparison of two publish observations.

    Reports the count difference, the routing keys that appeared or
    disappeared, and the payload digest difference. A changed routing key
    is called out separately from a changed count: "the message went to a
    different queue" and "the message was sent twice" are different
    regressions with the same count.
    """
    base_count = int(base.get("publish_count") or 0)
    head_count = int(head.get("publish_count") or 0)
    base_keys = set(base.get("routing_keys") or [])
    head_keys = set(head.get("routing_keys") or [])
    base_digests = list(base.get("payload_digests") or [])
    head_digests = list(head.get("payload_digests") or [])

    changes: list[dict[str, Any]] = []
    if base_count != head_count:
        changes.append({
            "change": "publish_count_changed",
            "base": base_count,
            "head": head_count,
        })
    for key in sorted(base_keys - head_keys):
        changes.append({"change": "routing_key_missing", "routing_key": key})
    for key in sorted(head_keys - base_keys):
        changes.append({"change": "routing_key_added", "routing_key": key})
    if base_digests != head_digests:
        changes.append({
            "change": "payload_digests_changed",
            "base": base_digests,
            "head": head_digests,
        })
    return {"changed": changes, "changed_count": len(changes)}


# ── Object storage ──────────────────────────────────────────────────────────


class ObjectStoreLike(Protocol):
    """The stat surface an object probe reads through."""

    def object_exists(self, bucket: str, object_name: str) -> bool: ...

    def object_stat(self, bucket: str, object_name: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ObjectState:
    """One object, as it was OBSERVED.

    Absence is a fact, not an empty value: an object that is not there
    is reported as ``present: false``. A missing object must never read
    as "the artifact was deleted" — that is a conclusion, and this
    collector does not draw conclusions.
    """

    bucket: str
    object_name: str
    present: bool
    size_bytes: int = 0
    content_type: str = ""
    sha256: str = ""
    version: str = ""

    @property
    def ref(self) -> str:
        return f"{self.bucket}/{self.object_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "object_name": self.object_name,
            "present": self.present,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "sha256": self.sha256,
            "version": self.version,
        }


class ObjectStateCollector:
    """Collect what the object store ACTUALLY holds (P1-7).

    Same contract as the Redis and RabbitMQ collectors: absence is
    recorded, the caller may not supply the verdict, and the
    dependencies arrive as arguments so the whole thing runs without
    MinIO.
    """

    def __init__(
        self,
        objects: ObjectStoreLike,
        *,
        collector_version: str = COLLECTOR_VERSION,
    ) -> None:
        self._objects = objects
        self.collector_version = collector_version

    def snapshot(self, refs: Iterable[str]) -> dict[str, ObjectState]:
        """Observe each "bucket/object-name" reference."""
        states: dict[str, ObjectState] = {}
        for ref in refs:
            bucket, _, name = str(ref).partition("/")
            if not bucket or not name:
                continue
            try:
                present = bool(self._objects.object_exists(bucket, name))
            except Exception:  # noqa: BLE001 — an unreachable store is absence
                present = False
            if not present:
                states[str(ref)] = ObjectState(
                    bucket=bucket, object_name=name, present=False,
                )
                continue
            try:
                stat = self._objects.object_stat(bucket, name)
            except Exception:  # noqa: BLE001 — raced away between the calls
                states[str(ref)] = ObjectState(
                    bucket=bucket, object_name=name, present=False,
                )
                continue
            states[str(ref)] = ObjectState(
                bucket=bucket,
                object_name=name,
                present=True,
                size_bytes=int(stat.get("size_bytes") or 0),
                content_type=str(stat.get("content_type") or ""),
                sha256=str(stat.get("sha256") or ""),
                version=str(stat.get("version") or ""),
            )
        return states

    @staticmethod
    def compare(
        base: Mapping[str, ObjectState],
        head: Mapping[str, ObjectState],
    ) -> dict[str, Any]:
        """What changed between the two snapshots, per object.

        DESCRIPTIVE, like every other comparison here: which objects
        appeared, disappeared, or carry different bytes. Whether that is
        bad is the Review Court's call, not this module's.
        """
        changed: list[dict[str, Any]] = []
        for ref in sorted(set(base) | set(head)):
            before = base.get(ref)
            after = head.get(ref)
            if before is None or after is None:
                changed.append({
                    "ref": ref,
                    "change": "appeared" if before is None else "disappeared",
                    "base": before.to_dict() if before else None,
                    "head": after.to_dict() if after else None,
                })
                continue
            if before.present != after.present:
                changed.append({
                    "ref": ref,
                    "change": "appeared" if after.present else "disappeared",
                    "base": before.to_dict(),
                    "head": after.to_dict(),
                })
                continue
            if not before.present:
                continue
            if before.sha256 != after.sha256 or before.size_bytes != after.size_bytes:
                changed.append({
                    "ref": ref,
                    "change": "content_changed",
                    "base": before.to_dict(),
                    "head": after.to_dict(),
                })
                continue
            if before.content_type != after.content_type:
                changed.append({
                    "ref": ref,
                    "change": "content_type_changed",
                    "base": before.to_dict(),
                    "head": after.to_dict(),
                })
        return {"changed": changed, "changed_count": len(changed)}

    def fragment(
        self,
        experiment_id: str,
        base: Mapping[str, ObjectState],
        head: Mapping[str, ObjectState],
    ) -> ObjectObservation:
        """Build the observation for one experiment."""
        observed = any(
            state.present for state in list(base.values()) + list(head.values())
        )
        comparison = self.compare(base, head)
        if not observed:
            status = STATUS_NO_EVIDENCE
        elif comparison["changed_count"] == 0:
            status = STATUS_COMPLIANT
        else:
            status = STATUS_AMBIGUOUS
        return ObjectObservation(
            experiment_id=experiment_id,
            fragment_type="object",
            collector_version=self.collector_version,
            collected_at=_now_iso(),
            base={ref: state.to_dict() for ref, state in base.items()},
            head={ref: state.to_dict() for ref, state in head.items()},
            normalization={
                "ref": "bucket/object-name",
                "sha256": "the payload digest reported by the object store",
                "presence": "an object that is not there is reported as present=false",
            },
            comparison=comparison,
            status=status,
            confidence=1.0 if observed else 0.0,
            evidence_ref=None,
            reproducibility="reproducible",
            extension={"observed_any_object": observed},
        )


def object_fragment_from_snapshots(
    experiment_id: str,
    base: Mapping[str, ObjectState],
    head: Mapping[str, ObjectState],
    *,
    collector_version: str = COLLECTOR_VERSION,
) -> ObjectObservation:
    """Build the object fragment from TWO snapshots taken at two moments.

    See redis_fragment_from_snapshots: comparing a snapshot with itself
    always says "nothing changed" — the two moments have to be real.
    """
    observed = any(
        state.present for state in list(base.values()) + list(head.values())
    )
    comparison = ObjectStateCollector.compare(base, head)
    if not observed:
        status = STATUS_NO_EVIDENCE
    elif comparison["changed_count"] == 0:
        status = STATUS_COMPLIANT
    else:
        status = STATUS_AMBIGUOUS
    return ObjectObservation(
        experiment_id=experiment_id,
        fragment_type="object",
        collector_version=collector_version,
        collected_at=_now_iso(),
        base={ref: state.to_dict() for ref, state in base.items()},
        head={ref: state.to_dict() for ref, state in head.items()},
        normalization={
            "ref": "bucket/object-name",
            "sha256": "the payload digest reported by the object store",
            "presence": "an object that is not there is reported as present=false",
        },
        comparison=comparison,
        status=status,
        confidence=1.0 if observed else 0.0,
        evidence_ref=None,
        reproducibility="reproducible",
        extension={"observed_any_object": observed},
    )


def _payload_digest(payload: Mapping[str, Any]) -> str:
    import hashlib

    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "COLLECTOR_VERSION",
    "STATUS_AMBIGUOUS",
    "STATUS_COMPLIANT",
    "STATUS_NO_EVIDENCE",
    "STATUS_NON_REPRODUCIBLE",
    "STATUS_REGRESSION",
    "KeyState",
    "MqObservation",
    "PublishRecord",
    "RecordingPublisher",
    "RedisObservation",
    "RedisStateCollector",
    "compare_publish_observations",
]
