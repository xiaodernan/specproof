"""MySQL integration tests for storage.object_metadata — gated on MYSQL_URL.

Run with a real MySQL (matches the production backend):

    MYSQL_URL=mysql://user:pass@host:3306/specproof_phase0 \
        python -m pytest tests/integration/test_object_metadata_mysql.py

Without MYSQL_URL the whole module is skipped at collection — it never
fails and needs no Docker here. Each run cleans the object_metadata and
object_contracts tables (fresh uuid ids + truncation).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from storage.object_metadata import (
    MySQLObjectMetadataStore,
    ObjectAlreadyExistsError,
    new_metadata,
    resolve_object,
)

MYSQL_URL = os.getenv("MYSQL_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        MYSQL_URL is None,
        reason="MYSQL_URL not set — MySQL integration tests skipped",
    ),
]


def _test_database_url() -> str:
    """The SAME server, but the TEST schema — never the product one.

    The URL in the environment may name the product schema; writing
    integration rows into it would put test data where the product
    lives. The conftest already rewrites MYSQL_DATABASE to the test
    schema, so the credentials are taken from the same config and only
    the database is replaced.
    """
    from urllib.parse import quote

    from storage.mysql import MySQLConfig

    config = MySQLConfig.from_env()
    database = (
        os.getenv("SPECPROOF_TEST_MYSQL_DATABASE") or config.database
    )
    return (
        f"mysql://{quote(config.user)}:{quote(config.password)}"
        f"@{config.host}:{config.port}/{database}"
    )


def _clear(store: MySQLObjectMetadataStore) -> None:
    with store.connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM object_contracts")
        cur.execute("DELETE FROM object_metadata")


@pytest.fixture()
def store() -> Iterator[MySQLObjectMetadataStore]:
    backend = MySQLObjectMetadataStore(_test_database_url())
    backend.ensure_schema()
    _clear(backend)
    yield backend
    _clear(backend)


def test_record_and_query_round_trip(store: MySQLObjectMetadataStore) -> None:
    record = store.record(new_metadata(
        "capsule",
        {"payload_sha256": "a" * 64},
        job_id="it-job-1",
        contract_ids=("AUTH-01", "UNIQUE-01"),
        path_hint="capsules/capsule-F-1.zip",
    ))
    assert store.get(record.object_id) == record
    assert store.by_job("it-job-1") == [record]
    assert store.by_kind("capsule") == [record]
    assert store.by_digest("sha256:" + "a" * 64) == [record]
    assert store.by_contract("AUTH-01") == [record]
    assert store.by_contract("UNIQUE-01") == [record]
    assert store.by_contract("MISSING") == []


def test_duplicate_object_id_raises(store: MySQLObjectMetadataStore) -> None:
    record = store.record(new_metadata(
        "replay_report", {"payload_sha256": "b" * 64},
    ))
    with pytest.raises(ObjectAlreadyExistsError):
        store.record(record)


def test_resolve_object_via_metadata(store: MySQLObjectMetadataStore) -> None:
    record = store.record(new_metadata(
        "certificate",
        {"payload_sha256": "c" * 64},
        job_id="it-job-2",
        path_hint="reports/merge-certificate-it.json",
    ))
    assert resolve_object(store, record.object_id) == record
    assert resolve_object(store, "c" * 64) == record
    assert resolve_object(store, "reports/merge-certificate-it.json") == record
    assert resolve_object(store, "missing-path.json") is None


def test_ensure_schema_idempotent(store: MySQLObjectMetadataStore) -> None:
    store.ensure_schema()
    store.ensure_schema()
    record = store.record(new_metadata(
        "capsule", {"payload_sha256": "d" * 64},
    ))
    assert store.get(record.object_id) is not None


def test_the_object_reference_round_trips_and_resolves(
    store: MySQLObjectMetadataStore,
) -> None:
    """P1-7 on the production backend: the coordinate survives the row."""
    record = store.record(new_metadata(
        "capsule",
        {"payload_sha256": "e" * 64},
        job_id="it-job-3",
        path_hint="/tmp/capsule.zip",
        object_ref="specproof/jobs/it-job-3/capsule.zip",
    ))
    fetched = store.get(record.object_id)
    assert fetched is not None
    assert fetched.object_ref == "specproof/jobs/it-job-3/capsule.zip"
    assert resolve_object(store, "specproof/jobs/it-job-3/capsule.zip") == record


def test_ensure_schema_migrates_a_table_created_before_object_ref(
    store: MySQLObjectMetadataStore,
) -> None:
    """The migration on the production backend.

    A table created by an older build has no object_ref column; CREATE
    TABLE IF NOT EXISTS will not add it, and the first SELECT that names
    it fails with a column error that reads like corruption.
    """
    with store.connection() as conn:
        cur = conn.cursor()
        cur.execute("ALTER TABLE object_metadata DROP COLUMN object_ref")

    store.ensure_schema()

    record = store.record(new_metadata(
        "capsule",
        {"payload_sha256": "f" * 64},
        object_ref="specproof/jobs/it-job-4/capsule.zip",
    ))
    fetched = store.get(record.object_id)
    assert fetched is not None
    assert fetched.object_ref == "specproof/jobs/it-job-4/capsule.zip"
