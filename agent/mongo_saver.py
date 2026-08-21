"""MongoDB-backed LangGraph checkpoint saver (P1.6).

Implements BaseCheckpointSaver so the compiled graph persists state
after every node execution. Worker crash recovery reads the latest
checkpoint and resumes from the interrupted node.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from storage.mongodb import MongoDBStore

logger = logging.getLogger(__name__)


class MongoDBSaver(BaseCheckpointSaver[Any]):
    """Persist LangGraph checkpoints to MongoDB.

    Each checkpoint is stored as a document in the `agent_checkpoints` collection.
    Checkpoint lookup is keyed by `thread_id` (which is the job_id).
    """

    def __init__(self, store: MongoDBStore | None = None) -> None:
        super().__init__(serde=JsonPlusSerializer())
        self._store = store or MongoDBStore()
        self._store.ensure_collections()

    @property
    def collection(self) -> Any:
        return self._store.db.agent_checkpoints

    @property
    def writes_collection(self) -> Any:
        """Pending-writes collection (auto-created by pymongo on first write)."""
        return self._store.db.checkpoint_writes

    # ── Core interface ──────────────────────────────────────────

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Get one checkpoint for a thread_id (job_id).

        Honors an explicit checkpoint_id: LangGraph's resume loop asks for
        specific checkpoint ids to read their pending writes, and a lookup
        that always returns the latest document would hide every pending
        task (observed live: a worker-kill resume replayed the run from the
        input instead of continuing from the last checkpoint).
        """
        thread_id = self._thread_id(config)
        if not thread_id:
            return None

        query: dict[str, Any] = {"thread_id": thread_id}
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if checkpoint_id:
            query["checkpoint_id"] = checkpoint_id
        doc = self.collection.find_one(query)
        if not doc:
            return None

        checkpoint = self._doc_to_checkpoint(doc)
        metadata = self._doc_to_metadata(doc)
        parent_config: Any = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": doc["parent_checkpoint_id"],
                }
            }
            if doc.get("parent_checkpoint_id")
            else None
        )
        pending_writes = self._load_pending_writes(
            thread_id,
            str(doc.get("checkpoint_ns") or ""),
            str(doc.get("checkpoint_id") or ""),
        )
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": doc["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
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
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store pending writes (node outputs not yet committed).

        LangGraph persists the task list BEFORE the superstep executes, so a
        hard kill mid-superstep leaves these writes behind and resume
        replays exactly that superstep. They live in their own collection
        keyed by (thread_id, checkpoint_ns, checkpoint_id, task_id) — the
        checkpoint document itself must stay immutable once written.
        """
        thread_id = self._thread_id(config)
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id", "")
        checkpoint_ns = config.get("configurable", {}).get("checkpoint_ns", "")

        doc = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "task_path": task_path,
            "writes": self._serialize_writes(writes),
        }
        self.writes_collection.replace_one(
            {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
            },
            doc,
            upsert=True,
        )

    def _load_pending_writes(
        self, thread_id: str, checkpoint_ns: str, checkpoint_id: str,
    ) -> list[tuple[str, str, Any]] | None:
        """Pending task writes for one checkpoint (None when there are none).

        The wire shape LangGraph resumes from is (task_id, channel, value)
        triples — the same shape MemorySaver produces.
        """
        docs = self.writes_collection.find(
            {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            },
        ).sort("task_id", 1)
        writes: list[tuple[str, str, Any]] = []
        for wdoc in docs:
            task_id = str(wdoc.get("task_id") or "")
            for channel, value in wdoc.get("writes") or []:
                writes.append((task_id, channel, value))
        return writes or None

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
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
            parent_config: Any = (
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": doc["parent_checkpoint_id"],
                    }
                }
                if doc.get("parent_checkpoint_id")
                else None
            )
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": doc["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )

    # ── Helpers ──────────────────────────────────────────────────

    def _thread_id(self, config: RunnableConfig) -> str:
        if not config:
            return ""
        return str(config.get("configurable", {}).get("thread_id", ""))

    # Upstream Checkpoint TypedDict shape drifts between langgraph releases;
    # we rebuild it from a stored document, so the reconstructed dict is Any.
    def _doc_to_checkpoint(self, doc: dict[str, Any]) -> Any:
        cp = doc.get("checkpoint", doc)
        return cast(Any, {
            "v": cp.get("v", 1),
            "id": cp.get("id", doc.get("checkpoint_id", "")),
            "ts": cp.get("ts", ""),
            "channel_values": cp.get("channel_values", {}),
            "channel_versions": cp.get("channel_versions", {}),
            "versions_seen": cp.get("versions_seen", {}),
        })

    # CheckpointMetadata keys also drift upstream (e.g. "writes").
    def _doc_to_metadata(self, doc: dict[str, Any]) -> Any:
        md = doc.get("metadata", {})
        return cast(Any, {
            "source": md.get("source", "loop"),
            "step": md.get("step", -1),
            "writes": md.get("writes", None),
            "parents": md.get("parents", {}),
        })

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

    def _serialize_writes(self, writes: Sequence[tuple[str, Any]]) -> Any:
        result: list[Any] = []
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
        self.writes_collection.delete_many({"thread_id": thread_id})

    def get_next_version(
        self, current: str | None, channel: None = None
    ) -> str | None:
        """Generate next version for a channel. Simple counter."""
        if current is None:
            return "1"
        try:
            return str(int(current) + 1)
        except (ValueError, TypeError):
            return "1"
