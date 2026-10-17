"""Fence tests for ``commands/replay.py`` reference classification.

``replay`` resolves a capsule through the object metadata store FIRST, then
falls back to a legacy path lookup. The branch is decided entirely by
``_looks_like_object_reference``: a 32-hex uuid4 or 64-hex sha256 (optionally
``sha256:``-prefixed) is treated as a store reference; anything else is a
plain path. A regression in that classifier silently flips capsules between
the two resolution paths — so the classifier and the legacy fallback branch
are fenced here, with the store isolated so the test never needs a database.

Speed: pure-string and path checks only; no network, no Docker, no DB.
"""

from pathlib import Path

import pytest

from cli.specproof.commands import replay as replay_mod
from cli.specproof.commands.replay import (
    _looks_like_object_reference,
    _resolve_capsule,
)

# ─────────────────────────────────────────────────────────────
# _looks_like_object_reference — the dispatch classifier
# ─────────────────────────────────────────────────────────────

def test_uuid4_32hex_is_a_reference():
    assert _looks_like_object_reference("0123456789abcdef0123456789abcdef") is True


def test_sha256_64hex_is_a_reference():
    assert _looks_like_object_reference("a" * 64) is True


def test_sha256_prefixed_64hex_is_a_reference():
    assert _looks_like_object_reference("sha256:" + "a" * 64) is True


def test_case_insensitive_hex_is_a_reference():
    # .lower() runs before matching, so uppercase hex still qualifies.
    assert _looks_like_object_reference("A" * 32) is True
    assert _looks_like_object_reference("SHA256:" + "F" * 64) is True


def test_whitespace_padding_is_stripped():
    assert _looks_like_object_reference("  " + "a" * 32 + "  ") is True


def test_plain_path_is_not_a_reference():
    assert _looks_like_object_reference("capsules/foo.zip") is False
    assert _looks_like_object_reference("./capsule.zip") is False
    assert _looks_like_object_reference("C:\\capsules\\foo.zip") is False


def test_sha256_prefix_with_wrong_length_is_not_a_reference():
    # 63 hex after the prefix is neither uuid4 nor sha256 length.
    assert _looks_like_object_reference("sha256:" + "a" * 63) is False
    assert _looks_like_object_reference("sha256:" + "a" * 65) is False


def test_non_hex_after_prefix_is_not_a_reference():
    assert _looks_like_object_reference("sha256:not-a-hex-string") is False


def test_wrong_hex_length_is_not_a_reference():
    assert _looks_like_object_reference("a" * 31) is False
    assert _looks_like_object_reference("a" * 33) is False


def test_empty_and_blank_are_not_references():
    assert _looks_like_object_reference("") is False
    assert _looks_like_object_reference("   ") is False


# ─────────────────────────────────────────────────────────────
# _resolve_capsule — legacy path fallback (store isolated)
# ─────────────────────────────────────────────────────────────

def test_legacy_fallback_returns_existing_path(monkeypatch, tmp_path: Path):
    # With the store absent, a plain existing path resolves to itself
    # with no metadata record.
    monkeypatch.setattr(replay_mod, "_open_store", lambda: None)
    capsule = tmp_path / "capsule.zip"
    capsule.write_text("payload", encoding="utf-8")
    path, record = _resolve_capsule(str(capsule))
    assert path == capsule
    assert record is None


def test_legacy_fallback_missing_path_exits_nonzero(
    monkeypatch, tmp_path: Path,
):
    # A non-existent plain path is an honest error, never a silent miss.
    monkeypatch.setattr(replay_mod, "_open_store", lambda: None)
    with pytest.raises(SystemExit) as exc:
        _resolve_capsule(str(tmp_path / "missing.zip"))
    assert exc.value.code == 1
