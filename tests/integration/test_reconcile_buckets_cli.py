"""The reconciler must be reachable by an OPERATOR, not only from Python.

``specproof ops reconcile-buckets`` is the surface a human actually uses.
This leg drives the real CLI group against a real (scratch) bucket and a real
SQLite index, and asserts that the command's own output names the ghost it
found — a command that renders but says nothing is a report nobody can act
on.

Isolation: the bucket is this file's own and is removed afterwards; the
index is a SQLite file under ``tmp_path`` (the CLI reads it through
``SPECPROOF_OBJECT_METADATA_DB``, the same knob the product uses).
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


def test_the_cli_names_the_ghost_it_found(
    scratch_bucket: MinIOClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECPROOF_OBJECT_METADATA_DB", str(tmp_path / "objects.sqlite3"))
    data = b"cli-visible-ghost"
    scratch_bucket.client.put_object(
        bucket_name=BUCKET,
        object_name="ghost/cli-visible.zip",
        data=io.BytesIO(data),
        length=len(data),
        content_type="application/octet-stream",
        metadata={"X-Amz-Meta-Sha256": hashlib.sha256(data).hexdigest()},
    )

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
