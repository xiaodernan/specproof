"""MongoDB-backed LangGraph checkpoint saver (P1.6).

Implements BaseCheckpointSaver so the compiled graph persists state
after every node execution. Worker crash recovery reads the latest
checkpoint and resumes from the interrupted node.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from storage.mongodb import MongoDBStore

logger = logging.getLogger(__name__)


class MongoDBSaver(BaseCheckpointSaver):
    """Persist LangGraph checkpoints to MongoDB.

    Each checkpoint is stored as a document in the `agent_checkpoints` collection.
    Checkpoint lookup is keyed by `thread_id` (which is the job_id).
    """

    def __init__(self, store: MongoDBStore | None = None) -> None:
        super().__init__(serde=JsonPlusSerializer())
        self._store = store or MongoDBStore()
        self._store.ensure_collections()

    @property
    def collection(self):
        return self._store.db.agent_checkpoints

    # ── Core interface ──────────────────────────────────────────

    def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """Get the latest checkpoint for a thread_id (job_id)."""
        thread_id = self._thread_id(config)
        if not thread_id:
            return None

        doc = self.collection.find_one(
            {"thread_id": thread_id},
            sort=[("checkpoint_id", -1)],
        )
        if not doc:
            return None

        checkpoint = self._doc_to_checkpoint(doc)
        metadata = self._doc_to_metadata(doc)
        parent_config = (
            {"configurable": {"thread_id": thread_id, "checkpoint_id": doc["parent_checkpoint_id"]}}
            if doc.get("parent_checkpoint_id")
            else None
        )
        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_id": doc["checkpoint_id"]}},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
        )

    def put(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> dict[str, Any]:
        """Save a checkpoint. Upserts by (thread_id, checkpoint_id)."""
        thread_id = self._thread_id(config)
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config.get("configurable", {}).get("checkpoint_id")

        doc = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "checkpoint_ns": config.get("configurable", {}).get("checkpoint_ns", ""),
            "checkpoint": {
                "v": checkpoint.get("v", 1),
                "id": checkpoint_id,
                "ts": checkpoint.get("ts", ""),
                "channel_values": self._serialize_channels(checkpoint.get("channel_values", {})),
                "channel_versions": dict(checkpoint.get("channel_versions", {})),
                "versions_seen": {
                    k: dict(v) for k, v in checkpoint.get("versions_seen", {}).items()
                },
            },
            "metadata": {
                "source": metadata.get("source", ""),
                "step": metadata.get("step", -1),
                "writes": metadata.get("writes", {}),
                "parents": metadata.get("parents", {}),
            },
        }

        self.collection.replace_one(
            {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
            doc,
            upsert=True,
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
                "checkpoint_ns": config.get("configurable", {}).get("checkpoint_ns", ""),
            }
        }

    def put_writes(
        self,
        config: dict[str, Any],
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Store pending writes (node outputs not yet committed)."""
        thread_id = self._thread_id(config)
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", "")

        doc = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "writes": self._serialize_writes(writes),
        }
        self.collection.update_one(
            {"thread_id": thread_id, "checkpoint_id": checkpoint_id},
            {"$push": {"pending_writes": doc}},
            upsert=True,
        )

    def list(
        self,
        config: dict[str, Any] | None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints for a thread, ordered newest first."""
        thread_id = self._thread_id(config) if config else None
        if not thread_id:
            return

        query: dict[str, Any] = {"thread_id": thread_id}
        if before:
            before_id = before.get("configurable", {}).get("checkpoint_id")
            if before_id:
                query["checkpoint_id"] = {"$lt": before_id}

        cursor = self.collection.find(query).sort("checkpoint_id", -1)
        if limit:
            cursor = cursor.limit(limit)

        for doc in cursor:
            checkpoint = self._doc_to_checkpoint(doc)
            metadata = self._doc_to_metadata(doc)
            parent_config = (
                {"configurable": {"thread_id": thread_id, "checkpoint_id": doc["parent_checkpoint_id"]}}
                if doc.get("parent_checkpoint_id")
                else None
            )
            yield CheckpointTuple(
                config={"configurable": {"thread_id": thread_id, "checkpoint_id": doc["checkpoint_id"]}},
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )

    # ── Helpers ──────────────────────────────────────────────────

    def _thread_id(self, config: dict[str, Any]) -> str:
        if not config:
            return ""
        return config.get("configurable", {}).get("thread_id", "")

    def _doc_to_checkpoint(self, doc: dict[str, Any]) -> Checkpoint:
        cp = doc.get("checkpoint", doc)
        return Checkpoint(
            v=cp.get("v", 1),
            id=cp.get("id", doc.get("checkpoint_id", "")),
            ts=cp.get("ts", ""),
            channel_values=cp.get("channel_values", {}),
            channel_versions=cp.get("channel_versions", {}),
            versions_seen=cp.get("versions_seen", {}),
        )

    def _doc_to_metadata(self, doc: dict[str, Any]) -> CheckpointMetadata:
        md = doc.get("metadata", {})
        return CheckpointMetadata(
            source=md.get("source", "loop"),
            step=md.get("step", -1),
            writes=md.get("writes", None),
            parents=md.get("parents", {}),
        )

    def _serialize_channels(self, channel_values: dict[str, Any]) -> dict[str, Any]:
        """Convert channel values to MongoDB-safe dicts.

        Phase0State extends MessagesState, so channels may include
        Message objects that need serialization.
        """
        result: dict[str, Any] = {}
        for key, value in channel_values.items():
            if key == "messages":
                result[key] = [
                    m.model_dump() if hasattr(m, "model_dump") else
                    (dict(m) if hasattr(m, "__dict__") else str(m))
                    for m in (value or [])
                ]
            elif isinstance(value, (list, tuple)):
                result[key] = list(value)
            elif isinstance(value, dict):
                result[key] = dict(value)
            else:
                result[key] = value
        return result

    def _serialize_writes(self, writes: list[tuple[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for channel, value in (writes or []):
            if hasattr(value, "model_dump"):
                result.append([channel, value.model_dump()])
            elif hasattr(value, "__dict__"):
                result.append([channel, dict(value)])
            else:
                result.append([channel, value])
        return result

    # ── Admin ────────────────────────────────────────────────────

    def delete_thread(self, thread_id: str) -> None:
        self.collection.delete_many({"thread_id": thread_id})

    def get_next_version(self, current: str | None, channel: str) -> str | None:
        """Generate next version for a channel. Simple counter."""
        if current is None:
            return "1"
        try:
            return str(int(current) + 1)
        except (ValueError, TypeError):
            return "1"
