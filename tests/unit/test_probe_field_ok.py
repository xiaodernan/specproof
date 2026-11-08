"""Direct tests for ``_probe_field_ok`` — the per-field verdict inside the
probe expectation evaluator.

Pinned here because the isinstance semantics are load-bearing and surprising:
``bool`` is a subclass of ``int`` in Python, so ``True`` is a *legal*
publish_count expectation; an ``int`` 1 is *not* a legal
payload_timestamp_non_null expectation. And the ``payload_timestamp_non_null``
field guards ``all()`` with ``bool(payloads)`` so an empty list never reads as
"all timestamps non-null".
"""

from __future__ import annotations

from agent.nodes.run_differential import _probe_field_ok

# ── artifact is None: nothing is ever okay ──────────────────────────────────


def test_none_artifact_never_matches() -> None:
    assert _probe_field_ok(1, None, "publish_count") is False
    assert _probe_field_ok("success", None, "outcome") is False
    assert _probe_field_ok(True, None, "payload_timestamp_non_null") is False


# ── publish_count ─────────────────────────────────────────────────────────────


def test_publish_count_equal() -> None:
    assert _probe_field_ok(1, {"publish_count": 1}, "publish_count") is True
    assert _probe_field_ok(0, {"publish_count": 0}, "publish_count") is True


def test_publish_count_mismatch() -> None:
    assert _probe_field_ok(1, {"publish_count": 2}, "publish_count") is False


def test_publish_count_expectation_must_be_int() -> None:
    assert _probe_field_ok("1", {"publish_count": 1}, "publish_count") is False
    assert _probe_field_ok(1.0, {"publish_count": 1}, "publish_count") is False


def test_publish_count_bool_expectation_is_a_legal_int() -> None:
    """Python semantics, pinned: isinstance(True, int) is True, and
    1 == True. A True expectation therefore matches publish_count 1."""
    assert _probe_field_ok(True, {"publish_count": 1}, "publish_count") is True
    assert _probe_field_ok(True, {"publish_count": 0}, "publish_count") is False


def test_publish_count_missing_from_artifact() -> None:
    assert _probe_field_ok(1, {}, "publish_count") is False


# ── outcome ───────────────────────────────────────────────────────────────────


def test_outcome_equal() -> None:
    assert _probe_field_ok("success", {"outcome": "success"}, "outcome") is True


def test_outcome_mismatch() -> None:
    assert _probe_field_ok("success", {"outcome": "error"}, "outcome") is False


def test_outcome_expectation_must_be_str() -> None:
    assert _probe_field_ok(0, {"outcome": "success"}, "outcome") is False


def test_outcome_missing_from_artifact() -> None:
    assert _probe_field_ok("success", {}, "outcome") is False


# ── payload_timestamp_non_null ────────────────────────────────────────────────


def test_payload_timestamps_all_non_null() -> None:
    artifact = {"payloads": [{"timestamp": "t"}, {"timestamp": "u"}]}
    assert _probe_field_ok(True, artifact, "payload_timestamp_non_null") is True
    assert _probe_field_ok(False, artifact, "payload_timestamp_non_null") is False


def test_payload_with_null_timestamp() -> None:
    artifact = {"payloads": [{"timestamp": None}]}
    assert _probe_field_ok(True, artifact, "payload_timestamp_non_null") is False
    assert _probe_field_ok(False, artifact, "payload_timestamp_non_null") is True


def test_payload_missing_timestamp_key() -> None:
    artifact = {"payloads": [{"exchange": "e"}]}
    assert _probe_field_ok(True, artifact, "payload_timestamp_non_null") is False


def test_empty_payloads_never_read_as_all_non_null() -> None:
    artifact = {"payloads": []}
    assert _probe_field_ok(True, artifact, "payload_timestamp_non_null") is False
    assert _probe_field_ok(False, artifact, "payload_timestamp_non_null") is True


def test_missing_payloads_key_behaves_as_empty() -> None:
    assert _probe_field_ok(True, {}, "payload_timestamp_non_null") is False
    assert _probe_field_ok(False, {}, "payload_timestamp_non_null") is True


def test_non_list_payloads_do_not_crash_and_read_as_empty() -> None:
    artifact = {"payloads": "not-a-list"}
    # all() over string chars fails isinstance(p, dict) -> actual is False.
    assert _probe_field_ok(True, artifact, "payload_timestamp_non_null") is False
    assert _probe_field_ok(False, artifact, "payload_timestamp_non_null") is True


def test_payload_timestamp_expectation_must_be_bool() -> None:
    artifact = {"payloads": [{"timestamp": "t"}]}
    assert _probe_field_ok(1, artifact, "payload_timestamp_non_null") is False
    assert _probe_field_ok("true", artifact, "payload_timestamp_non_null") is False


# ── unknown field ─────────────────────────────────────────────────────────────


def test_unknown_field_is_never_okay() -> None:
    assert _probe_field_ok(1, {"publish_count": 1}, "mystery") is False
