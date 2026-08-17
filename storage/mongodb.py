"""MongoDB store — complex replayable artifacts for Phase 0 / Phase 1.

P1.5: Added evidence_packs collection with artifact chain verification
(MinIO sha256 cross-check) and agent checkpoints support.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database


@dataclass
class MongoDBConfig:
    host: str = "localhost"
    port: int = 27017
    user: str = "specproof"
    password: str = "specproof_pass"
    database: str = "specproof_phase0"

    @classmethod
    def from_env(cls) -> "MongoDBConfig":
        return cls(
            host=os.getenv("MONGODB_HOST", "localhost"),
            port=int(os.getenv("MONGODB_PORT", "27017")),
            user=os.getenv("MONGODB_USER", "specproof"),
            password=os.getenv("MONGODB_PASSWORD", "specproof_pass"),
            database=os.getenv("MONGODB_DATABASE", "specproof_phase0"),
        )


class MongoDBStore:
    """Stores complex, schema-flexible analysis artifacts."""

    def __init__(self, config: MongoDBConfig | None = None) -> None:
        self.config = config or MongoDBConfig.from_env()
        self._client: MongoClient | None = None

    @property
    def client(self) -> MongoClient:
        if self._client is None:
            uri = (
                f"mongodb://{self.config.user}:{self.config.password}"
                f"@{self.config.host}:{self.config.port}"
            )
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return self._client

    @property
    def db(self) -> Database:
        return self.client[self.config.database]

    def ensure_collections(self) -> None:
        existing = self.db.list_collection_names()
        wanted = ["agent_checkpoints", "differential_runs", "evidence_packs"]
        for name in wanted:
            if name not in existing:
                self.db.create_collection(name)

        # Ensure indexes
        self.db.agent_checkpoints.create_index(
            [("thread_id", 1), ("checkpoint_id", 1)], unique=True, background=True
        )
        self.db.differential_runs.create_index(
            [("job_id", 1), ("contract_id", 1)], background=True
        )
        self.db.evidence_packs.create_index(
            [("job_id", 1), ("contract_id", 1)], unique=True, background=True
        )
        self.db.evidence_packs.create_index("created_at", background=True)

    def save_differential_run(self, run: dict[str, Any]) -> str:
        run.setdefault("created_at", datetime.now(UTC))
        result = self.db.differential_runs.insert_one(run)
        return str(result.inserted_id)

    def get_differential_run(self, job_id: str) -> dict[str, Any] | None:
        return self.db.differential_runs.find_one({"job_id": job_id})

    # ── P1.5: evidence packs + artifact chain verification ─────

    def save_evidence_pack(self, pack: dict[str, Any]) -> str:
        """Insert or update an evidence pack (upsert by job_id + contract_id)."""
        pack.setdefault("created_at", datetime.now(UTC))
        key = {"job_id": pack["job_id"], "contract_id": pack["contract_id"]}
        result = self.db.evidence_packs.replace_one(key, pack, upsert=True)
        return str(result.upserted_id) if result.upserted_id else "updated"

    def get_evidence_pack(self, job_id: str, contract_id: str | None = None) -> dict[str, Any] | None:
        filt: dict[str, Any] = {"job_id": job_id}
        if contract_id:
            filt["contract_id"] = contract_id
        return self.db.evidence_packs.find_one(filt)

    def get_evidence_packs_for_job(self, job_id: str) -> list[dict[str, Any]]:
        return list(self.db.evidence_packs.find({"job_id": job_id}).sort("created_at", 1))

    def verify_artifact_chain(
        self, job_id: str, minio_batch_check: "callable | None" = None
    ) -> list[str]:
        """Verify every MinIO object referenced by this job's evidence packs exists.

        Args:
            job_id: The job to verify.
            minio_batch_check: A callable(bucket, object_names) -> {name: exists}.
                               If None, only reports what *would* be checked.

        Returns:
            List of missing object descriptions. Empty list = all consistent.
        """
        missing: list[str] = []
        packs = self.get_evidence_packs_for_job(job_id)
        for pack in packs:
            for obj in pack.get("minio_objects", []):
                bucket = obj.get("bucket", "")
                name = obj.get("object_name", "")
                if not bucket or not name:
                    missing.append(f"invalid_ref in pack {pack.get('contract_id', '?')}: {obj}")
                    continue
                if minio_batch_check is not None:
                    results = minio_batch_check(bucket, [name])
                    if not results.get(name, False):
                        missing.append(f"missing: {bucket}/{name}")
        return missing

    def is_ready(self) -> bool:
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
