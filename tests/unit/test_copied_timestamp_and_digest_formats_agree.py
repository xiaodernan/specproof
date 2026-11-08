"""#514 — the two copy families the near-clone lens found that nothing pinned.

The ratchet counts copies; a count does not stop one copy from drifting. The
house precedent is #493's `test_capsule_and_report_paths_agree.py`: where the
merge needs an owner decision first, pin the **contract** instead, so editing one
copy fails a test rather than changing one layer's output in silence.

Two families qualified, both chosen by measurement rather than taste:

* `sha256_hex` — three copies across `craft`, `sandbox` and `storage`. The tests
  import **one** of them (`sandbox.cache_verify`), so the other two can change
  the digest of the same bytes and nothing goes red. That is an integrity
  question for a verification platform: the same artifact would carry two
  identities depending on which layer hashed it. **Still three copies**, so the
  agreement legs below are what keep them honest.
* `_now_iso` — #514 pinned three byte-identical copies in `evidence/`; #516
  measured the real population as **five** (a fourth in `contracts/events.py`,
  invisible because the ratchet's package census omitted `contracts`, and a fifth
  in `experiments/collectors.py`, invisible because its lazy `from datetime
  import` changes its AST while leaving its output identical) and merged all five
  into `contracts.clock.utc_now_iso`. The timestamp legs below therefore pin the
  **single producer**, the modules that delegate to it, and the format on the
  fields clients read — a count of copies is no longer the interesting claim.

`_env_int` was measured too and is deliberately **not** repeated here — it is
already pinned by `test_env_int_readers_policy_table.py`.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contracts.clock import utc_now_iso
from contracts.events import build_envelope
from craft.schemas import sha256_hex as craft_sha256_hex
from evidence.batch_replay import BatchReplayRecord
from evidence.offline_verify import VerificationReport
from sandbox.cache_verify import sha256_hex as cache_verify_sha256_hex
from storage.object_metadata import sha256_hex as storage_sha256_hex
from tests.unit.test_structural_clone_ratchet import PACKAGES

REPO = Path(__file__).resolve().parents[2]

#: The shipped modules that must go through the one producer. #516 measured them
#: as the copies; they are now the consumers, and this list is the census.
TIMESTAMP_CONSUMERS = (
    "contracts/events.py",
    "evidence/batch_replay.py",
    "evidence/fragments.py",
    "evidence/offline_verify.py",
    "experiments/collectors.py",
)

TIMESTAMP_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

DIGEST_READERS: dict[str, Callable[[bytes], str]] = {
    "craft.schemas": craft_sha256_hex,
    "sandbox.cache_verify": cache_verify_sha256_hex,
    "storage.object_metadata": storage_sha256_hex,
}


def _product_modules_spelling_the_format() -> list[str]:
    """Modules whose own code calls `isoformat(timespec="milliseconds")`.

    Walked over the ratchet's own package census, so the two gates cannot cover
    different trees: this is the same "what ships" list, and #516's finding was
    precisely that a producer living outside that list stayed invisible. Scoped
    to the filesystem rather than `git ls-files` because `contracts/clock.py` is
    untracked until the commit that lands it.
    """
    hits: list[str] = []
    for package in PACKAGES:
        for path in (REPO / package).rglob("*.py"):
            if "__pycache__" in path.relative_to(REPO).parts:
                continue
            if 'isoformat(timespec="milliseconds")' in path.read_text(encoding="utf-8"):
                hits.append(path.relative_to(REPO).as_posix())
    return sorted(hits)


def test_the_shared_producer_writes_utc_milliseconds_and_z() -> None:
    """`...T..:..:..mmmZ` — the form `fromisoformat` round-trips as UTC.

    The `.replace("+00:00", "Z")` is not decoration: a `+00:00` tail and a `Z`
    tail compare unequal as strings, and evidence rows are compared as strings.
    """
    value = utc_now_iso()
    assert TIMESTAMP_FORMAT.match(value), f"utc_now_iso() wrote {value!r}"
    assert datetime.fromisoformat(value).tzinfo is UTC


def test_the_format_has_exactly_one_producer_in_product_code() -> None:
    """Reverse control for the merge: a re-spelled copy must go red.

    The clone ratchet compares same-named bodies; this compares the *spelling* of
    the format, so a copy under another name — or a module that inlines the
    expression again — fails here. `contracts/clock.py` is untracked until the
    commit that lands it, which is why this walks the filesystem.
    """
    assert _product_modules_spelling_the_format() == ["contracts/clock.py"]


@pytest.mark.parametrize("rel", TIMESTAMP_CONSUMERS)
def test_every_measured_consumer_delegates_instead_of_spelling_the_format(
    rel: str,
) -> None:
    """Each of the five copies is now an import of the one producer.

    Checked on the AST, not on a substring: the module must import `utc_now_iso`
    and hold no `datetime.now(...)` of its own.
    """
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "contracts.clock"
        for alias in node.names
    }
    assert "utc_now_iso" in imported, f"{rel} no longer imports the shared producer"
    own_now = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "now"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "datetime"
    ]
    assert not own_now, f"{rel} reads the clock again instead of delegating"


@pytest.mark.parametrize(
    ("model", "field_name"),
    [(BatchReplayRecord, "started_at"), (VerificationReport, "verified_at")],
    ids=["batch_replay.started_at", "offline_verify.verified_at"],
)
def test_the_persisted_timestamp_fields_are_wired_to_the_one_producer(
    model: type, field_name: str
) -> None:
    """The field clients read must default to the shared producer, by identity."""
    found = next(f for f in dataclasses.fields(model) if f.name == field_name)
    assert found.default_factory is utc_now_iso, (
        f"{model.__name__}.{field_name} no longer defaults to contracts.clock.utc_now_iso"
    )


def test_the_event_envelope_carries_the_shared_format() -> None:
    """`occurred_at` is the wire field §3.4 documents; it must stay in shape."""
    envelope = build_envelope("specproof.test", "job-1", {"job": "1"})
    assert TIMESTAMP_FORMAT.match(envelope["occurred_at"]), envelope["occurred_at"]


@pytest.mark.parametrize("value", ["2026-10-28T09:00:00+00:00", "2026-10-28T09:00:00Z"])
def test_a_drifted_timestamp_fails_the_shape_rule(value: str) -> None:
    """Reverse control: the shape test must reject the two drifts it exists for.

    `+00:00` is what `isoformat()` returns before the `.replace` — and what the
    30 no-argument call sites across 22 product modules still write — while
    no-milliseconds is what the format looks like after someone tidies it up.
    Both parse fine, which is exactly why agreement needs a shape and one
    producer, not a parse.
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

    There IS a second digest vocabulary: `contracts/events.py::payload_digest`
    returns `"sha256:" + hexdigest` for event envelopes. That is not a drift — the
    two are reconciled at read time by `storage/object_metadata.normalize_payload_digest`,
    which strips the prefix and lowercases. This leg is about the three artifact
    copies, whose consumers compare them as bare strings with no normalizer between.
    """
    assert re.fullmatch(r"[0-9a-f]{64}", DIGEST_READERS[reader](b"specproof"))


def test_the_digest_copies_agree_on_a_value_no_copy_hardcoded() -> None:
    """A copy that returns a constant to make the agreement test pass still fails."""
    payload = b"evidence capsule bytes"
    values = {name: reader(payload) for name, reader in DIGEST_READERS.items()}
    assert len(set(values.values())) == 1, values
    assert next(iter(values.values())) == hashlib.sha256(payload).hexdigest()
