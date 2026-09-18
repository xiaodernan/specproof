"""Durable console metadata, approval history, and bounded event journal.

SQLite follows the agent-job database by default; MySQL uses the same URL.
Every event sequence is allocated transactionally, including across processes.
Only a bounded recent event window is retained; approval and diff evidence are
stored independently so pruning verbose model output cannot erase decisions.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from storage.agent_jobs import MySqlAgentJobStore
from storage.tenant_scope import current_scope

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS agent_console_meta (
        job_id VARCHAR(255) PRIMARY KEY, repo_path TEXT NOT NULL,
        task_name TEXT NOT NULL, tenant_id VARCHAR(255), last_seq BIGINT NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS agent_console_events (
        job_id VARCHAR(255) NOT NULL, seq BIGINT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (job_id, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_console_approvals (
        id VARCHAR(255) PRIMARY KEY, job_id VARCHAR(255) NOT NULL,
        created_at VARCHAR(64) NOT NULL, payload TEXT NOT NULL,
        UNIQUE(job_id, created_at, id)
    )""",
    """CREATE TABLE IF NOT EXISTS agent_console_bundles (
        job_id VARCHAR(255) PRIMARY KEY, payload TEXT NOT NULL
    )""",
)


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ConsoleState:
    """Small SQL journal with identical memory/SQLite/MySQL semantics."""

    def __init__(self, url: str = "", *, max_events: int = 20_000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self.max_events = max_events
        self._lock = threading.RLock()
        self._mysql: MySqlAgentJobStore | None = None
        self._sqlite: sqlite3.Connection | None = None
        if url.startswith(("mysql://", "mysql+pymysql://")):
            self._mysql = MySqlAgentJobStore(url)
        else:
            if url and not url.startswith("sqlite:"):
                raise ValueError("Console storage requires sqlite:<path> or mysql:// URL")
            path = url.removeprefix("sqlite:") if url else ":memory:"
            if path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._sqlite = sqlite3.connect(path, timeout=30, check_same_thread=False)
            self._sqlite.row_factory = sqlite3.Row
            self._sqlite.execute("PRAGMA busy_timeout=30000")
            if path != ":memory:":
                self._sqlite.execute("PRAGMA journal_mode=WAL")
        with self._transaction() as cur:
            for statement in _SCHEMA:
                # Large edit snapshots exceed MySQL TEXT's 64 KiB ceiling.
                sql = (
                    statement.replace("payload TEXT", "payload LONGTEXT")
                    if self._mysql
                    else statement
                )
                cur.execute(sql)
            if not self._mysql:
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_console_approval_job "
                    "ON agent_console_approvals(job_id, created_at, id)"
                )

    @contextmanager
    def _transaction(self, *, write: bool = True) -> Iterator[Any]:
        with self._lock:
            if self._mysql is not None:
                with self._mysql.connection() as conn, conn.cursor() as cur:
                    yield cur
                return
            assert self._sqlite is not None
            cur = self._sqlite.cursor()
            try:
                if write:
                    cur.execute("BEGIN IMMEDIATE")
                yield cur
                self._sqlite.commit()
            except Exception:
                self._sqlite.rollback()
                raise
            finally:
                cur.close()

    def _execute(self, cur: Any, statement: str, values: tuple[Any, ...] = ()) -> Any:
        cur.execute(statement.replace("?", "%s") if self._mysql else statement, values)
        return cur

    def close(self) -> None:
        with self._lock:
            if self._sqlite is not None:
                self._sqlite.close()

    def _ensure_meta(self, cur: Any, job_id: str) -> None:
        statement = (
            "INSERT IGNORE INTO agent_console_meta(job_id, repo_path, task_name) VALUES (?, ?, ?)"
            if self._mysql
            else "INSERT OR IGNORE INTO agent_console_meta(job_id, repo_path, task_name) "
            "VALUES (?, ?, ?)"
        )
        self._execute(cur, statement, (job_id, "", job_id))

    def set_meta(self, job_id: str, repo_path: str, task_name: str | None) -> None:
        with self._transaction() as cur:
            self._ensure_meta(cur, job_id)
            self._execute(
                cur,
                "UPDATE agent_console_meta SET repo_path=?, task_name=? WHERE job_id=?",
                (repo_path, task_name or f"agent-{job_id[:8]}", job_id),
            )

    def set_owner(self, job_id: str, tenant_id: str | None) -> None:
        with self._transaction() as cur:
            self._ensure_meta(cur, job_id)
            self._execute(
                cur,
                "UPDATE agent_console_meta SET tenant_id=? WHERE job_id=? AND tenant_id IS NULL",
                (tenant_id, job_id),
            )

    def visible(self, job_id: str) -> bool:
        scope = current_scope()
        if scope is None or scope.is_auditor():
            return True
        with self._transaction(write=False) as cur:
            row = self._execute(
                cur, "SELECT tenant_id FROM agent_console_meta WHERE job_id=?", (job_id,)
            ).fetchone()
        # Unowned legacy console jobs are not shared across tenant boundaries.
        return row is not None and row["tenant_id"] == scope.tenant_id

    def summaries_for(self, job_ids: list[str]) -> dict[str, dict[str, Any]]:
        """One indexed read for a whole API page, including ownership and counts."""
        if not job_ids:
            return {}
        placeholders = ",".join("?" for _ in job_ids)
        statement = (
            "SELECT m.job_id, m.repo_path, m.task_name, m.tenant_id, m.last_seq, "
            "(SELECT COUNT(*) FROM agent_console_approvals a WHERE a.job_id=m.job_id) "
            "AS approvals_count FROM agent_console_meta m WHERE m.job_id IN ("
            + placeholders + ")"
        )
        with self._transaction(write=False) as cur:
            rows = self._execute(cur, statement, tuple(job_ids)).fetchall()
        return {str(row["job_id"]): dict(row) for row in rows}

    def meta_for(self, job_id: str) -> dict[str, str]:
        with self._transaction(write=False) as cur:
            row = self._execute(
                cur, "SELECT repo_path, task_name FROM agent_console_meta WHERE job_id=?", (job_id,)
            ).fetchone()
        return dict(row) if row else {"repo_path": "", "task_name": job_id}

    def _append(self, cur: Any, job_id: str, etype: str, data: dict[str, Any]) -> dict[str, Any]:
        self._ensure_meta(cur, job_id)
        self._execute(
            cur, "UPDATE agent_console_meta SET last_seq=last_seq+1 WHERE job_id=?", (job_id,)
        )
        seq = int(
            self._execute(
                cur, "SELECT last_seq FROM agent_console_meta WHERE job_id=?", (job_id,)
            ).fetchone()["last_seq"]
        )
        event = {"seq": seq, "type": etype, "at": datetime.now(UTC).isoformat(), "data": data}
        self._execute(
            cur,
            "INSERT INTO agent_console_events(job_id, seq, payload) VALUES (?, ?, ?)",
            (job_id, seq, _encode(event)),
        )
        if seq > self.max_events:
            self._execute(
                cur,
                "DELETE FROM agent_console_events WHERE job_id=? AND seq<=?",
                (job_id, seq - self.max_events),
            )
        return copy.deepcopy(event)

    def record_event(self, job_id: str, etype: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._transaction() as cur:
            return self._append(cur, job_id, etype, data)

    def events_since(self, job_id: str, after_seq: int, limit: int = 500) -> list[dict[str, Any]]:
        with self._transaction(write=False) as cur:
            rows = self._execute(
                cur,
                "SELECT payload FROM agent_console_events "
                "WHERE job_id=? AND seq>? ORDER BY seq LIMIT ?",
                (job_id, max(0, after_seq), max(1, min(limit, 1000))),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def events_count(self, job_id: str) -> int:
        with self._transaction(write=False) as cur:
            row = self._execute(
                cur, "SELECT last_seq FROM agent_console_meta WHERE job_id=?", (job_id,)
            ).fetchone()
        return int(row["last_seq"]) if row else 0

    def record_approval(
        self,
        job_id: str,
        target: str,
        decision: str,
        note: str | None,
        step_index: int | None,
        actor: str = "console",
    ) -> dict[str, Any]:
        approval = {
            "id": str(uuid.uuid4()),
            "job_id": job_id,
            "target": target,
            "step_index": step_index,
            "decision": decision,
            "note": note,
            "actor": actor,
            "created_at": datetime.now(UTC).isoformat(),
        }
        with self._transaction() as cur:
            self._execute(
                cur,
                "INSERT INTO agent_console_approvals(id, job_id, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (approval["id"], job_id, approval["created_at"], _encode(approval)),
            )
            self._append(cur, job_id, "gate", {"approval": approval})
        return copy.deepcopy(approval)

    def approvals_for(self, job_id: str) -> list[dict[str, Any]]:
        with self._transaction(write=False) as cur:
            rows = self._execute(
                cur,
                "SELECT payload FROM agent_console_approvals "
                "WHERE job_id=? ORDER BY created_at, id",
                (job_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def approvals_count(self, job_id: str) -> int:
        with self._transaction(write=False) as cur:
            row = self._execute(
                cur, "SELECT COUNT(*) AS n FROM agent_console_approvals WHERE job_id=?", (job_id,)
            ).fetchone()
        return int(row["n"])

    def set_bundle(self, job_id: str, files: list[dict[str, Any]]) -> None:
        with self._transaction() as cur:
            self._execute(cur, "DELETE FROM agent_console_bundles WHERE job_id=?", (job_id,))
            self._execute(
                cur,
                "INSERT INTO agent_console_bundles(job_id, payload) VALUES (?, ?)",
                (job_id, _encode(files)),
            )
            self._append(cur, job_id, "edit", {"bundle": {"files_changed": len(files)}})

    def bundle_for(self, job_id: str) -> list[dict[str, Any]]:
        with self._transaction(write=False) as cur:
            row = self._execute(
                cur, "SELECT payload FROM agent_console_bundles WHERE job_id=?", (job_id,)
            ).fetchone()
        return json.loads(row["payload"]) if row else []
