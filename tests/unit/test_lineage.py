"""§18.1 unit tests — 契约血缘证据链 (Contract Lineage evidence chain).

Covers: DAG build + verify roundtrip, tamper detection with precise location,
honest omission of missing product branches, root-hash determinism, capsule
replay tamper detection, stable serialization, certificate extension
backward-compatibility, signing compatibility, and the publish_report node
wiring.
"""

import hashlib
import json
import zipfile

import pytest

from agent.nodes.publish_report import publish_report_node
from evidence.certificate import (
    MergeCertificate,
    RejectionNotice,
    build_rejection_notice,
    issue_certificate,
)
from evidence.lineage import (
    EMPTY_ROOT_HASH,
    LineageError,
    build_lineage,
    deserialize_lineage,
    edge_hash,
    lineage_to_json,
    serialize_lineage,
    verify_lineage,
)

FIXED_TS = "2026-08-18T00:00:00+00:00"
REQUIREMENT_TEXT = "Only authenticated users may change the account email."


def make_context() -> dict:
    """A realistic pipeline product context (digests as recorded in state)."""
    return {
        "requirement_text": REQUIREMENT_TEXT,
        "contracts": [
            {
                "id": "AUTH-01",
                "checker_type": "http",
                "requirement": "auth required",
                "expected_behavior": "401 without token",
                "approved": True,
            },
            {
                "id": "UNIQUE-01",
                "checker_type": "sql",
                "requirement": "unique email",
                "expected_behavior": "duplicate rejected",
                "approved": True,
            },
        ],
        "static_findings": [
            {
                "contract_id": "AUTH-01",
                "type": "static",
                "description": "annotation dropped",
                "evidence_type": "static_analysis",
                "severity": "MAJOR",
                "confidence": 0.8,
                "location": "SecurityConfig.java",
            },
        ],
        "diff_results": [
            {
                "contract_id": "AUTH-01",
                "experiment_id": "DIFF-01",
                "verdict": "COMPLIANT",
                "evidence_type": "differential_execution",
                "evidence_digest": "sha256:" + "1" * 64,
                "detail": "passes in both Base and Head",
            },
        ],
        "contract_results": [
            {
                "contract_id": "AUTH-01",
                "result": "PASS",
                "experiment": "generated_test_differential",
                "evidence_ref": "sha256:" + "2" * 64,
            },
        ],
        "confirmed_findings": [
            {
                "id": "F-1",
                "contract_id": "AUTH-01",
                "severity": "MAJOR",
                "confidence": 0.9,
                "evidence_type": "differential_execution",
                "evidence_digest": "sha256:" + "3" * 64,
                "source": "differential",
                "description": "regression",
            },
        ],
        "capsules": [],
        "certificate": None,
    }


def flip_first_hex(text: str) -> str:
    first = text[0]
    return ("a" if first != "a" else "b") + text[1:]


def edge_of(dag: dict, source: str, target: str) -> dict | None:
    for edge in dag["edges"]:
        if edge["source"] == source and edge["target"] == target:
            return edge
    return None


def node_of(dag: dict, node_id: str) -> dict | None:
    for node in dag["nodes"]:
        if node["id"] == node_id:
            return node
    return None


def write_capsule(tmp_path, name: str, finding_id: str, severity: str = "MAJOR") -> str:
    """Write a capsule zip whose manifest_digest follows create_capsule's rule."""
    manifest = {
        "finding_id": finding_id,
        "severity": severity,
        "contract_id": "AUTH-01",
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    manifest["manifest_digest"] = f"sha256:{digest}"
    zip_path = tmp_path / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    return str(zip_path)


# ── build + verify ──────────────────────────────────────────────────


def test_build_and_verify_roundtrip():
    dag, root = build_lineage(make_context(), built_at=FIXED_TS)
    # requirement + 2 contracts + checker + experiment + artifact + finding
    assert len(dag["nodes"]) == 7
    assert len(dag["edges"]) == 7
    kinds = {node["kind"] for node in dag["nodes"]}
    assert kinds == {
        "requirement",
        "contract_version",
        "checker",
        "experiment",
        "artifact",
        "finding",
    }
    ok, diffs = verify_lineage(dag, root)
    assert ok
    assert diffs == []


def test_edge_hashes_match_design_formula():
    dag, _root = build_lineage(make_context(), built_at=FIXED_TS)
    nodes = {node["id"]: node for node in dag["nodes"]}
    for edge in dag["edges"]:
        expected = edge_hash(
            edge["source"],
            nodes[edge["source"]]["digest"],
            edge["target"],
            nodes[edge["target"]]["digest"],
            edge["type"],
            FIXED_TS,
        )
        assert edge["hash"] == expected
        assert edge["timestamp"] == FIXED_TS


# ── tamper detection ────────────────────────────────────────────────


def test_tamper_artifact_digest_detected_and_located():
    dag, root = build_lineage(make_context(), built_at=FIXED_TS)
    payload = json.loads(lineage_to_json(dag, root))
    artifact = next(n for n in payload["nodes"] if n["kind"] == "artifact")
    artifact["digest"] = flip_first_hex(artifact["digest"])
    tampered = {"nodes": payload["nodes"], "edges": payload["edges"]}
    ok, diffs = verify_lineage(tampered, root)
    assert not ok
    mismatch = [d for d in diffs if d.get("kind") == "edge_hash_mismatch"]
    assert mismatch
    assert any(
        artifact["id"] in diff.get("suspect_nodes", []) for diff in mismatch
    )


def test_tamper_isolated_node_digest_detected_via_root():
    # A node no edge references is still covered because node leaves feed
    # the root hash.
    ctx = {"requirement_text": REQUIREMENT_TEXT}
    dag, root = build_lineage(ctx, built_at=FIXED_TS)
    payload = json.loads(lineage_to_json(dag, root))
    payload["nodes"][0]["digest"] = flip_first_hex(payload["nodes"][0]["digest"])
    ok, diffs = verify_lineage(
        {"nodes": payload["nodes"], "edges": payload["edges"]}, root
    )
    assert not ok
    assert any(d.get("kind") == "root_hash_mismatch" for d in diffs)


def test_tamper_edge_hash_detected():
    dag, root = build_lineage(make_context(), built_at=FIXED_TS)
    payload = json.loads(lineage_to_json(dag, root))
    target = payload["edges"][0]
    target["hash"] = flip_first_hex(target["hash"])
    ok, diffs = verify_lineage(
        {"nodes": payload["nodes"], "edges": payload["edges"]}, root
    )
    assert not ok
    assert any(
        d.get("kind") == "edge_hash_mismatch"
        and d.get("edge_source") == target["source"]
        and d.get("edge_target") == target["target"]
        for d in diffs
    )


def test_tamper_root_hash_detected():
    dag, root = build_lineage(make_context(), built_at=FIXED_TS)
    ok, diffs = verify_lineage(dag, "0" * 64)
    assert not ok
    assert any(d.get("kind") == "root_hash_mismatch" for d in diffs)


def test_capsule_replay_detects_tampered_manifest(tmp_path):
    # §18.1 acceptance: tampering a capsule changes its manifest digest,
    # which changes the replayed root hash.
    ctx = make_context()
    ctx["capsules"] = [write_capsule(tmp_path, "capsule-a", "F-1", "MAJOR")]
    dag, root = build_lineage(ctx, built_at=FIXED_TS)
    capsule_node = node_of(dag, "capsule:F-1")
    assert capsule_node is not None
    assert capsule_node["kind"] == "capsule"
    assert edge_of(dag, "capsule:F-1", "finding:F-1") is not None
    ok, diffs = verify_lineage(dag, root)
    assert ok and diffs == []

    tampered_ctx = make_context()
    tampered_ctx["capsules"] = [
        write_capsule(tmp_path, "capsule-b", "F-1", "BLOCKER")
    ]
    _dag2, root2 = build_lineage(tampered_ctx, built_at=FIXED_TS)
    assert root2 != root


# ── honest omission + determinism ───────────────────────────────────


def test_missing_product_branches_honestly_omitted():
    dag, root = build_lineage(
        {"requirement_text": REQUIREMENT_TEXT}, built_at=FIXED_TS
    )
    assert [n["id"] for n in dag["nodes"]] == ["requirement"]
    assert dag["edges"] == []
    assert verify_lineage(dag, root)[0]

    dag2, root2 = build_lineage(
        {
            "requirement_text": REQUIREMENT_TEXT,
            "contracts": make_context()["contracts"],
        },
        built_at=FIXED_TS,
    )
    kinds = {node["kind"] for node in dag2["nodes"]}
    assert kinds == {"requirement", "contract_version"}
    assert all(
        edge["type"] == "produced_by" for edge in dag2["edges"]
    )
    assert verify_lineage(dag2, root2)[0]


def test_empty_context_builds_empty_lineage():
    dag, root = build_lineage({}, built_at=FIXED_TS)
    assert dag == {"nodes": [], "edges": []}
    assert root == EMPTY_ROOT_HASH == hashlib.sha256(b"").hexdigest()
    assert verify_lineage(dag, root)[0]


def test_root_hash_deterministic_for_same_input():
    dag1, root1 = build_lineage(make_context(), built_at=FIXED_TS)
    dag2, root2 = build_lineage(make_context(), built_at=FIXED_TS)
    assert root1 == root2
    assert dag1 == dag2
    assert lineage_to_json(dag1, root1) == lineage_to_json(dag2, root2)


def test_root_hash_changes_with_timestamp():
    _dag1, root1 = build_lineage(make_context(), built_at=FIXED_TS)
    _dag2, root2 = build_lineage(
        make_context(), built_at="2026-08-18T00:00:01+00:00"
    )
    assert root1 != root2


# ── serialization ───────────────────────────────────────────────────


def test_serialize_roundtrip_and_stable_field_order():
    dag, root = build_lineage(make_context(), built_at=FIXED_TS)
    payload = json.loads(lineage_to_json(dag, root))
    assert list(payload.keys()) == ["schema_version", "root_hash", "nodes", "edges"]
    assert payload["schema_version"] == 1
    assert payload["root_hash"] == root
    for node in payload["nodes"]:
        assert list(node.keys()) == ["id", "kind", "digest", "meta"]
    for edge in payload["edges"]:
        assert list(edge.keys()) == ["source", "target", "type", "timestamp", "hash"]

    dag2, root2 = deserialize_lineage(payload)
    assert root2 == root
    assert dag2 == dag
    ok, diffs = verify_lineage(dag2, root2)
    assert ok and diffs == []


def test_deserialize_rejects_unknown_schema():
    with pytest.raises(LineageError):
        deserialize_lineage({"schema_version": 2, "root_hash": "0" * 64})


# ── certificate extension (backward compatible) ─────────────────────


def _merge_certificate(**extra):
    return MergeCertificate(
        repository="repo",
        commit_sha="abc123",
        requirements_digest="sha256:" + "a" * 64,
        verified_contracts=1,
        evidence_digests=["sha256:" + "b" * 64],
        toolchain={"python": "3.12"},
        **extra,
    )


def test_certificate_without_extension_stays_backward_compatible():
    document = _merge_certificate().to_dict()
    assert "extension" not in document
    assert document["result"] == "VERIFIED"
    assert json.loads(_merge_certificate().to_json())["version"] == "0.1.0"


def test_certificate_with_extension_serializes():
    extension = {
        "lineage_root": "c" * 64,
        "lineage_nodes": 7,
        "lineage_edges": 7,
    }
    document = _merge_certificate(extension=extension).to_dict()
    assert document["extension"] == extension
    assert json.loads(_merge_certificate(extension=extension).to_json())[
        "extension"
    ]["lineage_root"] == "c" * 64


def test_rejection_notice_extension_optional():
    bare = RejectionNotice(
        repository="repo",
        commit_sha="abc123",
        requirements_digest="sha256:" + "a" * 64,
        verified_contracts=0,
        unverified_contracts=1,
        failed_contracts=0,
        reasons=["unverified"],
    ).to_dict()
    assert "extension" not in bare
    extended = build_rejection_notice(
        repository="repo",
        commit_sha="abc123",
        requirements_text=REQUIREMENT_TEXT,
        contracts=[{"id": "AUTH-01", "result": "FAIL"}],
        reasons=["regression"],
        extension={"lineage_root": "d" * 64},
    ).to_dict()
    assert extended["extension"] == {"lineage_root": "d" * 64}
    assert extended["result"] == "REJECTED"


def test_issue_certificate_accepts_extension():
    extension = {"lineage_root": "e" * 64, "lineage_nodes": 7, "lineage_edges": 7}
    issued = issue_certificate(
        repository="repo",
        commit_sha="abc123",
        requirements_text=REQUIREMENT_TEXT,
        contracts=[{"id": "AUTH-01", "result": "PASS"}],
        evidence_digests=["sha256:" + "f" * 64],
        extension=extension,
    )
    assert issued is not None
    assert issued.to_dict()["extension"] == extension
    plain = issue_certificate(
        repository="repo",
        commit_sha="abc123",
        requirements_text=REQUIREMENT_TEXT,
        contracts=[{"id": "AUTH-01", "result": "PASS"}],
    )
    assert plain is not None
    assert "extension" not in plain.to_dict()


def test_signed_certificate_with_extension_verifies(monkeypatch):
    from evidence.signing import (
        generate_key_hex,
        public_key_hex,
        sign_json_document,
        verify_statement,
    )

    monkeypatch.setenv("SPECPROOF_SIGNING_KEY", generate_key_hex())
    extension = {
        "lineage_root": "1" * 64,
        "lineage_nodes": 7,
        "lineage_edges": 7,
    }
    statement = sign_json_document(_merge_certificate(extension=extension).to_dict())
    assert statement["payload"]["extension"] == extension
    assert verify_statement(statement, public_key_hex())
    # A legacy payload without the extension field still verifies.
    legacy = sign_json_document(_merge_certificate().to_dict())
    assert verify_statement(legacy, public_key_hex())


# ── publish_report node wiring ──────────────────────────────────────


def test_publish_report_node_writes_lineage_and_attaches_to_certificate(tmp_path):
    state = make_context()
    state.update({
        "output_dir": str(tmp_path),
        "matrix": {"rows": [], "passed": 0, "failed": 0, "unverified": 0},
        "repo_path": "repo",
        "base_ref": "base",
        "head_ref": "head",
        "errors": [],
        "certificate": {"subject": {"repository": "repo"}, "result": "VERIFIED"},
    })
    result = publish_report_node(state)
    lineage_files = list(tmp_path.glob("*-lineage.json"))
    assert len(lineage_files) == 1
    assert result["lineage_path"].endswith("-lineage.json")

    payload = json.loads(lineage_files[0].read_text(encoding="utf-8"))
    assert payload["root_hash"] == result["lineage_root"]
    dag, root = deserialize_lineage(payload)
    ok, diffs = verify_lineage(dag, root)
    assert ok and diffs == []

    assert result["certificate"]["extension"]["lineage_root"] == result["lineage_root"]
    assert result["certificate"]["extension"]["lineage_nodes"] == result["lineage_nodes"]
    assert result["certificate"]["extension"]["lineage_edges"] == result["lineage_edges"]
