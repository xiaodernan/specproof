"""The row must say WHERE the evidence for that requirement is (#366b).

The evidence chain has an address — the object-store coordinate of the
capsule ("bucket/object-name"), where the bytes ARE, not where the
local file was. Until now that address lived only in the state and in
the evidence pack: the matrix row, which is what a reader reads, could
not point at it.

For the row to carry the address, the capsules have to be packaged
BEFORE the matrix is built — hence the graph order. The capsules do not
read the matrix (they package the Review Court's confirmed findings),
so the order costs nothing.

What is asserted here:
- the capsule node records the coordinate against the contract it
  belongs to (a flat list of addresses cannot be attributed);
- the row carries those records — an empty list when the contract has
  no capsule, never a missing field;
- the row's verdict is untouched: an address is not a reason;
- the address reaches the reader (the HTML report, the job summary).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent.nodes.build_matrix import build_matrix_node
from agent.nodes.create_capsule import create_capsule_node

BUCKET = "specproof-bug-capsules"
NAME = "jobs/job-200/capsule-F1.zip"
REF = f"{BUCKET}/{NAME}"


class _FakeMinIOClient:
    """An object-store double: records the uploads it was asked to make."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, str, int]] = []
        self.removed: list[tuple[str, str]] = []

    def put_object_with_digest(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]:
        self.uploads.append((bucket, object_name, len(data)))
        return {
            "bucket": bucket,
            "object_name": object_name,
            "sha256": "a" * 64,
            "size_bytes": len(data),
            "content_type": content_type,
            "version": version,
        }

    def remove_object(self, bucket: str, object_name: str) -> None:
        self.removed.append((bucket, object_name))


class _FakeMetadataStore:
    """An index double: records what was indexed, and can refuse."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.recorded: list[Any] = []

    def record(self, metadata: Any) -> Any:
        if self.fail:
            raise RuntimeError("index unavailable")
        self.recorded.append(metadata)
        return metadata


def _stub_stores(
    monkeypatch: pytest.MonkeyPatch, *, index_fails: bool = False,
) -> _FakeMinIOClient:
    objects = _FakeMinIOClient()
    metadata = _FakeMetadataStore(fail=index_fails)
    monkeypatch.setattr("storage.minio.MinIOClient", lambda *a, **k: objects)
    monkeypatch.setattr(
        "storage.object_metadata.default_object_metadata_store",
        lambda: metadata,
    )
    return objects


def _finding(contract_id: str = "AUTH-01") -> dict[str, Any]:
    return {
        "id": "F1",
        "severity": "BLOCKER",
        "confidence": 0.9,
        "contract_id": contract_id,
        "description": "guard removed",
    }


def _capsule_state(
    tmp_path: Path, findings: list[dict[str, Any]],
) -> dict[str, Any]:
    tests = tmp_path / "SpecProofGeneratedTest.java"
    tests.write_text("class SpecProofGeneratedTest {}", encoding="utf-8")
    return {
        "confirmed_findings": findings,
        "contracts": [{"id": "AUTH-01", "checker_type": "http"}],
        "requirement_text": "Unauthenticated requests must receive 401.",
        "generated_tests_path": str(tests),
        "base_ref": "base",
        "head_ref": "head-v1",
        "job_id": "job-200",
    }


def _matrix(state: dict[str, Any]) -> dict[str, Any]:
    return build_matrix_node(state)["matrix"]  # type: ignore[arg-type]


def _row(matrix: dict[str, Any], contract_id: str = "AUTH-01") -> dict[str, Any]:
    return next(r for r in matrix["rows"] if r["contract_id"] == contract_id)


# ── the capsule node records the address against its contract ────────────


def test_the_capsule_node_records_the_address_against_its_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A flat list of addresses cannot be attributed to a requirement
    without guessing — so the mapping is recorded too."""
    _stub_stores(monkeypatch)
    monkeypatch.chdir(tmp_path)

    out = create_capsule_node(_capsule_state(tmp_path, [_finding()]))  # type: ignore[arg-type]

    assert out["capsule_refs"] == [REF]
    records = out["artifact_records_by_contract"]["AUTH-01"]
    assert [record["ref"] for record in records] == [REF]
    # The digest travels with the address: the reader can check the
    # bytes they fetch against what the row says.
    assert records[0]["sha256"] == "a" * 64
    assert records[0]["size_bytes"] > 0
    assert records[0]["indexed"] is True


def test_a_capsule_without_a_contract_is_not_attributed_to_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A finding with no contract id has no contract to attribute the
    address to — the address still travels, but unattributed."""
    _stub_stores(monkeypatch)
    monkeypatch.chdir(tmp_path)

    out = create_capsule_node(_capsule_state(tmp_path, [_finding("")]))  # type: ignore[arg-type]

    assert out["capsule_refs"] == [REF]
    assert out["artifact_records_by_contract"] == {}


def test_an_uploaded_but_unindexed_capsule_is_recorded_as_a_ghost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The bytes are in the store, but no index row points at them. The
    record says exactly that — a row that reads "no capsule" while the
    object sits in the bucket would be a different, and false, story."""
    _stub_stores(monkeypatch, index_fails=True)
    monkeypatch.chdir(tmp_path)

    out = create_capsule_node(_capsule_state(tmp_path, [_finding()]))  # type: ignore[arg-type]

    record = out["artifact_records_by_contract"]["AUTH-01"][0]
    assert record["ref"] == REF
    assert record["uploaded"] is True
    assert record["indexed"] is False
    assert "NOT indexed" in record["note"]


def test_a_capsule_that_never_reached_the_store_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The store is down: the zip is on disk, the address is empty, and
    the record says which."""

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("object store unreachable")

    monkeypatch.setattr("storage.minio.MinIOClient", _boom)
    monkeypatch.chdir(tmp_path)

    out = create_capsule_node(_capsule_state(tmp_path, [_finding()]))  # type: ignore[arg-type]

    assert out["capsule_refs"] == []
    record = out["artifact_records_by_contract"]["AUTH-01"][0]
    assert record["ref"] == ""
    assert record["uploaded"] is False
    assert "upload failed" in record["note"]


# ── the row carries the records ──────────────────────────────────────────


def _state_with_capsule(
    tmp_path: Path, contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    capsule = create_capsule_node(_capsule_state(tmp_path, [_finding()]))  # type: ignore[arg-type]
    return {
        **_capsule_state(tmp_path, [_finding()]),
        "capsule_refs": capsule["capsule_refs"],
        "artifact_records_by_contract": capsule["artifact_records_by_contract"],
        "contracts": contracts,
    }


def test_the_row_carries_the_records_of_its_own_capsule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _stub_stores(monkeypatch)
    monkeypatch.chdir(tmp_path)

    state = _state_with_capsule(tmp_path, [
        {"id": "AUTH-01", "checker_type": "http"},
        {"id": "TX-01", "checker_type": "http"},
    ])
    row = _row(_matrix(state))
    assert [record["ref"] for record in row["artifact_records"]] == [REF]
    assert row["artifact_records"][0]["sha256"] == "a" * 64


def test_a_contract_without_a_capsule_gets_an_empty_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Empty, not missing: "nothing was packaged for this contract" is a
    fact the reader can see."""
    _stub_stores(monkeypatch)
    monkeypatch.chdir(tmp_path)

    state = _state_with_capsule(tmp_path, [
        {"id": "AUTH-01", "checker_type": "http"},
        {"id": "TX-01", "checker_type": "http"},
    ])
    row = _row(_matrix(state), "TX-01")
    assert row["artifact_records"] == []


def test_the_records_never_change_the_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """An address and a digest are not reasons: the row's result is
    decided by the experiments."""
    _stub_stores(monkeypatch)
    monkeypatch.chdir(tmp_path)

    base_state = {
        **_capsule_state(tmp_path, [_finding()]),
        "contracts": [{"id": "AUTH-01", "checker_type": "http"}],
    }
    without = _row(_matrix(base_state))
    with_records = _row(_matrix(_state_with_capsule(
        tmp_path, [{"id": "AUTH-01", "checker_type": "http"}],
    )))
    assert with_records["artifact_records"]
    assert with_records["result"] == without["result"]
    assert with_records["unverified_reason"] == without["unverified_reason"]


# ── the address reaches the reader ───────────────────────────────────────


def test_the_report_shows_the_address_and_the_digest() -> None:
    from evidence.report import render_verification_report

    matrix = {
        "rows": [{
            "contract_id": "AUTH-01",
            "requirement": "unauthenticated must 401",
            "result": "FAIL",
            "experiment": "DIFF-01",
            "evidence": "sha256:abc",
            "artifact_records": [{
                "ref": REF,
                "uploaded": True,
                "indexed": True,
                "sha256": "b" * 64,
                "size_bytes": 2048,
                "content_type": "application/zip",
                "note": "",
            }],
        }],
        "passed": 0,
        "failed": 1,
        "unverified": 0,
    }
    html = render_verification_report(
        "repo", "base", "head", matrix, [], generated_at="2026-01-01 00:00:00 UTC",
    )
    assert REF in html
    assert "bbbbbbbbbbbbbbbb" in html


def test_the_report_says_a_capsule_that_never_reached_the_store() -> None:
    from evidence.report import render_verification_report

    matrix = {
        "rows": [{
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "artifact_records": [{
                "ref": "",
                "uploaded": False,
                "indexed": False,
                "sha256": "",
                "size_bytes": 0,
                "content_type": "",
                "note": "the upload failed — the capsule stays a local artifact",
            }],
        }],
        "passed": 0,
        "failed": 1,
        "unverified": 0,
    }
    html = render_verification_report(
        "repo", "base", "head", matrix, [], generated_at="2026-01-01 00:00:00 UTC",
    )
    assert "not uploaded" in html


def test_the_summary_carries_the_records_to_the_api() -> None:
    from agent.worker import _matrix_rows_for_summary

    matrix = {
        "rows": [{
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "artifact_records": [{"ref": REF, "indexed": True}],
        }],
        "total_rows": 1,
    }
    summary = _matrix_rows_for_summary(matrix)
    assert summary["matrix_rows"][0]["artifact_records"][0]["ref"] == REF


def test_the_capsules_are_packaged_before_the_matrix_is_built() -> None:
    """The order is what makes the address possible: the matrix can only
    carry an address that already exists."""
    from agent.graph import build_phase0_graph

    edges = {
        (e.source, e.target)
        for e in build_phase0_graph().get_graph().edges
    }
    assert ("review_court", "create_capsule") in edges
    assert ("create_capsule", "build_matrix") in edges
