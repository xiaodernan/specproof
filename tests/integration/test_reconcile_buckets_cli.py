"""The reconciler must be reachable by an OPERATOR, not only from Python.

``specproof ops reconcile-buckets`` is the surface a human actually uses.
This leg drives the real CLI group against a real (scratch) bucket and a real
SQLite index, and asserts that the command's own output names the ghost it
found — a command that renders but says nothing is a report nobody can act
on.

Which index the command reads is the point of two of these legs: the test
suite forces ``SPECPROOF_OBJECT_METADATA_BACKEND=memory`` so that no run
touches ``~/.specproof/*.sqlite3``. These legs therefore set that knob to
"" and point ``SPECPROOF_OBJECT_METADATA_DB`` at their own file — and one
leg proves the command really read it (a row that points at an object
which is not in the bucket can only be found by reading the index).

Isolation: the bucket is this file's own and is removed afterwards; the
index is a SQLite file under ``tmp_path``.
"""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import suppress
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli.specproof.commands.ops import ops_cmd
from storage.minio import MinIOClient
from storage.object_metadata import SQLiteObjectMetadataStore, new_metadata

BUCKET = "specproof-test-bucket-cli"


@pytest.fixture
def scratch_bucket() -> MinIOClient:
    client = MinIOClient()
    try:
        client.client.bucket_exists(BUCKET)
    except Exception as exc:  # noqa: BLE001 — any connection failure means "no MinIO here"
        pytest.skip(f"MinIO not available for the CLI leg: {exc}")
    with suppress(Exception):  # the bucket may already exist
        client.client.make_bucket(BUCKET)
    try:
        yield client
    finally:
        try:
            for obj in client.client.list_objects(BUCKET, recursive=True):
                client.client.remove_object(BUCKET, obj.object_name)
            client.client.remove_bucket(BUCKET)
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass


def _point_the_cli_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make the command read THIS file's index (not the in-memory default).

    The suite-wide fixture sets ``SPECPROOF_OBJECT_METADATA_BACKEND=memory``
    so that no test touches the developer's real index; this leg needs a
    real file, so it turns that knob off and names its own.
    """
    db_path = tmp_path / "objects.sqlite3"
    monkeypatch.setenv("SPECPROOF_OBJECT_METADATA_BACKEND", "")
    monkeypatch.setenv("SPECPROOF_OBJECT_METADATA_DB", str(db_path))
    return db_path


def _put(scratch_bucket: MinIOClient, name: str, data: bytes) -> None:
    scratch_bucket.client.put_object(
        bucket_name=BUCKET,
        object_name=name,
        data=io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
        metadata={"X-Amz-Meta-Sha256": hashlib.sha256(data).hexdigest()},
    )


def test_the_cli_names_the_ghost_it_found(
    scratch_bucket: MinIOClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _point_the_cli_at(tmp_path, monkeypatch)
    _put(scratch_bucket, "ghost/cli-visible.zip", b"cli-visible-ghost")

    result = CliRunner().invoke(
        ops_cmd,
        ["reconcile-buckets", "--bucket", BUCKET, "--json"],
    )

    assert result.exit_code == 0, f"the command failed: {result.output}"
    report = json.loads(result.output)
    assert report["is_clean"] is False
    kinds = {finding["kind"] for finding in report["findings"]}
    assert "unindexed" in kinds
    names = {finding["object_name"] for finding in report["findings"]}
    assert "ghost/cli-visible.zip" in names


def test_the_cli_really_reads_the_index_file_it_was_pointed_at(
    scratch_bucket: MinIOClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that points at nothing can only be found by reading the index.

    If the command silently used the in-memory default instead of the file
    this leg is pointed at, this finding would not appear — and the leg
    would be proving nothing about the index at all.
    """
    db_path = _point_the_cli_at(tmp_path, monkeypatch)
    store = SQLiteObjectMetadataStore(db_path)
    store.record(
        new_metadata(
            "capsule",  # type: ignore[arg-type]
            {"payload_sha256": "b" * 64},
            job_id="job-absent",
            path_hint=str(tmp_path / "absent.zip"),
            object_ref=f"{BUCKET}/capsule/absent.zip",
        )
    )

    result = CliRunner().invoke(
        ops_cmd,
        ["reconcile-buckets", "--bucket", BUCKET, "--json"],
    )

    assert result.exit_code == 0, f"the command failed: {result.output}"
    report = json.loads(result.output)
    kinds = {finding["kind"] for finding in report["findings"]}
    assert "missing" in kinds, (
        f"the index row was not found by the command — it did not read the "
        f"index file it was pointed at: {report['findings']!r}"
    )
    names = {finding["object_name"] for finding in report["findings"]}
    assert "capsule/absent.zip" in names


def test_the_cli_says_when_the_scan_could_not_read_the_whole_index(
    scratch_bucket: MinIOClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated scan must not be able to say "clean" in silence.

    The index on a real machine is bigger than a naive read limit; the
    command has to say so rather than let the operator read a prefix as
    the whole picture.
    """
    db_path = _point_the_cli_at(tmp_path, monkeypatch)
    store = SQLiteObjectMetadataStore(db_path)
    store.record(
        new_metadata(
            "capsule",  # type: ignore[arg-type]
            {"payload_sha256": "a" * 64},
            job_id="job-truncated",
            path_hint=str(tmp_path / "capsule.zip"),
            object_ref=f"{BUCKET}/capsule/truncated.zip",
        )
    )

    result = CliRunner().invoke(
        ops_cmd,
        ["reconcile-buckets", "--bucket", BUCKET, "--record-limit", "1", "--json"],
    )

    assert result.exit_code == 0, f"the command failed: {result.output}"
    report = json.loads(result.output)
    assert report["truncated"] is True, (
        "the command read the index up to its limit and did not say the "
        "scan was incomplete"
    )
