"""Contract tests for the §3.4 event Envelope (guide: 事件 Envelope).

Covers the canonical envelope produced by contracts/events.py and the flat
wire form emitted by storage/outbox_relay.py: field completeness, digest
determinism, idempotency-key propagation, secret redaction, and tolerance
of unknown fields by legacy flat consumers.
"""

from __future__ import annotations

import json
import re
from typing import Any

from contracts.events import (
    DEFAULT_ACTOR_ID,
    DEFAULT_TENANT_ID,
    REDACTION_PLACEHOLDER,
    SCHEMA_VERSION,
    build_envelope,
    payload_digest,
)
from storage.outbox_relay import OutboxRelay

ENVELOPE_FIELDS = [
    "event_id",
    "event_type",
    "occurred_at",
    "tenant_id",
    "actor_id",
    "trace_id",
    "aggregate_type",
    "aggregate_id",
    "schema_version",
    "idempotency_key",
    "payload",
    "payload_digest",
]


def _job_payload() -> dict[str, Any]:
    return {
        "job_id": "job-1",
        "repo_path": "/repo",
        "base_ref": "main",
        "head_ref": "head-sha",
        "spec_path": "/spec.md",
        "depth": "FAST",
    }


def _relay_row() -> dict[str, Any]:
    return {
        "id": 7,
        "aggregate_id": "job-1",
        "event_type": "JobCreated",
        "routing_key": "q.p1.verify.job",
        "payload": json.dumps(_job_payload()),
    }


def test_envelope_has_all_guide_fields() -> None:
    env = build_envelope(
        event_type="JobCreated", aggregate_id="job-1", payload=_job_payload(),
    )
    assert set(ENVELOPE_FIELDS) <= set(env)
    assert env["schema_version"] == SCHEMA_VERSION == 1
    assert env["tenant_id"] == DEFAULT_TENANT_ID == "default"
    assert env["actor_id"] == DEFAULT_ACTOR_ID
    assert env["aggregate_type"] == "verification_job"
    assert env["aggregate_id"] == "job-1"
    assert env["event_type"] == "JobCreated"


def test_event_id_default_is_unique_uuid4_hex() -> None:
    first = build_envelope(
        event_type="JobCreated", aggregate_id="job-1", payload={},
    )
    second = build_envelope(
        event_type="JobCreated", aggregate_id="job-1", payload={},
    )
    assert re.fullmatch(r"[0-9a-f]{32}", first["event_id"])
    assert re.fullmatch(r"[0-9a-f]{32}", second["event_id"])
    assert first["event_id"] != second["event_id"]


def test_occurred_at_is_utc_zulu() -> None:
    env = build_envelope(
        event_type="JobCreated", aggregate_id="job-1", payload={},
    )
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", env["occurred_at"],
    )


def test_payload_digest_is_deterministic_and_sensitive() -> None:
    digest_a = payload_digest({"a": 1, "b": [1, 2]})
    digest_b = payload_digest({"b": [1, 2], "a": 1})  # key order irrelevant
    assert digest_a == digest_b
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest_a)
    assert payload_digest({"a": 1}) != payload_digest({"a": 2})


def test_envelope_digest_covers_the_embedded_payload() -> None:
    env = build_envelope(
        event_type="JobCreated", aggregate_id="job-1", payload=_job_payload(),
    )
    assert env["payload_digest"] == payload_digest(env["payload"])


def test_idempotency_key_passthrough() -> None:
    env = build_envelope(
        event_type="JobCreated",
        aggregate_id="job-1",
        payload=_job_payload(),
        idempotency_key="github:delivery:d-1",
    )
    assert env["idempotency_key"] == "github:delivery:d-1"


def test_no_plaintext_secrets_in_envelope() -> None:
    fake_key = "sk-live-not-a-real-key-12345"
    fake_pem = "-----BEGIN PRIVATE KEY-----fake-----END PRIVATE KEY-----"
    env = build_envelope(
        event_type="JobCreated",
        aggregate_id="job-1",
        payload={
            "job_id": "job-1",
            "api_key": fake_key,
            "nested": {"private_key": fake_pem, "notes": ["a", "b"]},
        },
    )
    wire = json.dumps(env, ensure_ascii=False)
    assert fake_key not in wire
    assert fake_pem not in wire
    assert env["payload"]["api_key"] == REDACTION_PLACEHOLDER
    assert env["payload"]["nested"]["private_key"] == REDACTION_PLACEHOLDER
    assert env["payload"]["nested"]["notes"] == ["a", "b"]  # untouched
    assert env["payload_digest"] == payload_digest(env["payload"])


def test_relay_flat_wire_keeps_legacy_fields_and_adds_envelope() -> None:
    flat = OutboxRelay()._flatten_envelope(_relay_row())
    # Legacy wire contract untouched: deterministic id, flat job fields…
    assert flat["event_id"] == "outbox-7"
    assert flat["outbox_id"] == 7
    assert flat["job_id"] == "job-1"
    assert flat["event_type"] == "JobCreated"
    assert flat["created_at"] is None
    assert flat["repo_path"] == "/repo"
    assert flat["base_ref"] == "main"
    assert flat["head_ref"] == "head-sha"
    assert flat["spec_path"] == "/spec.md"
    assert flat["depth"] == "FAST"
    assert "payload" not in flat
    # …plus the new §3.4 envelope fields, flat for old consumers to ignore.
    assert flat["schema_version"] == 1
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", flat["payload_digest"])
    assert flat["idempotency_key"] == "outbox:7"
    assert flat["tenant_id"] == "default"
    assert flat["aggregate_type"] == "verification_job"
    assert flat["aggregate_id"] == "job-1"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", flat["occurred_at"],
    )
    assert flat["event_type"] == "JobCreated"


def test_relay_wire_digest_matches_spread_payload() -> None:
    flat = OutboxRelay()._flatten_envelope(_relay_row())
    spread = {
        key: flat[key]
        for key in (
            "job_id", "repo_path", "base_ref", "head_ref", "spec_path", "depth",
        )
    }
    assert flat["payload_digest"] == payload_digest(spread)


def test_relay_redacts_secret_fields_on_the_wire() -> None:
    row = _relay_row()
    row["payload"] = json.dumps({**_job_payload(), "api_key": "sk-fake-999"})
    flat = OutboxRelay()._flatten_envelope(row)
    wire = json.dumps(flat, ensure_ascii=False)
    assert "sk-fake-999" not in wire
    assert flat["api_key"] == REDACTION_PLACEHOLDER


def test_relay_tolerates_corrupt_payload() -> None:
    row = _relay_row()
    row["payload"] = "{not-json"
    flat = OutboxRelay()._flatten_envelope(row)
    assert flat["job_id"] == "job-1"
    assert flat["event_id"] == "outbox-7"
    assert flat["schema_version"] == 1
    assert flat["payload_digest"] == payload_digest({})


def _legacy_consumer(raw: dict[str, Any]) -> dict[str, Any]:
    """Minimal flat reader like the worker: reads known keys, ignores rest."""
    return {
        key: raw.get(key)
        for key in (
            "job_id", "event_type", "repo_path", "base_ref",
            "head_ref", "spec_path", "depth",
        )
    }


def test_legacy_consumer_ignores_unknown_envelope_fields() -> None:
    flat = OutboxRelay()._flatten_envelope(_relay_row())
    consumed = _legacy_consumer(flat)
    assert consumed["job_id"] == "job-1"
    assert consumed["event_type"] == "JobCreated"
    assert consumed["repo_path"] == "/repo"
    assert consumed["depth"] == "FAST"
    # Unknown envelope fields are present on the wire and simply ignored.
    for extra in (
        "schema_version", "payload_digest", "idempotency_key",
        "occurred_at", "tenant_id", "actor_id", "trace_id",
    ):
        assert extra in flat
        assert extra not in consumed
