"""#514 — the two copy families the near-clone lens found that nothing pinned.

The ratchet counts copies; a count does not stop one copy from drifting. The
house precedent is #493's `test_capsule_and_report_paths_agree.py`: where the
merge needs an owner decision first, pin the **contract** instead, so editing one
copy fails a test rather than changing one layer's output in silence.

Two families qualified, both chosen by measurement rather than taste:

* `evidence/_now_iso` — three byte-identical copies of the UTC timestamp that is
  written into `collected_at` and `finished_at`. `grep` over `tests/` found
  **zero** references to `_now_iso` and zero assertions on `collected_at`.
* `sha256_hex` — three copies across `craft`, `sandbox` and `storage`. The tests
  import **one** of them (`sandbox.cache_verify`), so the other two can change
  the digest of the same bytes and nothing goes red. That is an integrity
  question for a verification platform: the same artifact would carry two
  identities depending on which layer hashed it.

`_env_int` was measured too and is deliberately **not** repeated here — it is
already pinned by `test_env_int_readers_policy_table.py`.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from craft.schemas import sha256_hex as craft_sha256_hex
from evidence.batch_replay import _now_iso as batch_replay_now
from evidence.fragments import _now_iso as fragments_now
from evidence.offline_verify import _now_iso as offline_verify_now
from sandbox.cache_verify import sha256_hex as cache_verify_sha256_hex
from storage.object_metadata import sha256_hex as storage_sha256_hex

TIMESTAMP_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

TIMESTAMP_READERS: dict[str, Callable[[], str]] = {
    "batch_replay": batch_replay_now,
    "fragments": fragments_now,
    "offline_verify": offline_verify_now,
}

DIGEST_READERS: dict[str, Callable[[bytes], str]] = {
    "craft.schemas": craft_sha256_hex,
    "sandbox.cache_verify": cache_verify_sha256_hex,
    "storage.object_metadata": storage_sha256_hex,
}


@pytest.mark.parametrize("reader", sorted(TIMESTAMP_READERS))
def test_every_timestamp_copy_writes_utc_with_milliseconds_and_z(reader: str) -> None:
    """`...T..:..:..mmmZ` — the form `fromisoformat` round-trips as UTC.

    The `.replace("+00:00", "Z")` is not decoration: a `+00:00` tail and a `Z`
    tail compare unequal as strings, and evidence rows are compared as strings.
    """
    value = TIMESTAMP_READERS[reader]()
    assert TIMESTAMP_FORMAT.match(value), f"{reader} wrote {value!r}"
    assert datetime.fromisoformat(value).tzinfo is UTC


def test_the_three_timestamp_copies_are_the_same_instant() -> None:
    """One moment, three readers, no clock skew between evidence writers."""
    values = {name: reader() for name, reader in TIMESTAMP_READERS.items()}
    moments = {name: datetime.fromisoformat(value) for name, value in values.items()}
    spread = max(moments.values()) - min(moments.values())
    assert spread.total_seconds() < 1.0, values


@pytest.mark.parametrize("value", ["2026-10-28T09:00:00+00:00", "2026-10-28T09:00:00Z"])
def test_a_drifted_timestamp_fails_the_shape_rule(value: str) -> None:
    """Reverse control: the shape test must reject the two drifts it exists for.

    `+00:00` is what `isoformat()` returns before the `.replace`, and dropping
    `timespec="milliseconds"` is what a copy looks like after someone tidies it
    up. Both parse fine — which is exactly why agreement needs a shape, not a
    parse.
    """
    assert not TIMESTAMP_FORMAT.match(value)


@pytest.mark.parametrize("payload", [b"", b"a", "校验".encode(), bytes(range(256))])
def test_every_digest_copy_returns_the_same_hex_for_the_same_bytes(payload: bytes) -> None:
    """One artifact, one identity — whichever layer hashed it.

    `sha256_hex` exists in `craft`, `sandbox` and `storage`. The manifest that
    cache verification reads is built by one of them and compared against a value
    produced by another, so two formats for the same bytes do not fail loudly:
    they fail as "the artifact does not match its digest".
    """
    expected = hashlib.sha256(payload).hexdigest()
    got = {name: reader(payload) for name, reader in DIGEST_READERS.items()}
    assert got == dict.fromkeys(got, expected), got


@pytest.mark.parametrize("reader", sorted(DIGEST_READERS))
def test_the_digest_stays_plain_lowercase_hex_without_a_prefix(reader: str) -> None:
    """The contract is the *shape*, not just the algorithm.

    `sha256:` / uppercase / base64 are all reasonable edits to a digest helper and
    each one silently splits artifact identity in two.
    """
    assert re.fullmatch(r"[0-9a-f]{64}", DIGEST_READERS[reader](b"specproof"))


def test_the_digest_copies_agree_on_a_value_no_copy_hardcoded() -> None:
    """A copy that returns a constant to make the agreement test pass still fails."""
    payload = b"evidence capsule bytes"
    values = {name: reader(payload) for name, reader in DIGEST_READERS.items()}
    assert len(set(values.values())) == 1, values
    assert next(iter(values.values())) == hashlib.sha256(payload).hexdigest()
