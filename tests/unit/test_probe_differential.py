"""Unit tests for execution-time probe artifacts + expectation evaluation.

No Docker: only the pure parsing/comparison logic and the adapter's
artifact reader (against a temp directory).
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.nodes.run_differential import evaluate_probe_expectation
from experiments.adapters import (
    PROBE_ARTIFACT_REL,
    JavaMavenAdapter,
    parse_probe_artifact,
)


def _payload(
    timestamp: str | None = "2026-01-01T00:00:00Z", failed: bool = False
) -> dict[str, object]:
    return {
        "exchange": "specproof.demo.events",
        "routingKey": "order.created",
        "type": "OrderCreatedEvent",
        "timestamp": timestamp,
        "failed": failed,
    }


def _artifact(
    publish_count: int,
    outcome: str = "success",
    payloads: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    if payloads is None:
        payloads = [_payload() for _ in range(publish_count)]
    return {
        "probe_version": 1,
        "publish_count": publish_count,
        "outcome": outcome,
        "payloads": payloads,
    }


# ── parse_probe_artifact ─────────────────────────────────────────────


class TestParseProbeArtifact:
    def test_valid_artifact_roundtrip(self) -> None:
        artifact = _artifact(2, "success")
        parsed = parse_probe_artifact(json.dumps(artifact))
        assert parsed == artifact

    def test_null_timestamp_payload_is_valid(self) -> None:
        artifact = _artifact(1, "success", [_payload(timestamp=None)])
        parsed = parse_probe_artifact(json.dumps(artifact))
        assert parsed is not None
        assert parsed["payloads"][0]["timestamp"] is None

    def test_invalid_json_returns_none(self) -> None:
        assert parse_probe_artifact("{not json") is None

    def test_missing_probe_version_returns_none(self) -> None:
        artifact = _artifact(1)
        del artifact["probe_version"]
        assert parse_probe_artifact(json.dumps(artifact)) is None

    def test_count_payload_mismatch_returns_none(self) -> None:
        artifact = _artifact(1, "success", [_payload(), _payload()])
        assert parse_probe_artifact(json.dumps(artifact)) is None

    def test_missing_payload_key_returns_none(self) -> None:
        artifact = _artifact(1, "success", [{"exchange": "x"}])
        assert parse_probe_artifact(json.dumps(artifact)) is None

    def test_non_bool_failed_returns_none(self) -> None:
        payload = _payload()
        payload["failed"] = "yes"
        assert parse_probe_artifact(json.dumps(_artifact(1, payloads=[payload]))) is None

    def test_non_int_count_returns_none(self) -> None:
        artifact = _artifact(1)
        artifact["publish_count"] = "one"
        assert parse_probe_artifact(json.dumps(artifact)) is None


# ── evaluate_probe_expectation ───────────────────────────────────────


class TestEvaluateProbeExpectation:
    def test_97_retry_duplicate_regression(self) -> None:
        """base fast-fails with 1 attempt; head retries into 2 attempts."""
        expectation = {
            "base": {"publish_count": 1},
            "head": {"publish_count": 1},
        }
        base = _artifact(1, "error", [_payload(failed=True)])
        head = _artifact(2, "success", [_payload(failed=True), _payload()])
        verdict, detail, violations = evaluate_probe_expectation(
            expectation, base, head
        )
        assert verdict == "REGRESSION"
        assert violations == ["publish_count"]
        assert "publish_count" in detail

    def test_97_compliant_when_head_does_not_retry(self) -> None:
        expectation = {
            "base": {"publish_count": 1},
            "head": {"publish_count": 1},
        }
        base = _artifact(1, "error", [_payload(failed=True)])
        head = _artifact(1, "error", [_payload(failed=True)])
        verdict, _detail, violations = evaluate_probe_expectation(
            expectation, base, head
        )
        assert verdict == "COMPLIANT"
        assert violations == []

    def test_98_noop_head_errors_regression(self) -> None:
        """head removed the early return: no-op change errors (outcome)."""
        expectation = {
            "base": {"publish_count": 0, "outcome": "success"},
            "head": {"publish_count": 0, "outcome": "success"},
        }
        base = _artifact(0, "success", [])
        head = _artifact(0, "error", [])
        verdict, detail, violations = evaluate_probe_expectation(
            expectation, base, head
        )
        assert verdict == "REGRESSION"
        assert violations == ["outcome"]
        assert "outcome" in detail

    def test_98_compliant_on_honest_base_and_head(self) -> None:
        expectation = {
            "base": {"publish_count": 0, "outcome": "success"},
            "head": {"publish_count": 0, "outcome": "success"},
        }
        base = _artifact(0, "success", [])
        head = _artifact(0, "success", [])
        verdict, _detail, violations = evaluate_probe_expectation(
            expectation, base, head
        )
        assert verdict == "COMPLIANT"
        assert violations == []

    def test_100_null_timestamp_regression(self) -> None:
        """base payload timestamp set; head nulled it before publish."""
        expectation = {
            "base": {"payload_timestamp_non_null": True},
            "head": {"payload_timestamp_non_null": True},
        }
        base = _artifact(1, "success", [_payload(timestamp="2026-01-01T00:00:00Z")])
        head = _artifact(1, "success", [_payload(timestamp=None)])
        verdict, detail, violations = evaluate_probe_expectation(
            expectation, base, head
        )
        assert verdict == "REGRESSION"
        assert violations == ["payload_timestamp_non_null"]
        assert "payload_timestamp_non_null" in detail

    def test_100_compliant_when_timestamp_kept(self) -> None:
        expectation = {
            "base": {"payload_timestamp_non_null": True},
            "head": {"payload_timestamp_non_null": True},
        }
        base = _artifact(1, "success", [_payload()])
        head = _artifact(1, "success", [_payload()])
        verdict, _detail, violations = evaluate_probe_expectation(
            expectation, base, head
        )
        assert verdict == "COMPLIANT"
        assert violations == []

    def test_base_violation_is_non_reproducible(self) -> None:
        expectation = {
            "base": {"publish_count": 1},
            "head": {"publish_count": 1},
        }
        verdict, detail, violations = evaluate_probe_expectation(
            expectation, _artifact(3), _artifact(1)
        )
        assert verdict == "NON_REPRODUCIBLE"
        assert violations == ["publish_count"]
        assert "base artifact" in detail

    def test_missing_artifacts_are_non_reproducible(self) -> None:
        expectation = {
            "base": {"publish_count": 0},
            "head": {"publish_count": 0},
        }
        verdict, detail, _violations = evaluate_probe_expectation(
            expectation, None, _artifact(0, payloads=[])
        )
        assert verdict == "NON_REPRODUCIBLE"
        assert "base" in detail

    def test_unknown_field_is_non_reproducible(self) -> None:
        expectation = {
            "base": {"publish_count": 0, "mystery": 1},
            "head": {"publish_count": 0},
        }
        verdict, detail, _violations = evaluate_probe_expectation(
            expectation, _artifact(0, payloads=[]), _artifact(0, payloads=[])
        )
        assert verdict == "NON_REPRODUCIBLE"
        assert "mystery" in detail

    def test_missing_profiles_are_non_reproducible(self) -> None:
        verdict, _detail, _violations = evaluate_probe_expectation(
            {"contract_id": "EVENT_ONCE-01"},
            _artifact(0, payloads=[]),
            _artifact(0, payloads=[]),
        )
        assert verdict == "NON_REPRODUCIBLE"


# ── JavaMavenAdapter probe hooks ─────────────────────────────────────


class TestAdapterProbeHooks:
    def test_probe_test_class_selectors(self) -> None:
        adapter = JavaMavenAdapter()
        assert adapter.probe_test_class() == "SpecProofProbeTest"
        assert adapter.probe_test_class("brokerFailureRetry") == (
            "SpecProofProbeTest#brokerFailureRetry"
        )

    def test_read_probe_artifact_roundtrip(self, tmp_path: Path) -> None:
        artifact = _artifact(1, "success")
        (tmp_path / "target").mkdir()
        (tmp_path / PROBE_ARTIFACT_REL).write_text(
            json.dumps(artifact), encoding="utf-8"
        )
        adapter = JavaMavenAdapter()
        assert adapter.read_probe_artifact(str(tmp_path)) == artifact

    def test_read_probe_artifact_absent_returns_none(self, tmp_path: Path) -> None:
        adapter = JavaMavenAdapter()
        assert adapter.read_probe_artifact(str(tmp_path)) is None

    def test_read_probe_artifact_invalid_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "target").mkdir()
        (tmp_path / PROBE_ARTIFACT_REL).write_text(
            '{"probe_version": "x"}', encoding="utf-8"
        )
        adapter = JavaMavenAdapter()
        assert adapter.read_probe_artifact(str(tmp_path)) is None
