"""Contract Lineage — 契约血缘证据链 (GRAND PLAN V2 §18.1).

Links every pipeline artifact into a hash chain from the requirement to the
certificate, so that each number in a Merge Certificate can be traced back to
the original experiment products. This is the "why did this verify" causal
chain, made cryptographic.

Design (§18.1):

- Node kinds: requirement / contract_version / checker / experiment /
  artifact / capsule / finding / certificate.  Every node carries
  {id, kind, digest, meta}; the digest is the artifact's existing
  sha256/registry digest when one was recorded, otherwise the sha256 of the
  artifact's canonical JSON (computed digests are marked in meta).
- Edge kinds: produced_by (source was produced by target) / verifies
  (source verifies target) / derived_from (source derived from target).
- Edge hash = sha256 over the deterministic JSON array
  [source_id, source_digest, target_id, target_digest, edge_type, timestamp]
  — the unambiguous serialization of the design's
  sha256(node_a.id + digest + node_b.id + digest + edge_type + timestamp).
- Root hash = sha256 over the sorted, newline-joined leaf list in which each
  node contributes "node:<id>:<kind>:<digest>" and each edge contributes its
  hash. Sorting plus a fixed field order make the root reproducible regardless
  of insertion order; including node leaves means tampering with ANY node
  digest is detectable even when no edge references that node.
- Missing product classes are omitted honestly: build_lineage never invents a
  node or an edge for data the context does not carry. A verify against the
  stored root therefore replays deterministically from the same context.

Replay model: the certificate records the root hash (extension.lineage_root).
Re-running build_lineage over the stored products must reproduce it; any
tampered capsule/report/artifact changes its digest, changes its edge hash,
and breaks the root.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

LINEAGE_SCHEMA_VERSION = 1

NODE_KINDS = frozenset({
    "requirement",
    "contract_version",
    "checker",
    "experiment",
    "artifact",
    "capsule",
    "finding",
    "certificate",
})

EDGE_TYPES = frozenset({"produced_by", "verifies", "derived_from"})

# Root of an empty lineage: sha256 of the empty leaf list.
EMPTY_ROOT_HASH = hashlib.sha256(b"").hexdigest()

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SHORT_DIGEST_RE = re.compile(r"^[0-9a-f]{16}$")

# Stable fields of a contract_version node's content digest.
_CONTRACT_FIELDS = ("id", "checker_type", "requirement", "expected_behavior")

# Volatile/derived fields excluded from the certificate node's content digest.
_CERTIFICATE_VOLATILE_FIELDS = ("issued_at", "signatures", "extension", "_type")


class LineageError(Exception):
    """Raised when a serialized lineage payload is structurally invalid."""


@dataclass(frozen=True)
class LineageNode:
    """One vertex of the evidence DAG."""

    id: str
    kind: str
    digest: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "digest": self.digest,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class LineageEdge:
    """One directed, hashed edge of the evidence DAG."""

    source: str
    target: str
    type: str
    timestamp: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "timestamp": self.timestamp,
            "hash": self.hash,
        }


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    """Deterministic JSON serialization (sorted keys, no whitespace)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def normalize_digest(value: str) -> str | None:
    """Normalize a recorded digest to lowercase hex (strips "sha256:").

    Accepts 64-hex (sha256) and 16-hex (registry spec digest) values.
    Returns None for anything else, so callers can omit the node honestly.
    """
    stripped = value.strip()
    if stripped.startswith("sha256:"):
        stripped = stripped[len("sha256:"):]
    lowered = stripped.lower()
    if _DIGEST_RE.fullmatch(lowered) or _SHORT_DIGEST_RE.fullmatch(lowered):
        return lowered
    return None


def edge_hash(
    source_id: str,
    source_digest: str,
    target_id: str,
    target_digest: str,
    edge_type: str,
    timestamp: str,
) -> str:
    """Design §18.1 edge hash: sha256(a.id+digest, b.id+digest, type, ts)."""
    payload = _canonical_json(
        [source_id, source_digest, target_id, target_digest, edge_type, timestamp]
    )
    return _sha256_hex(payload)


def _item_digest(
    item: Mapping[str, Any], prefer: tuple[str, ...] = ("evidence_digest",)
) -> str:
    """Recorded digest when present, else sha256 of the item's canonical JSON."""
    for key in prefer:
        recorded = item.get(key)
        if isinstance(recorded, str) and recorded.strip():
            return recorded
    try:
        return _sha256_hex(_canonical_json(dict(item)))
    except (TypeError, ValueError):
        return ""


def _contract_digest(contract: Mapping[str, Any]) -> str:
    recorded = contract.get("contract_digest") or contract.get("spec_digest")
    if isinstance(recorded, str) and recorded.strip():
        return recorded
    stable = {
        key: contract[key]
        for key in _CONTRACT_FIELDS
        if key in contract and contract[key] is not None
    }
    if not stable:
        return ""
    try:
        return _sha256_hex(_canonical_json(stable))
    except (TypeError, ValueError):
        return ""


def _certificate_digest(certificate: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in certificate.items()
        if key not in _CERTIFICATE_VOLATILE_FIELDS
    }
    try:
        return _sha256_hex(_canonical_json(stable))
    except (TypeError, ValueError):
        return ""


def _capsule_manifest(zip_path: str) -> dict[str, Any] | None:
    """Read manifest.json out of a capsule zip (best effort, never raises)."""
    import zipfile

    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            raw = archive.read("manifest.json")
        manifest = json.loads(raw)
        if isinstance(manifest, dict):
            return manifest
    except Exception:  # noqa: BLE001 — unreadable capsule is omitted honestly
        return None
    return None


def build_lineage(
    context: Mapping[str, Any], built_at: str | None = None
) -> tuple[dict[str, Any], str]:
    """Build the evidence DAG from pipeline products in *context*.

    Products are read from the same keys the Phase0 state carries:
    requirement_text, contracts, static_findings, diff_results,
    contract_results, confirmed_findings, capsules, certificate. A product
    class absent from the context (or lacking a usable digest) omits its
    branch — the DAG never fabricates nodes or edges.

    Args:
        context: pipeline product context (e.g. the Phase0 state dict).
        built_at: edge timestamp (ISO-8601). Defaults to now; inject a fixed
            value for reproducible replay/determinism tests.

    Returns:
        (dag, root_hash) where dag is {"nodes": [...], "edges": [...]}.
    """
    timestamp = built_at if built_at is not None else datetime.now(UTC).isoformat()
    nodes: dict[str, LineageNode] = {}
    edges: list[LineageEdge] = []

    def add_node(
        node_id: str, kind: str, digest: str, meta: dict[str, Any] | None = None
    ) -> bool:
        normalized = normalize_digest(digest) if isinstance(digest, str) else None
        if not node_id or kind not in NODE_KINDS or normalized is None:
            return False
        if node_id in nodes:
            return False
        nodes[node_id] = LineageNode(
            id=node_id, kind=kind, digest=normalized, meta=dict(meta or {})
        )
        return True

    def add_edge(source: str, target: str, edge_type: str) -> None:
        if source == target:
            return
        if source not in nodes or target not in nodes:
            return
        if edge_type not in EDGE_TYPES:
            return
        digest = edge_hash(
            source,
            nodes[source].digest,
            target,
            nodes[target].digest,
            edge_type,
            timestamp,
        )
        edges.append(
            LineageEdge(
                source=source,
                target=target,
                type=edge_type,
                timestamp=timestamp,
                hash=digest,
            )
        )

    # ── requirement ───────────────────────────────────────────────
    requirement_text = str(context.get("requirement_text") or "")
    if requirement_text:
        add_node(
            "requirement",
            "requirement",
            _sha256_hex(requirement_text),
            {"spec_path": str(context.get("spec_path") or "")},
        )

    # ── contract_version ──────────────────────────────────────────
    contracts = context.get("contracts") or []
    for contract in contracts:
        if not isinstance(contract, Mapping):
            continue
        contract_id = str(contract.get("id") or "")
        if not contract_id:
            continue
        node_id = f"contract:{contract_id}"
        digest = _contract_digest(contract)
        recorded = contract.get("contract_digest") or contract.get("spec_digest")
        meta: dict[str, Any] = {
            "checker_type": str(contract.get("checker_type") or ""),
            "approved": bool(contract.get("approved", False)),
            "digest_source": "recorded" if recorded else "computed",
        }
        version = contract.get("version")
        if version is not None:
            meta["version"] = version
        if add_node(node_id, "contract_version", digest, meta):
            add_edge(node_id, "requirement", "produced_by")

    # ── checker (static findings) ─────────────────────────────────
    checker_by_contract: dict[str, str] = {}
    static_findings = context.get("static_findings") or []
    for index, finding in enumerate(static_findings):
        if not isinstance(finding, Mapping):
            continue
        contract_id = str(finding.get("contract_id") or "")
        node_id = f"checker:{contract_id or 'static'}:{index}"
        digest = _item_digest(finding)
        meta = {
            "contract_id": contract_id,
            "evidence_type": str(finding.get("evidence_type") or ""),
            "digest_source": (
                "recorded"
                if str(finding.get("evidence_digest") or "")
                else "computed"
            ),
        }
        if add_node(node_id, "checker", digest, meta):
            checker_by_contract.setdefault(contract_id, node_id)
            add_edge(node_id, f"contract:{contract_id}", "verifies")

    # ── experiment (differential results) ─────────────────────────
    experiment_by_contract: dict[str, str] = {}
    diff_results = context.get("diff_results") or []
    for index, result in enumerate(diff_results):
        if not isinstance(result, Mapping):
            continue
        contract_id = str(result.get("contract_id") or "")
        experiment_id = str(result.get("experiment_id") or "DIFF-01")
        node_id = f"experiment:{experiment_id}:{index}"
        digest = _item_digest(result)
        meta = {
            "contract_id": contract_id,
            "verdict": str(result.get("verdict") or ""),
            "evidence_type": str(result.get("evidence_type") or ""),
            "digest_source": (
                "recorded"
                if str(result.get("evidence_digest") or "")
                else "computed"
            ),
        }
        if add_node(node_id, "experiment", digest, meta):
            experiment_by_contract.setdefault(contract_id, node_id)
            add_edge(node_id, f"contract:{contract_id}", "verifies")

    # ── artifact (per-contract evidence refs) ─────────────────────
    contract_results = context.get("contract_results") or []
    for result in contract_results:
        if not isinstance(result, Mapping):
            continue
        contract_id = str(result.get("contract_id") or "")
        if not contract_id:
            continue
        evidence_ref = str(result.get("evidence_ref") or "")
        node_id = f"artifact:{contract_id}"
        meta = {
            "contract_id": contract_id,
            "result": str(result.get("result") or ""),
            "experiment": str(result.get("experiment") or ""),
        }
        if not add_node(node_id, "artifact", evidence_ref, meta):
            continue
        producer = experiment_by_contract.get(contract_id) or checker_by_contract.get(
            contract_id
        )
        if producer:
            add_edge(node_id, producer, "produced_by")

    # ── finding (confirmed by the Review Court) ───────────────────
    confirmed_findings = context.get("confirmed_findings") or []
    for index, finding in enumerate(confirmed_findings):
        if not isinstance(finding, Mapping):
            continue
        finding_id = str(finding.get("id") or f"F-{index}")
        contract_id = str(finding.get("contract_id") or "")
        node_id = f"finding:{finding_id}"
        digest = _item_digest(finding)
        meta = {
            "contract_id": contract_id,
            "severity": str(finding.get("severity") or ""),
            "evidence_type": str(finding.get("evidence_type") or ""),
            "digest_source": (
                "recorded"
                if str(finding.get("evidence_digest") or "")
                else "computed"
            ),
        }
        if not add_node(node_id, "finding", digest, meta):
            continue
        add_edge(node_id, f"contract:{contract_id}", "verifies")
        source = str(finding.get("source") or "")
        if source == "static_analysis":
            origin = checker_by_contract.get(contract_id)
        else:
            origin = experiment_by_contract.get(contract_id)
        if origin:
            add_edge(node_id, origin, "derived_from")

    # ── capsule (bug capsule manifests) ───────────────────────────
    capsules = context.get("capsules") or []
    for capsule_path in capsules:
        manifest = _capsule_manifest(str(capsule_path))
        if manifest is None:
            continue
        finding_id = str(manifest.get("finding_id") or "")
        manifest_digest = str(manifest.get("manifest_digest") or "")
        node_id = f"capsule:{finding_id}"
        meta = {"path": str(capsule_path)}
        if not add_node(node_id, "capsule", manifest_digest, meta):
            continue
        add_edge(node_id, f"finding:{finding_id}", "produced_by")

    # ── certificate ───────────────────────────────────────────────
    certificate = context.get("certificate")
    if isinstance(certificate, dict) and certificate:
        digest = _certificate_digest(certificate)
        if add_node("certificate", "certificate", digest):
            add_edge("certificate", "requirement", "derived_from")
            for finding_node in (
                node for node in nodes if node.startswith("finding:")
            ):
                add_edge("certificate", finding_node, "derived_from")
            if not any(e.source == "certificate" and e.type == "derived_from" for e in edges):
                for contract_node in (
                    node for node in nodes if node.startswith("contract:")
                ):
                    add_edge("certificate", contract_node, "derived_from")

    dag = {
        "nodes": [
            nodes[key].to_dict() for key in sorted(nodes, key=lambda k: (k,))
        ],
        "edges": [
            edge.to_dict()
            for edge in sorted(
                edges,
                key=lambda e: (e.source, e.target, e.type, e.timestamp, e.hash),
            )
        ],
    }
    return dag, _root_hash(dag)


def _root_hash(dag: Mapping[str, Any]) -> str:
    leaves = []
    for node in dag.get("nodes", []):
        if isinstance(node, Mapping):
            leaves.append(
                f"node:{node.get('id', '')}:{node.get('kind', '')}:"
                f"{node.get('digest', '')}"
            )
    for edge in dag.get("edges", []):
        if isinstance(edge, Mapping):
            leaves.append(str(edge.get("hash", "")))
    return _sha256_hex("\n".join(sorted(leaves)))


def verify_lineage(
    dag: Mapping[str, Any], root_hash: str
) -> tuple[bool, list[dict[str, Any]]]:
    """Recompute every edge hash and the root; report any tampering.

    A node digest changed anywhere shows up as an edge_hash_mismatch on the
    adjacent edges (with the suspect node ids) and, because node leaves feed
    the root, as a root_hash_mismatch when no edge references the node.

    Returns (ok, diffs); diffs is empty when the lineage is intact.
    """
    diffs: list[dict[str, Any]] = []
    raw_nodes = dag.get("nodes")
    raw_edges = dag.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return False, [{
            "kind": "malformed_dag",
            "message": "lineage nodes/edges must be lists",
        }]

    nodes: dict[str, dict[str, str]] = {}
    for node in raw_nodes:
        if not isinstance(node, Mapping):
            diffs.append({"kind": "malformed_node", "message": str(node)})
            continue
        node_id = str(node.get("id", ""))
        kind = str(node.get("kind", ""))
        digest = str(node.get("digest", ""))
        if not node_id or not digest:
            diffs.append({"kind": "invalid_node", "node": node_id})
            continue
        if node_id in nodes:
            diffs.append({"kind": "duplicate_node", "node": node_id})
        if kind not in NODE_KINDS:
            diffs.append({"kind": "unknown_node_kind", "node": node_id, "value": kind})
        nodes[node_id] = {"id": node_id, "kind": kind, "digest": digest}

    for edge in raw_edges:
        if not isinstance(edge, Mapping):
            diffs.append({"kind": "malformed_edge", "message": str(edge)})
            continue
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        edge_type = str(edge.get("type", ""))
        stored_hash = str(edge.get("hash", ""))
        if source not in nodes or target not in nodes:
            diffs.append({
                "kind": "dangling_edge",
                "edge_source": source,
                "edge_target": target,
                "edge_type": edge_type,
            })
            continue
        if edge_type not in EDGE_TYPES:
            diffs.append({
                "kind": "unknown_edge_type",
                "edge_source": source,
                "edge_target": target,
                "edge_type": edge_type,
            })
            continue
        timestamp = str(edge.get("timestamp", ""))
        recomputed = edge_hash(
            source,
            nodes[source]["digest"],
            target,
            nodes[target]["digest"],
            edge_type,
            timestamp,
        )
        if recomputed != stored_hash:
            diffs.append({
                "kind": "edge_hash_mismatch",
                "edge_source": source,
                "edge_target": target,
                "edge_type": edge_type,
                "stored_hash": stored_hash,
                "expected_hash": recomputed,
                "suspect_nodes": [source, target],
            })

    if not diffs:
        computed_root = _root_hash(dag)
        if computed_root != root_hash:
            diffs.append({
                "kind": "root_hash_mismatch",
                "expected_root": root_hash,
                "computed_root": computed_root,
            })
    return (not diffs, diffs)


def serialize_lineage(dag: Mapping[str, Any], root_hash: str) -> dict[str, Any]:
    """Stable-field-order serialization of a lineage (JSON-ready dict)."""
    return {
        "schema_version": LINEAGE_SCHEMA_VERSION,
        "root_hash": root_hash,
        "nodes": dag.get("nodes", []),
        "edges": dag.get("edges", []),
    }


def lineage_to_json(dag: Mapping[str, Any], root_hash: str) -> str:
    """Serialize the lineage to a stable, replay-verifiable JSON document."""
    return json.dumps(serialize_lineage(dag, root_hash), indent=2)


def deserialize_lineage(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Restore (dag, root_hash) from a serialized lineage payload."""
    if payload.get("schema_version") != LINEAGE_SCHEMA_VERSION:
        raise LineageError(
            f"unsupported lineage schema_version: {payload.get('schema_version')}"
        )
    root_hash = str(payload.get("root_hash", ""))
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise LineageError("lineage payload must contain node/edge lists")
    return ({"nodes": nodes, "edges": edges}, root_hash)


__all__ = [
    "LineageError",
    "LineageNode",
    "LineageEdge",
    "NODE_KINDS",
    "EDGE_TYPES",
    "EMPTY_ROOT_HASH",
    "LINEAGE_SCHEMA_VERSION",
    "normalize_digest",
    "edge_hash",
    "build_lineage",
    "verify_lineage",
    "serialize_lineage",
    "lineage_to_json",
    "deserialize_lineage",
]
