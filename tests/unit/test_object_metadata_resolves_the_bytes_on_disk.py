"""A path must resolve to the record that describes the bytes on disk.

The DEEP run of 2026-10-22 printed "WARNING: digest mismatch" for
capsule-COURT-UNIQUE-01.zip while the file was perfectly intact: the
store holds one record per run (the same path is written again every
time), the newest record spelled its path relatively and an older one
spelled it absolutely, and the lookup took the first spelling that
matched - an old record whose digest describes bytes that are long
gone. The tool cried wolf about a healthy artifact.

These tests pin the fix:

- a path spelled two ways resolves to the SAME file;
- the record that describes the bytes on disk wins;
- when NO recorded version matches the bytes, the newest record is
  returned, so the caller reports a TRUE mismatch (not a false one).

No Docker, no network: SQLite on a temp file.
"""

from __future__ import annotations

import hashlib

from storage.object_metadata import (
    SQLiteObjectMetadataStore,
    new_metadata,
    normalize_payload_digest,
    payload_sha256_of_file,
    resolve_object,
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(store, data: bytes, job_id: str, hint: str):
    """Record one version of a file (the digest is of the bytes)."""
    return store.record(new_metadata(
        "capsule",
        {"payload_sha256": _digest(data)},
        job_id=job_id,
        path_hint=hint,
    ))


def test_the_same_file_spelled_two_ways_is_one_file(tmp_path, monkeypatch):
    """Relative and absolute spellings name the same file."""
    monkeypatch.chdir(tmp_path)
    capsule = tmp_path / "capsules" / "capsule-X.zip"
    capsule.parent.mkdir(parents=True)
    capsule.write_bytes(b"v1")
    store = SQLiteObjectMetadataStore(tmp_path / "meta.sqlite3")
    # An older record spells the path absolutely, a newer one relative.
    _record(store, b"v1", "job-old", str(capsule))
    _record(store, b"v1", "job-new", "capsules/capsule-X.zip")

    from_absolute = resolve_object(store, str(capsule))
    from_relative = resolve_object(store, "capsules/capsule-X.zip")
    assert from_absolute is not None
    assert from_relative is not None
    # The bytes are the arbiter: both spellings land on the same
    # record, and it is the one that describes the bytes on disk.
    assert from_absolute.object_id == from_relative.object_id
    assert normalize_payload_digest(
        from_absolute.digests["payload_sha256"]
    ) == payload_sha256_of_file(capsule)


def test_the_record_for_the_bytes_on_disk_wins(tmp_path):
    """The path is written again every run; the current bytes decide.

    Both records spell the path the SAME way here - the lookup used
    to take the first match, which was the older one.
    """
    capsule = tmp_path / "capsules" / "capsule-Y.zip"
    capsule.parent.mkdir(parents=True)
    capsule.write_bytes(b"v1")
    store = SQLiteObjectMetadataStore(tmp_path / "meta.sqlite3")
    old = _record(store, b"v1", "job-old", str(capsule))
    # The next run rewrites the same path with new bytes.
    capsule.write_bytes(b"v2")
    new = _record(store, b"v2", "job-new", str(capsule))

    resolved = resolve_object(store, str(capsule))
    assert resolved is not None
    assert resolved.object_id == new.object_id
    assert resolved.object_id != old.object_id
    assert resolved.digests["payload_sha256"] == _digest(b"v2")


def test_bytes_that_match_no_record_give_the_newest_record(tmp_path):
    """A file that is NOT what we recorded must still be reported as a
    mismatch - the newest record, so the truth survives."""
    capsule = tmp_path / "capsules" / "capsule-Z.zip"
    capsule.parent.mkdir(parents=True)
    capsule.write_bytes(b"recorded")
    store = SQLiteObjectMetadataStore(tmp_path / "meta.sqlite3")
    _record(store, b"recorded", "job-old", str(capsule))
    # The file was replaced by something the tool never recorded.
    capsule.write_bytes(b"tampered")
    _record(store, b"other", "job-new", str(capsule))

    resolved = resolve_object(store, str(capsule))
    assert resolved is not None
    assert resolved.job_id == "job-new"
    # ... and the digest check must NOT call it a match.
    actual = payload_sha256_of_file(capsule)
    assert normalize_payload_digest(resolved.digests["payload_sha256"]) != actual
