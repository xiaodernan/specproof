"""End-to-end against a REAL object store: two moments, two real snapshots.

The unit tests use a double. This one talks to the actual S3 endpoint the
pipeline talks to (the compose service behind `specproof-minio`), because
the two things a double cannot show are:

- the object store really answers, and the production client really
  reaches it;
- a snapshot really changes when an object appears — and a missing
  object is really reported as ABSENT rather than as "present with an
  empty body".

The production client (`storage.minio.MinIOClient`) is the one used
here: a test that builds its own client would not be testing the path
the pipeline takes.

An object reference is ``bucket/object-name`` — the bucket is the FIRST
segment, so the test prefix lives INSIDE the object name.

Run it against the compose object store:

    docker compose -f compose.phase0.yml up -d minio
    python -m pytest tests/integration/test_external_state_against_real_object_store.py
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

from experiments.collectors import object_fragment_from_snapshots
from experiments.external_state import (
    build_object_store,
    capture_object_state,
    object_states_from_dicts,
)

BUCKET = "specproof-tool-reports"
PREFIX = "specproof-test/"
MINIO_HOST = os.getenv("MINIO_HOST", "localhost")
MINIO_PORT = os.getenv("MINIO_PORT", "9000")


def _ref(name: str) -> str:
    """The reference the collector speaks: bucket/object-name."""
    return f"{BUCKET}/{PREFIX}{name}"


@pytest.fixture()
def store() -> Any:
    client = build_object_store()
    if client is None:
        pytest.skip(
            f"no object store reachable at {MINIO_HOST}:{MINIO_PORT} — "
            "start it with: docker compose -f compose.phase0.yml up -d minio"
        )
    yield client
    try:
        for obj in client.client.list_objects(BUCKET, recursive=True):
            if obj.object_name.startswith(PREFIX):
                client.client.remove_object(BUCKET, obj.object_name)
    except Exception:  # noqa: BLE001 — cleanup is best effort
        pass


def _put(client: Any, name: str, data: bytes) -> None:
    """Upload through the PRODUCTION API (digest-bearing)."""
    client.put_object_with_digest(
        BUCKET, f"{PREFIX}{name}", data,
        content_type="application/octet-stream",
    )


def test_the_client_really_connects(store: Any) -> None:
    assert store.is_ready() is True
    assert BUCKET in [b.name for b in store.client.list_buckets()]


def test_two_real_moments_show_a_real_difference(store: Any) -> None:
    """An object uploaded between the two moments is visible as a change."""
    name = f"two-moments-{uuid.uuid4().hex}.bin"
    ref = _ref(name)

    # Moment 1: the object does not exist.
    first = capture_object_state(store, [ref])
    assert first[ref]["present"] is False
    assert first[ref]["size_bytes"] == 0

    # The world changes.
    _put(store, name, b"capsule-bytes")

    # Moment 2: it does.
    second = capture_object_state(store, [ref])
    assert second[ref]["present"] is True
    assert second[ref]["size_bytes"] == len(b"capsule-bytes")

    fragment = object_fragment_from_snapshots(
        "job-real-object-store",
        object_states_from_dicts({"objects": first}),
        object_states_from_dicts({"objects": second}),
    )
    assert fragment.comparison["changed_count"] == 1
    assert fragment.comparison["changed"][0]["change"] == "appeared"
    assert fragment.status == "AMBIGUOUS"


def test_a_missing_object_is_absent_not_empty(store: Any) -> None:
    """A missing object is ABSENT — never "present with an empty body"."""
    ref = _ref(f"absent-{uuid.uuid4().hex}.bin")
    snapshot = capture_object_state(store, [ref])
    state = snapshot[ref]
    assert state["present"] is False
    assert state["size_bytes"] == 0
    assert state["content_type"] == ""


def test_an_empty_object_is_present(store: Any) -> None:
    """A zero-byte object EXISTS.

    Reporting it as absent would be a lie: the object is there, and
    "present and empty" is a different fact from "not there".
    """
    name = f"empty-{uuid.uuid4().hex}.bin"
    _put(store, name, b"")
    try:
        snapshot = capture_object_state(store, [_ref(name)])
        state = snapshot[_ref(name)]
        assert state["present"] is True
        assert state["size_bytes"] == 0
    finally:
        store.remove_object(BUCKET, f"{PREFIX}{name}")


def test_two_identical_moments_really_do_say_nothing_changed(store: Any) -> None:
    """The unchanged case is measured too — not only the interesting one."""
    name = f"same-{uuid.uuid4().hex}.bin"
    _put(store, name, b"same")
    try:
        first = capture_object_state(store, [_ref(name)])
        second = capture_object_state(store, [_ref(name)])
        fragment = object_fragment_from_snapshots(
            "job-real-object-store",
            object_states_from_dicts({"objects": first}),
            object_states_from_dicts({"objects": second}),
        )
        assert fragment.comparison["changed_count"] == 0
        assert fragment.status == "COMPLIANT"
    finally:
        store.remove_object(BUCKET, f"{PREFIX}{name}")
