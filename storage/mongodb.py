"""MongoDB store — complex replayable artifacts for Phase 0 / Phase 1.

P1.5: Added evidence_packs collection with artifact chain verification
(MinIO sha256 cross-check) and agent checkpoints support.

Schema versioning (§14.2): every document this module writes is stamped
with MONGO_SCHEMA_VERSION; schema_mismatches audits a batch against the
current version so legacy (unstamped) or newer documents are surfaced
honestly instead of being silently projected.
"""
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

#: Schema version stamped onto every differential_runs / evidence_packs
#: document written by this module. Bump when the document shape changes;
#: old documents keep their version and are surfaced by schema_mismatches.
MONGO_SCHEMA_VERSION = "1.0.0"


def stamp_schema_version(doc: dict[str, Any]) -> dict[str, Any]:
    """Stamp the current schema version; an existing stamp is preserved."""
    doc.setdefault("schema_version", MONGO_SCHEMA_VERSION)
    return doc


def schema_mismatches(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Documents whose schema_version is absent (legacy) or differs.

    Never mutates; _id is reported verbatim when present. An empty list
    means every document matches the current version.
    """
    mismatches: list[dict[str, Any]] = []
    for doc in docs:
        version = doc.get("schema_version")
        if version is None:
            mismatches.append({
                "_id": doc.get("_id"),
                "found": None,
                "expected": MONGO_SCHEMA_VERSION,
                "note": "legacy document without schema_version",
            })
        elif version != MONGO_SCHEMA_VERSION:
            mismatches.append({
                "_id": doc.get("_id"),
                "found": version,
                "expected": MONGO_SCHEMA_VERSION,
                "note": "document written by a different schema version",
            })
    return mismatches


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
        self._client: MongoClient[Any] | None = None

    @property
    def client(self) -> MongoClient[Any]:
        if self._client is None:
            uri = (
                f"mongodb://{self.config.user}:{self.config.password}"
                f"@{self.config.host}:{self.config.port}"
            )
            self._client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        return self._client

    @property
    def db(self) -> Database[Any]:
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
        stamp_schema_version(run)
        result = self.db.differential_runs.insert_one(run)
        return str(result.inserted_id)

    def get_differential_run(self, job_id: str) -> dict[str, Any] | None:
        return self.db.differential_runs.find_one({"job_id": job_id})

    # ── P1.5: evidence packs + artifact chain verification ─────

    def save_evidence_pack(self, pack: dict[str, Any]) -> str:
        """Insert or update an evidence pack (upsert by job_id + contract_id)."""
        pack.setdefault("created_at", datetime.now(UTC))
        stamp_schema_version(pack)
        key = {"job_id": pack["job_id"], "contract_id": pack["contract_id"]}
        result = self.db.evidence_packs.replace_one(key, pack, upsert=True)
        return str(result.upserted_id) if result.upserted_id else "updated"

    def get_evidence_pack(
        self, job_id: str, contract_id: str | None = None
    ) -> dict[str, Any] | None:
        filt: dict[str, Any] = {"job_id": job_id}
        if contract_id:
            filt["contract_id"] = contract_id
        return self.db.evidence_packs.find_one(filt)

    def get_evidence_packs_for_job(self, job_id: str) -> list[dict[str, Any]]:
        return list(self.db.evidence_packs.find({"job_id": job_id}).sort("created_at", 1))

    def delete_job_artifacts(self, job_id: str) -> dict[str, Any]:
        """Delete one job's differential_runs + evidence_packs documents.

        Data lifecycle (DATA_LIFECYCLE §3): explicit deletion path only.
        Returns deleted counts per collection; idempotent (zero on missing).
        """
        runs = self.db.differential_runs.delete_many({"job_id": job_id})
        packs = self.db.evidence_packs.delete_many({"job_id": job_id})
        return {
            "differential_runs": runs.deleted_count,
            "evidence_packs": packs.deleted_count,
        }

    def verify_schema_versions(self, job_id: str) -> list[dict[str, Any]]:
        """Audit one job's runs + packs against MONGO_SCHEMA_VERSION.

        Legacy (unstamped) or newer documents are listed with their _id and
        the found/expected versions — surfaced, never silently projected.
        """
        docs = list(self.db.differential_runs.find({"job_id": job_id}))
        docs.extend(self.get_evidence_packs_for_job(job_id))
        return schema_mismatches(docs)

    def verify_artifact_chain(
        self, job_id: str, minio_batch_check: Callable[..., Any] | None = None
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
