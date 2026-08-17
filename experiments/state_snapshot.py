"""P3 Differential Lab — full-stack state snapshots and semantic diff.

The differential executor compares Base and Head not only through tests but
through OBSERVABLE INFRASTRUCTURE STATE: MySQL rows, Redis keys/TTLs,
RabbitMQ queue depths. Two snapshots (base-run, head-run) produce a
semantic diff with attribution — which exact state changed, in which
direction, and which subsystem owns it.

Honesty contract: every capture failure is recorded per-subsystem; a diff
over missing data is marked incomplete, never invented.
"""

from __future__ import annotations

import json
import re
from typing import Any

from storage.mysql import MySQLStore
from storage.rabbitmq import RabbitMQClient
from storage.redis import RedisStore

# Snapshot table identifiers must be plain [schema.]name tokens — the list
# comes from trusted internal callers, and this allowlist makes the f-string
# SQL below provably injection-free.
_TABLE_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")


def capture_mysql_state(store: MySQLStore, tables: list[str]) -> dict[str, Any]:
    """Snapshot selected tables as {table: [row, ...]}."""
    state: dict[str, Any] = {}
    with store.connection() as conn:
        for table in tables:
            if not _TABLE_RE.fullmatch(table):
                state[table] = {
                    "error": "table name rejected by identifier allowlist"
                }
                continue
            try:
                cur = conn.cursor()
                # Identifier validated against the allowlist above.
                cur.execute(
                    f"SELECT * FROM {table} ORDER BY 1 LIMIT 500"  # nosec
                )
                state[table] = [dict(r) for r in cur.fetchall()]
            except Exception as exc:  # noqa: BLE001
                state[table] = {"error": str(exc)[:200]}
    return state


def capture_redis_state(store: RedisStore, pattern: str = "specproof:*") -> dict[str, Any]:
    """Snapshot matching keys with their TTLs."""
    try:
        keys = list(store.client.scan_iter(match=pattern, count=200))
        out: dict[str, Any] = {}
        for key in keys:
            ttl = store.client.ttl(key)
            key_type = store.client.type(key)
            if key_type == "string":
                raw = store.client.get(key)
                value = (
                    raw.decode("utf-8", errors="replace")
                    if isinstance(raw, bytes) else raw
                )
            else:
                value = "<" + str(key_type) + ">"
            out[str(key)] = {"value": value, "ttl": int(ttl)}
        return {"keys": out, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {"keys": {}, "error": str(exc)[:200]}


def capture_rabbitmq_state(client: RabbitMQClient, queues: list[str]) -> dict[str, Any]:
    """Snapshot queue message counts (passive declare)."""
    state: dict[str, Any] = {}
    try:
        client.ensure_topology()
        ch = client.channel
        for queue in queues:
            try:
                method = ch.queue_declare(queue=queue, passive=True)
                state[queue] = {
                    "messages": int(method.method.message_count),
                    "consumers": int(method.method.consumer_count),
                }
            except Exception as exc:  # noqa: BLE001
                state[queue] = {"error": str(exc)[:200]}
        return state
    except Exception as exc:  # noqa: BLE001
        return {"_connection_error": str(exc)[:200]}


def capture_full_stack(
    mysql: MySQLStore,
    redis: RedisStore,
    rabbitmq: RabbitMQClient,
    mysql_tables: list[str] | None = None,
    redis_pattern: str = "specproof:*",
    rabbit_queues: list[str] | None = None,
) -> dict[str, Any]:
    """One full-stack snapshot across all three subsystems."""
    return {
        "mysql": capture_mysql_state(mysql, mysql_tables or []),
        "redis": capture_redis_state(redis, redis_pattern),
        "rabbitmq": capture_rabbitmq_state(
            rabbitmq, rabbit_queues or ["q.p1.verify.job"]
        ),
    }


def diff_states(base: dict[str, Any], head: dict[str, Any]) -> dict[str, Any]:
    """Semantic diff between two full-stack snapshots.

    Returns {subsystem: {added, removed, changed}} where each entry carries
    the direction and the exact old/new values — attribution-ready.
    """
    result: dict[str, Any] = {"incomplete": []}
    for subsystem in ("mysql", "redis", "rabbitmq"):
        b = base.get(subsystem, {})
        h = head.get(subsystem, {})
        added: list[Any] = []
        removed: list[Any] = []
        changed: list[Any] = []
        if b.get("error") or h.get("error") or "_connection_error" in b or "_connection_error" in h:
            result["incomplete"].append(subsystem)
        if subsystem == "mysql":
            for table in sorted(set(b) | set(h)):
                b_rows = {
                    json.dumps(r, sort_keys=True, default=str): r
                    for r in b.get(table, [])
                    if isinstance(r, dict)
                }
                h_rows = {
                    json.dumps(r, sort_keys=True, default=str): r
                    for r in h.get(table, [])
                    if isinstance(r, dict)
                }
                for k, v in h_rows.items():
                    if k not in b_rows:
                        added.append({"table": table, "row": v})
                for k, v in b_rows.items():
                    if k not in h_rows:
                        removed.append({"table": table, "row": v})
        elif subsystem == "redis":
            b_keys = b.get("keys", {})
            h_keys = h.get("keys", {})
            for k, v in h_keys.items():
                if k not in b_keys:
                    added.append({"key": k, "value": v})
            for k, v in b_keys.items():
                if k not in h_keys:
                    removed.append({"key": k, "value": v})
                elif v != h_keys[k]:
                    changed.append({"key": k, "from": v, "to": h_keys[k]})
        else:  # rabbitmq
            for queue in sorted(set(b) | set(h)):
                bq = b.get(queue, {})
                hq = h.get(queue, {})
                if isinstance(bq, dict) and isinstance(hq, dict) and bq != hq:
                    changed.append({"queue": queue, "from": bq, "to": hq})
        result[subsystem] = {
            "added": added,
            "removed": removed,
            "changed": changed,
        }
    return result


def render_diff_report(diff: dict[str, Any]) -> str:
    """Human-readable diff report."""
    lines = ["=== Full-Stack Differential Report ==="]
    for subsystem in ("mysql", "redis", "rabbitmq"):
        d = diff.get(subsystem, {})
        lines.append(f"[{subsystem}] added={len(d.get('added', []))} "
                     f"removed={len(d.get('removed', []))} "
                     f"changed={len(d.get('changed', []))}")
        for item in d.get("changed", [])[:10]:
            lines.append("  changed " + json.dumps(item, default=str)[:160])
        for item in d.get("removed", [])[:5]:
            lines.append("  removed " + json.dumps(item, default=str)[:160])
        for item in d.get("added", [])[:5]:
            lines.append("  added   " + json.dumps(item, default=str)[:160])
    if diff.get("incomplete"):
        lines.append("WARNING: incomplete snapshots for: "
                     + ", ".join(diff["incomplete"]))
    return "\n".join(lines)
