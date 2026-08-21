"""Unit tests for MongoDB schema versioning (§14.2)."""

from __future__ import annotations

from storage.mongodb import (
    MONGO_SCHEMA_VERSION,
    schema_mismatches,
    stamp_schema_version,
)


class TestStamp:
    def test_stamps_missing_version(self) -> None:
        doc = {"job_id": "j1"}
        stamp_schema_version(doc)
        assert doc["schema_version"] == MONGO_SCHEMA_VERSION

    def test_preserves_existing_stamp(self) -> None:
        doc = {"job_id": "j1", "schema_version": "0.9.0"}
        stamp_schema_version(doc)
        assert doc["schema_version"] == "0.9.0"


class TestMismatches:
    def test_empty_for_all_current(self) -> None:
        assert schema_mismatches([
            {"_id": "a", "schema_version": MONGO_SCHEMA_VERSION},
        ]) == []

    def test_legacy_unstamped_listed(self) -> None:
        mismatches = schema_mismatches([{"_id": "a", "job_id": "j1"}])
        assert len(mismatches) == 1
        assert mismatches[0]["_id"] == "a"
        assert mismatches[0]["found"] is None
        assert "legacy" in mismatches[0]["note"]

    def test_newer_version_listed(self) -> None:
        mismatches = schema_mismatches([{"_id": "b", "schema_version": "9.9.9"}])
        assert len(mismatches) == 1
        assert mismatches[0]["found"] == "9.9.9"
        assert mismatches[0]["expected"] == MONGO_SCHEMA_VERSION

    def test_mixed_batch_reports_each(self) -> None:
        mismatches = schema_mismatches([
            {"_id": "a", "schema_version": MONGO_SCHEMA_VERSION},
            {"_id": "b"},
            {"_id": "c", "schema_version": "0.1.0"},
        ])
        assert [m["_id"] for m in mismatches] == ["b", "c"]


class TestStoreWiring:
    def test_save_run_and_pack_get_stamped(self, monkeypatch) -> None:
        from storage import mongodb as module

        inserted: dict = {}

        class FakeCollection:
            def insert_one(self, doc):
                inserted["run"] = dict(doc)
                return type("R", (), {"inserted_id": "id-1"})()

            def replace_one(self, key, doc, upsert):
                inserted["pack"] = dict(doc)
                return type("R", (), {"upserted_id": None})()

        class FakeDB:
            differential_runs = FakeCollection()
            evidence_packs = FakeCollection()

        store = module.MongoDBStore()
        monkeypatch.setattr(module.MongoDBStore, "db", property(lambda s: FakeDB()))
        store.save_differential_run({"job_id": "j1"})
        assert inserted["run"]["schema_version"] == module.MONGO_SCHEMA_VERSION
        store.save_evidence_pack({"job_id": "j1", "contract_id": "AUTH-01"})
        assert inserted["pack"]["schema_version"] == module.MONGO_SCHEMA_VERSION
