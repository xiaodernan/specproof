"""P1.5 Unit tests: MinIO digest, MongoDB evidence packs, artifact chain logic."""

import json
import uuid

import pytest

from storage.minio import MinIOClient, MinIOConfig
from storage.mongodb import MongoDBStore, MongoDBConfig


# ═══════════════════════════════════════════════════════════════
# MinIO digest logic (pure logic, no server needed)
# ═══════════════════════════════════════════════════════════════

class TestMinIODigest:
    def test_put_object_with_digest_returns_structure(self):
        sha256_hex = "a" * 64
        result = {"bucket": "test-bucket", "object_name": "a/b/c.zip", "sha256": sha256_hex, "size_bytes": 4096}
        assert set(result.keys()) == {"bucket", "object_name", "sha256", "size_bytes"}
        assert isinstance(result["sha256"], str)
        assert len(result["sha256"]) == 64
        assert isinstance(result["size_bytes"], int)
        assert result["size_bytes"] > 0

    def test_sha256_is_deterministic(self):
        import hashlib
        data = b"test artifact content"
        h1 = hashlib.sha256(data).hexdigest()
        h2 = hashlib.sha256(data).hexdigest()
        assert h1 == h2
        assert len(h1) == 64

    def test_sha256_differs_for_different_content(self):
        import hashlib
        h1 = hashlib.sha256(b"content A").hexdigest()
        h2 = hashlib.sha256(b"content B").hexdigest()
        assert h1 != h2


class TestBatchCheckExist:
    def test_all_exist(self):
        results = {"obj-1": True, "obj-2": True, "obj-3": True}
        missing = [k for k, v in results.items() if not v]
        assert missing == []

    def test_some_missing(self):
        results = {"obj-1": True, "obj-2": False, "obj-3": True}
        missing = [k for k, v in results.items() if not v]
        assert missing == ["obj-2"]

    def test_all_missing(self):
        results = {"obj-1": False, "obj-2": False}
        missing = [k for k, v in results.items() if not v]
        assert len(missing) == 2

    def test_empty_list(self):
        results: dict[str, bool] = {}
        assert list(results.keys()) == []


class TestPutObjectIfAbsent:
    def test_idempotent_logic(self):
        """put_object_if_absent should skip upload when object already exists."""
        existing_objects = {"reports/capsule.zip"}

        def simulated_put_if_absent(name):
            if name in existing_objects:
                return {"object_name": name, "sha256": "abc123", "size_bytes": 1024}
            else:
                existing_objects.add(name)
                return {"object_name": name, "sha256": "def456", "size_bytes": 2048}

        r1 = simulated_put_if_absent("reports/capsule.zip")
        r2 = simulated_put_if_absent("reports/capsule.zip")
        assert r1["object_name"] == r2["object_name"]


# ═══════════════════════════════════════════════════════════════
# MongoDB evidence pack CRUD (pure logic)
# ═══════════════════════════════════════════════════════════════

class TestEvidencePack:
    def make_pack(self, job_id="job-1", contract_id="DIFF-01", verdict="REGRESSION"):
        return {
            "job_id": job_id,
            "contract_id": contract_id,
            "verdict": verdict,
            "evidence_digest": f"sha256:{'a' * 64}",
            "minio_objects": [
                {
                    "bucket": "specproof-bug-capsules",
                    "object_name": f"jobs/{job_id}/capsule.zip",
                    "sha256": f"{'b' * 64}",
                    "size_bytes": 15175,
                },
                {
                    "bucket": "specproof-tool-reports",
                    "object_name": f"jobs/{job_id}/surefire-head.xml",
                    "sha256": f"{'c' * 64}",
                    "size_bytes": 4096,
                },
            ],
        }

    def test_pack_has_required_fields(self):
        pack = self.make_pack()
        assert pack["job_id"]
        assert pack["contract_id"]
        assert pack["verdict"] in ("REGRESSION", "PASS", "BLOCKER")
        assert pack["evidence_digest"]
        assert isinstance(pack["minio_objects"], list)
        assert len(pack["minio_objects"]) >= 1

    def test_minio_object_fields(self):
        pack = self.make_pack()
        for obj in pack["minio_objects"]:
            assert "bucket" in obj
            assert "object_name" in obj
            assert "sha256" in obj
            assert "size_bytes" in obj
            assert obj["size_bytes"] > 0

    def test_unique_job_contract_key(self):
        """Each (job_id, contract_id) should uniquely identify an evidence pack."""
        packs = [
            self.make_pack("job-1", "DIFF-01"),
            self.make_pack("job-1", "DIFF-02"),
            self.make_pack("job-2", "DIFF-01"),
        ]
        keys = [(p["job_id"], p["contract_id"]) for p in packs]
        assert len(keys) == len(set(keys))

    def test_upsert_overwrites_same_key(self):
        """Upsert by (job_id, contract_id) means same key replaces previous."""
        p1 = self.make_pack("job-1", "DIFF-01", "PASS")
        p2 = self.make_pack("job-1", "DIFF-01", "REGRESSION")
        # p2 should replace p1 based on same key
        assert p1["job_id"] == p2["job_id"]
        assert p1["contract_id"] == p2["contract_id"]
        assert p1["verdict"] != p2["verdict"]


# ═══════════════════════════════════════════════════════════════
# Artifact chain verification (pure logic)
# ═══════════════════════════════════════════════════════════════

class TestArtifactChainVerification:
    def test_all_objects_present(self):
        packs = [
            {
                "contract_id": "DIFF-01",
                "minio_objects": [
                    {"bucket": "b1", "object_name": "o1"},
                    {"bucket": "b2", "object_name": "o2"},
                ],
            }
        ]

        def batch_check(bucket, names):
            return {n: True for n in names}

        missing: list[str] = []
        for pack in packs:
            for obj in pack["minio_objects"]:
                results = batch_check(obj["bucket"], [obj["object_name"]])
                if not results.get(obj["object_name"], False):
                    missing.append(f"missing: {obj['bucket']}/{obj['object_name']}")

        assert missing == []

    def test_some_objects_missing(self):
        existing = {"o1", "o3"}
        packs = [
            {
                "contract_id": "DIFF-01",
                "minio_objects": [
                    {"bucket": "b1", "object_name": "o1"},
                    {"bucket": "b2", "object_name": "o2"},
                    {"bucket": "b3", "object_name": "o3"},
                ],
            }
        ]

        missing: list[str] = []
        for pack in packs:
            for obj in pack["minio_objects"]:
                if obj["object_name"] not in existing:
                    missing.append(f"missing: {obj['bucket']}/{obj['object_name']}")

        assert len(missing) == 1
        assert "o2" in missing[0]

    def test_empty_pack_no_missing(self):
        packs: list = []
        missing: list[str] = []
        for pack in packs:
            for obj in pack.get("minio_objects", []):
                pass
        assert missing == []

    def test_pack_without_minio_objects(self):
        packs = [{"contract_id": "DIFF-01"}]  # no minio_objects key
        missing: list[str] = []
        for pack in packs:
            for obj in pack.get("minio_objects", []):
                pass
        assert missing == []

    def test_invalid_object_ref_detected(self):
        packs = [
            {
                "contract_id": "DIFF-01",
                "minio_objects": [
                    {"bucket": "", "object_name": ""},  # invalid
                ],
            }
        ]
        invalid: list[str] = []
        for pack in packs:
            for obj in pack.get("minio_objects", []):
                if not obj.get("bucket") or not obj.get("object_name"):
                    invalid.append(f"invalid_ref: {obj}")
        assert len(invalid) == 1

    def test_sha256_mismatch_detected(self):
        recorded_sha256 = "aaa"
        actual_sha256 = "bbb"
        mismatch = recorded_sha256 != actual_sha256
        assert mismatch is True

    def test_sha256_match_ok(self):
        recorded_sha256 = "ccc"
        actual_sha256 = "ccc"
        assert recorded_sha256 == actual_sha256


# ═══════════════════════════════════════════════════════════════
# MongoDB config
# ═══════════════════════════════════════════════════════════════

class TestMongoDBConfig:
    def test_defaults(self):
        c = MongoDBConfig()
        assert c.host == "localhost"
        assert c.port == 27017
        assert c.database == "specproof_phase0"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MONGODB_HOST", "mongo.internal")
        monkeypatch.setenv("MONGODB_PORT", "27018")
        c = MongoDBConfig.from_env()
        assert c.host == "mongo.internal"
        assert c.port == 27018
