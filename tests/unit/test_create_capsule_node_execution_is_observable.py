"""Capsule-packing node execution tests (#200) — honest counters at the
node boundary, written WITH the landing (not backfilled).

The object-metadata recorder is stubbed (best-effort side path); the
capsule files, the zip packaging and the replay scripts are written for
real into a tmp cwd (the node's capsules directory is relative to the
process cwd). One case per outcome word in CREATE_CAPSULE_OUTCOMES:

- packed: a BLOCKER finding (with a MINOR sibling that must be filtered
  out) yields exactly one capsule zip with its full payload, and the
  metadata recorder is invoked once;
- no_findings: an empty confirmed-findings list yields an empty capsules
  list;
- filtered_out: findings that exist but sit below the BLOCKER/MAJOR
  threshold yield the same empty list — the word is the countable
  difference;

plus create_capsule_runs_total on every path and a drift gate binding the
parity family's regex words to CREATE_CAPSULE_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest

from agent.nodes.create_capsule import (
    CREATE_CAPSULE_OUTCOMES,
    create_capsule_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("create_capsule_runs_total",) + tuple(
    f"create_capsule_outcomes_{word}_total"
    for word in sorted(CREATE_CAPSULE_OUTCOMES)
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["create_capsule_runs_total"] = 1.0
    for word in words:
        deltas[f"create_capsule_outcomes_{word}_total"] = 1.0
    return deltas


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


def _stub_metadata(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(
        "storage.object_metadata.record_file_object_best_effort", recorder
    )
    return recorder


class _FakeMinIOClient:
    """An object-store double: records the uploads it was asked to make."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.uploads: list[tuple[str, str, int]] = []

    def put_object_with_digest(
        self,
        bucket: str,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        version: str | None = None,
    ) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("object store unreachable")
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


def _stub_object_store(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail: bool = False,
    index_fails: bool = False,
) -> tuple[_FakeMinIOClient, _FakeMetadataStore]:
    """Stub the two stores the ArtifactStore writes through."""
    objects = _FakeMinIOClient(fail=fail)
    metadata = _FakeMetadataStore(fail=index_fails)
    monkeypatch.setattr("storage.minio.MinIOClient", lambda *a, **k: objects)
    monkeypatch.setattr(
        "storage.object_metadata.default_object_metadata_store",
        lambda: metadata,
    )
    return objects, metadata


def _state(tmp_path: Path, findings: list[dict[str, Any]]) -> dict[str, Any]:
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


# ── the object store: where the bytes ARE ───────────────────────────────────


def _one_finding() -> list[dict[str, Any]]:
    return [{
        "id": "F1",
        "severity": "BLOCKER",
        "confidence": 0.9,
        "contract_id": "AUTH-01",
        "description": "guard removed",
    }]


def test_the_capsule_reaches_the_object_store_and_its_coordinate_comes_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The capsule is uploaded and the coordinate travels with the result.

    A local path says where the file WAS, on the machine that made it.
    The coordinate says where the bytes ARE — and it is the only thing
    that lets the evidence chain (or another machine) find the capsule.
    """
    monkeypatch.chdir(tmp_path)
    _stub_metadata(monkeypatch)
    objects, metadata = _stub_object_store(monkeypatch)

    out = create_capsule_node(_state(tmp_path, _one_finding()))  # type: ignore[arg-type]

    assert len(objects.uploads) == 1
    bucket, name, size = objects.uploads[0]
    assert bucket == "specproof-bug-capsules"
    assert name == "jobs/job-200/capsule-F1.zip"
    assert size > 0
    # The coordinate is "bucket/object-name" — the address the store
    # understands.
    assert out["capsule_refs"] == [f"{bucket}/{name}"]
    # And the object was INDEXED too — the two-store path, not a thinner
    # hand-written upload.
    assert len(metadata.recorded) == 1
    assert metadata.recorded[0].object_ref == f"{bucket}/{name}"


def test_a_capsule_uploaded_but_not_indexed_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The two-store hole: the bytes are durable, but nothing points at them.

    That is a ghost until the reconciliation scan finds it. The capsule
    itself is NOT lost (the zip is on disk), but the evidence chain
    cannot address it — and the run has to say so.
    """
    monkeypatch.chdir(tmp_path)
    _stub_metadata(monkeypatch)
    _stub_object_store(monkeypatch, index_fails=True)
    before = _counter("create_capsule_upload_unindexed_total")

    out = create_capsule_node(_state(tmp_path, _one_finding()))  # type: ignore[arg-type]

    assert _counter("create_capsule_upload_unindexed_total") == before + 1
    # The capsule is intact...
    assert len(out["capsules"]) == 1
    assert Path(out["capsules"][0]).is_file()
    # ...but there is no address, so there is no coordinate.
    assert out["capsule_refs"] == []


def test_a_failed_upload_is_counted_and_the_capsule_stays_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An object store that is down must not cost us the capsule — but it
    must not be silent either.

    The zip is still on disk (the artifact is real); what is missing is
    the ADDRESS. A degraded run that looks like a clean one is worse
    than a run that says it could not upload.
    """
    monkeypatch.chdir(tmp_path)
    _stub_metadata(monkeypatch)
    _stub_object_store(monkeypatch, fail=True)
    before = _counter("create_capsule_upload_failed_total")

    out = create_capsule_node(_state(tmp_path, _one_finding()))  # type: ignore[arg-type]

    assert _counter("create_capsule_upload_failed_total") == before + 1
    # The capsule itself is intact.
    assert len(out["capsules"]) == 1
    assert Path(out["capsules"][0]).is_file()
    # And there is no coordinate — nothing to point at.
    assert out["capsule_refs"] == []


def test_a_successful_upload_is_counted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _stub_metadata(monkeypatch)
    _stub_object_store(monkeypatch)
    before = _counter("create_capsule_upload_succeeded_total")

    create_capsule_node(_state(tmp_path, _one_finding()))  # type: ignore[arg-type]

    assert _counter("create_capsule_upload_succeeded_total") == before + 1


def test_packed_counts_packed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    recorder = _stub_metadata(monkeypatch)
    _stub_object_store(monkeypatch)
    findings = [
        {
            "id": "F1",
            "severity": "BLOCKER",
            "confidence": 0.9,
            "contract_id": "AUTH-01",
            "description": "guard removed",
        },
        {"id": "F2", "severity": "MINOR", "contract_id": "AUTH-01"},
    ]
    before = _before()
    out = create_capsule_node(_state(tmp_path, findings))  # type: ignore[arg-type]

    assert len(out["capsules"]) == 1
    zip_path = Path(out["capsules"][0])
    assert zip_path.is_file()
    assert zip_path.name == "capsule-F1.zip", (
        "the MINOR sibling must be filtered out of the packaging"
    )

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "finding.json" in names
        assert "run.sh" in names
        assert "run.ps1" in names
        assert "README.md" in names
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["finding_id"] == "F1"
    assert manifest["manifest_digest"].startswith("sha256:")

    # The capsule was UPLOADED, so it is indexed by its object coordinate
    # and NOT by its local path: indexing it twice would leave one
    # artifact under two identities.
    assert recorder.calls == [], (
        "an uploaded capsule is indexed by the object store — the file-path "
        "record is for the capsules that could NOT be uploaded"
    )
    assert _deltas(before) == _only("packed")


def test_no_findings_counts_no_findings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _before()
    out = create_capsule_node(_state(tmp_path, []))  # type: ignore[arg-type]

    assert out["capsules"] == []
    assert _deltas(before) == _only("no_findings")


def test_filtered_out_counts_filtered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    findings = [{"id": "F3", "severity": "MINOR", "contract_id": "AUTH-01"}]
    before = _before()
    out = create_capsule_node(_state(tmp_path, findings))  # type: ignore[arg-type]

    assert out["capsules"] == [], (
        "below-threshold findings produce the same empty list as none at all"
    )
    assert _deltas(before) == _only("filtered_out")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "create_capsule.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(
            r'incr\("create_capsule_outcomes_([a-z0-9_]+)_total"\)', source
        )
    )
    assert literals == set(CREATE_CAPSULE_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(CREATE_CAPSULE_OUTCOMES)}"
    )
    assert source.count('incr("create_capsule_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["create_capsule"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(CREATE_CAPSULE_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(CREATE_CAPSULE_OUTCOMES)}"
    )
