"""W38 unit tests — object metadata store (§A task 7).

No Docker, no network: SQLite runs on a temp file, MySQL is covered by
the MYSQL_URL-gated integration module. Covers:

- record shape validation (kind / payload digest / object id);
- query by job_id / kind / digest / contract_id;
- digest roundtrip through real files;
- metadata-first resolution + legacy fallback (resolve_object);
- SQLite persistence across store instances (cross-process property);
- wiring: capsule/replay-report/certificate recording through the
  shared default-store seam.
"""

from __future__ import annotations

import hashlib
import json
import zipfile

import pytest

from storage.object_metadata import (
    InMemoryObjectMetadataStore,
    InvalidDigestError,
    InvalidObjectKindError,
    ObjectAlreadyExistsError,
    ObjectMetadataError,
    SQLiteObjectMetadataStore,
    new_metadata,
    new_object_id,
    normalize_payload_digest,
    payload_sha256_of_file,
    record_file_object,
    resolve_object,
    sha256_hex,
)


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _payload_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _meta(**overrides: object) -> object:
    fields: dict[str, object] = {
        "kind": "capsule",
        "digests": {"payload_sha256": "a" * 64},
        "job_id": "job-1",
        "contract_ids": ("AUTH-01",),
        "path_hint": "capsules/capsule-AUTH-01.zip",
    }
    fields.update(overrides)
    return new_metadata(**fields)  # type: ignore[arg-type]


# ── validation ─────────────────────────────────────────────────────────────


def test_new_metadata_rejects_bad_kind_and_digest():
    with pytest.raises(InvalidObjectKindError):
        new_metadata("photo", {"payload_sha256": "a" * 64})  # type: ignore[arg-type]
    with pytest.raises(InvalidDigestError):
        new_metadata("capsule", {})
    with pytest.raises(InvalidDigestError):
        new_metadata("capsule", {"payload_sha256": "not-a-digest"})
    with pytest.raises(ObjectMetadataError):
        new_metadata("capsule", {"payload_sha256": "a" * 64}, object_id="nope")


def test_new_metadata_normalizes_sha256_prefix():
    metadata = _meta(digests={"payload_sha256": "sha256:" + "b" * 64})
    assert metadata.digests["payload_sha256"] == "b" * 64
    assert normalize_payload_digest("SHA256:" + "c" * 64) == "c" * 64


def test_new_object_id_is_uuid4_hex():
    first = new_object_id()
    second = new_object_id()
    assert first != second
    assert len(first) == 32
    assert all(char in "0123456789abcdef" for char in first)


# ── record + queries (shared across backends) ──────────────────────────────


@pytest.fixture(params=["inmemory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path):
    if request.param == "inmemory":
        backend = InMemoryObjectMetadataStore()
    else:
        backend = SQLiteObjectMetadataStore(tmp_path / "objects.sqlite3")
    yield backend
    backend.close()


def _seed(store):
    clock = FakeClock()
    return [
        store.record(new_metadata(
            "capsule", {"payload_sha256": "1" * 64},
            job_id="job-1", contract_ids=("AUTH-01", "UNIQUE-01"),
            path_hint="capsules/capsule-F-1.zip", now=clock,
        )),
        store.record(new_metadata(
            "certificate", {"payload_sha256": "2" * 64},
            job_id="job-1", contract_ids=("AUTH-01",),
            path_hint="reports/merge-certificate-job1.json", now=clock,
        )),
        store.record(new_metadata(
            "replay_report", {"payload_sha256": "3" * 64},
            job_id="job-2", contract_ids=("UNIQUE-01",),
            path_hint="reports/job2-lineage.json", now=clock,
        )),
    ]


def test_record_get_roundtrip(store):
    metadata = _seed(store)[0]
    fetched = store.get(metadata.object_id)
    assert fetched == metadata
    assert fetched is not None
    assert fetched.kind == "capsule"
    assert fetched.digests == {"payload_sha256": "1" * 64}
    assert fetched.contract_ids == ("AUTH-01", "UNIQUE-01")


def test_duplicate_object_id_raises(store):
    metadata = _seed(store)[0]
    with pytest.raises(ObjectAlreadyExistsError):
        store.record(metadata)


def test_queries_by_job_kind_digest_contract(store):
    _seed(store)
    by_job = store.by_job("job-1")
    assert {m.kind for m in by_job} == {"capsule", "certificate"}
    by_kind = store.by_kind("replay_report")
    assert len(by_kind) == 1
    assert by_kind[0].job_id == "job-2"
    by_digest = store.by_digest("sha256:" + "2" * 64)
    assert [m.kind for m in by_digest] == ["certificate"]
    by_contract = store.by_contract("AUTH-01")
    assert {m.kind for m in by_contract} == {"capsule", "certificate"}
    assert store.by_contract("MISSING") == []
    assert store.by_job("missing-job") == []


def test_created_at_uses_injected_clock():
    clock = FakeClock(42.0)
    store = InMemoryObjectMetadataStore(now_fn=clock)
    metadata = store.record(new_metadata(
        "capsule", {"payload_sha256": "4" * 64}, now=clock,
    ))
    assert metadata.created_at == 42.0


# ── digest roundtrip through real files ────────────────────────────────────


def test_record_file_object_digest_roundtrip(tmp_path):
    payload = b"capsule-bytes"
    target = tmp_path / "capsule.zip"
    target.write_bytes(payload)
    assert payload_sha256_of_file(target) == _payload_digest(payload)
    assert sha256_hex(payload) == _payload_digest(payload)

    store = InMemoryObjectMetadataStore()
    record = record_file_object(store, "capsule", target, job_id="j", contract_ids=("AUTH-01",))
    assert record.digests["payload_sha256"] == _payload_digest(payload)
    assert record.path_hint == str(target.resolve())
    assert store.by_digest(_payload_digest(payload)) == [record]

    # The digest query roundtrips through a SECOND store instance, the way
    # a verify process and a replay process share one SQLite file.
    db_path = tmp_path / "objects.sqlite3"
    sqlite_store = SQLiteObjectMetadataStore(db_path)
    sqlite_store.record(record)
    sqlite_store.close()
    reopened = SQLiteObjectMetadataStore(db_path)
    assert reopened.by_digest(_payload_digest(payload))[0].object_id == record.object_id
    assert reopened.by_contract("AUTH-01")[0].object_id == record.object_id
    reopened.close()


# ── metadata-first resolution + legacy fallback ────────────────────────────


def test_resolve_object_by_id_digest_and_path(store):
    records = _seed(store)
    capsule, certificate, replay = records
    assert resolve_object(store, capsule.object_id) == capsule
    assert resolve_object(store, "sha256:" + "2" * 64) == certificate
    assert resolve_object(store, "reports/merge-certificate-job1.json") == certificate
    # A recorded hint for this test file resolves by its own path.
    absolute = record_file_object(store, "capsule", __file__)
    assert resolve_object(store, __file__) == absolute



def test_resolve_object_miss_falls_back_to_legacy_lookup(store):
    # No record — the caller keeps the legacy path-based lookup. This is
    # exactly the pre-existing-artifact case: nothing in the store, the
    # path still works.
    assert resolve_object(store, "legacy-capsule.zip") is None
    assert resolve_object(store, "f" * 64) is None
    assert resolve_object(store, "") is None


def test_sqlite_store_survives_reopen(tmp_path):
    db_path = tmp_path / "persist.sqlite3"
    first = SQLiteObjectMetadataStore(db_path)
    metadata = _meta()
    first.record(metadata)
    first.close()
    second = SQLiteObjectMetadataStore(db_path)
    assert second.get(metadata.object_id) == metadata
    assert second.by_job("job-1") == [metadata]
    second.close()


# ── wiring: artifact writers record metadata through the default store ────


@pytest.fixture()
def shared_store(monkeypatch) -> InMemoryObjectMetadataStore:
    store = InMemoryObjectMetadataStore()
    monkeypatch.setattr(
        "storage.object_metadata.default_object_metadata_store",
        lambda: store,
    )
    return store


def test_create_capsule_node_records_capsule_metadata(shared_store, tmp_path, monkeypatch):
    from agent.nodes.create_capsule import create_capsule_node

    monkeypatch.chdir(tmp_path)
    state: dict[str, object] = {
        "confirmed_findings": [{
            "id": "F-9",
            "contract_id": "AUTH-01",
            "severity": "BLOCKER",
            "confidence": 0.95,
            "evidence_type": "differential_execution",
            "evidence_digest": "sha256:" + "9" * 64,
            "description": "regression",
        }],
        "contracts": [{
            "id": "AUTH-01", "checker_type": "http", "result": "FAIL",
        }],
        "requirement_text": "auth",
        "generated_tests_path": "",
        "base_ref": "base",
        "head_ref": "head-v1",
        "job_id": "job-capsule-1",
    }
    result = create_capsule_node(state)  # type: ignore[arg-type]
    capsule_paths = result["capsules"]
    assert len(capsule_paths) == 1

    records = shared_store.by_kind("capsule")
    assert len(records) == 1
    record = records[0]
    assert record.job_id == "job-capsule-1"
    assert record.contract_ids == ("AUTH-01",)
    assert record.path_hint == capsule_paths[0]
    expected = payload_sha256_of_file(capsule_paths[0])
    assert record.digests["payload_sha256"] == expected
    assert shared_store.by_digest(expected) == [record]
    assert shared_store.by_contract("AUTH-01") == [record]
    assert shared_store.by_job("job-capsule-1") == [record]


def test_publish_report_node_records_replay_report_metadata(shared_store, tmp_path):
    from agent.nodes.publish_report import publish_report_node

    state: dict[str, object] = {
        "output_dir": str(tmp_path),
        "matrix": {"rows": [], "passed": 0, "failed": 0, "unverified": 0},
        "repo_path": "repo",
        "base_ref": "base",
        "head_ref": "head",
        "errors": [],
        "job_id": "job-report-1",
        "contracts": [{"id": "AUTH-01", "version": 2, "checker_version": "2.0.0"}],
        "requirement_text": "Only authenticated users may change the email.",
    }
    result = publish_report_node(state)  # type: ignore[arg-type]
    records = shared_store.by_job("job-report-1")
    assert {m.kind for m in records} == {"replay_report"}
    assert len(records) == 2  # lineage.json + HTML report
    recorded_paths = {m.path_hint for m in records}
    assert result["lineage_path"] in recorded_paths
    assert result["report_path"] in recorded_paths
    for record in records:
        assert record.contract_ids == ("AUTH-01",)


def test_verify_certificate_recording_roundtrip(shared_store, tmp_path):
    from cli.specproof.commands.verify import _record_certificate_metadata

    cert_path = tmp_path / "merge-certificate-job1.json"
    cert_path.write_text(json.dumps({"subject": {"repository": "repo"}, "result": "VERIFIED"}))
    _record_certificate_metadata(cert_path, "job-cert-1", ["AUTH-01"])
    records = shared_store.by_kind("certificate")
    assert len(records) == 1
    assert records[0].job_id == "job-cert-1"
    assert records[0].contract_ids == ("AUTH-01",)
    assert records[0].digests["payload_sha256"] == payload_sha256_of_file(cert_path)
    assert resolve_object(shared_store, records[0].object_id) == records[0]
    assert resolve_object(shared_store, payload_sha256_of_file(cert_path)) == records[0]


def test_replay_command_resolves_via_metadata_first_and_records_report(
    shared_store, tmp_path,
):
    from click.testing import CliRunner

    from cli.specproof.commands.replay import replay

    # A capsule produced by a previous run, recorded in the shared store.
    manifest = {
        "finding_id": "F-7",
        "severity": "MAJOR",
        "contract_id": "AUTH-01",
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_digest"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    capsule_zip = tmp_path / "capsule-F-7.zip"
    with zipfile.ZipFile(capsule_zip, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    capsule_record = record_file_object(
        shared_store,
        "capsule",
        capsule_zip,
        job_id="job-7",
        contract_ids=("AUTH-01",),
    )

    out_dir = tmp_path / "replay-out"
    runner = CliRunner()
    # Resolve by OBJECT ID (not a path) — the metadata store is the only
    # thing that knows where this capsule lives.
    result = runner.invoke(replay, [capsule_record.object_id, "--output-dir", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert "Payload digest verified" in result.output
    manifest_out = out_dir / "manifest.json"
    assert manifest_out.exists()

    # The replay wrote + recorded a replay_report inheriting job/contracts.
    replay_records = [r for r in shared_store.by_kind("replay_report") if r.job_id == "job-7"]
    assert len(replay_records) == 1
    assert replay_records[0].contract_ids == ("AUTH-01",)
    report_path = out_dir / "replay-report.json"
    assert report_path.exists()
    assert replay_records[0].path_hint == str(report_path.resolve())


def test_replay_command_legacy_path_fallback(shared_store, tmp_path):
    from click.testing import CliRunner

    from cli.specproof.commands.replay import replay

    # A pre-existing capsule with NO metadata record: the legacy path-based
    # lookup must keep working (backward compatibility, no digest gate).
    manifest = {"finding_id": "F-8", "severity": "MINOR", "contract_id": "AUTH-01"}
    capsule_zip = tmp_path / "legacy.zip"
    with zipfile.ZipFile(capsule_zip, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    out_dir = tmp_path / "legacy-out"
    runner = CliRunner()
    result = runner.invoke(replay, [str(capsule_zip), "--output-dir", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert (out_dir / "manifest.json").exists()
    # The legacy replay still produces a recorded replay report.
    assert (out_dir / "replay-report.json").exists()
    assert shared_store.by_kind("replay_report")


def test_replay_command_detects_tampered_capsule_via_metadata(shared_store, tmp_path):
    from click.testing import CliRunner

    from cli.specproof.commands.replay import replay

    manifest = {"finding_id": "F-6", "severity": "MAJOR", "contract_id": "AUTH-01"}
    capsule_zip = tmp_path / "tampered.zip"
    with zipfile.ZipFile(capsule_zip, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
    record = record_file_object(shared_store, "capsule", capsule_zip)
    # Tamper AFTER the record: the payload no longer matches its digest.
    with zipfile.ZipFile(capsule_zip, "a") as archive:
        archive.writestr("extra.txt", "injected")
    runner = CliRunner()
    result = runner.invoke(replay, [record.object_id, "--output-dir", str(tmp_path / "tamper-out")])
    assert result.exit_code == 1
    assert "digest mismatch" in result.output


def test_resolve_object_on_empty_store_is_legacy_fallback_path():
    store = InMemoryObjectMetadataStore()
    assert resolve_object(store, "reports/old-report.html") is None
    assert store.list() == []
