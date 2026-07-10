"""MongoDB store — complex replayable artifacts for Phase 0."""

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
        wanted = ["agent_checkpoints", "differential_runs"]
        for name in wanted:
            if name not in existing:
                self.db.create_collection(name)

        # Ensure indexes
        if "agent_checkpoints" in wanted:
            self.db.agent_checkpoints.create_index(
                [("thread_id", 1), ("checkpoint_id", 1)], unique=True, background=True
            )
        if "differential_runs" in wanted:
            self.db.differential_runs.create_index(
                [("job_id", 1), ("contract_id", 1)], background=True
            )

    def save_differential_run(self, run: dict[str, Any]) -> str:
        run.setdefault("created_at", datetime.now(UTC))
        result = self.db.differential_runs.insert_one(run)
        return str(result.inserted_id)

    def get_differential_run(self, job_id: str) -> dict[str, Any] | None:
        return self.db.differential_runs.find_one({"job_id": job_id})

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
