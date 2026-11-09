"""Artifact references ride the progress stream and the stages fold (§3.1).

Contract, three layers deep:

1. `RedisStore.xadd_progress` carries the refs in the entry (JSON list),
   `xread_progress` parses them back, and a malformed payload degenerates
   to an EMPTY list — never a crash, never a fabricated reference.
2. `agent.worker._stage_artifact_refs` turns object-store addresses and
   report paths into per-node refs; nodes that wrote nothing return [].
3. `GET /jobs/{id}/stages` folds refs per node, order-preserving and
   deduplicated; the SSE payload carries them too.
"""

from __future__ import annotations

import json
from typing import Any

from agent.worker import _stage_artifact_refs
from storage.redis import RedisStore


class _FakeRedis:
    """Minimal client stand-in for progress-stream fields inspection."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.store: dict[str, list[dict[str, Any]]] = {}

    def incr(self, key: str) -> int:
        return 1

    def expire(self, key: str, ttl: int) -> None:  # noqa: ARG002
        return None

    def xadd(self, key: str, data: dict[str, Any], maxlen: int = 1000) -> str:  # noqa: ARG002
        self.data = dict(data)
        self.store.setdefault(key, []).append(
            ("1-0", data)
        )
        return "1-0"

    def xread(self, streams: dict[str, str], count: int = 100) -> Any:  # noqa: ARG002
        key = next(iter(streams))
        msgs = self.store.get(key) or []
        return [(key, msgs)] if msgs else None


def _store_with(fake: _FakeRedis) -> RedisStore:
    store = RedisStore()
    store._client = fake
    return store


class TestXaddCarriesArtifacts:
    def test_xadd_writes_artifacts_as_json(self) -> None:
        fake = _FakeRedis()
        store = _store_with(fake)
        store.xadd_progress("job-1", "create_capsule", "completed",
                            message="2 artifact(s)", percent=80.0,
                            artifacts=["bucket/out.zip", "capsule:file=out.zip"])
        assert json.loads(fake.data["artifacts"]) == ["bucket/out.zip", "capsule:file=out.zip"]

    def test_xadd_omits_artifacts_when_none(self) -> None:
        fake = _FakeRedis()
        store = _store_with(fake)
        store.xadd_progress("job-1", "preflight", "completed")
        assert "artifacts" not in fake.data

    def test_xadd_drops_blank_refs_and_reports_truthy_ones(self) -> None:
        fake = _FakeRedis()
        store = _store_with(fake)
        store.xadd_progress("job-1", "create_capsule", "completed",
                            artifacts=["", "  ", "bucket/out.zip"])
        assert json.loads(fake.data["artifacts"]) == ["bucket/out.zip"]


class TestXreadParsesArtifacts:
    def test_xread_returns_parsed_artifacts(self) -> None:
        fake = _FakeRedis()
        store = _store_with(fake)
        store.xadd_progress("job-1", "publish_report", "completed",
                            artifacts=["report:report.html"])
        events = store.xread_progress("job-1", from_id="0", count=10)
        assert events[0]["artifacts"] == ["report:report.html"]

    def test_xread_malformed_artifacts_degrades_to_empty_list(self) -> None:
        class _Malformed(_FakeRedis):
            def xread(self, streams: dict[str, str], count: int = 100) -> Any:  # noqa: ARG002
                key = next(iter(streams))
                return [(key, [("9-9", {
                    "seq": "1", "node": "create_capsule", "status": "completed",
                    "at": "2026-08-18T00:00:00Z", "percent": "80.0",
                    "message": "2 artifact(s)", "artifacts": "{not-json",
                })])]

        store = _store_with(_Malformed())
        events = store.xread_progress("job-1")
        assert events[0]["artifacts"] == []


class TestStageArtifactRefs:
    def test_create_capsule_returns_refs_then_file_names(self) -> None:
        refs = _stage_artifact_refs("create_capsule", {
            "capsule_refs": ["specproof-bug-capsules/capsule-AUTH-01.zip"],
            "capsules": ["/workspace/out/capsule-AUTH-01.zip"],
        })
        assert refs == [
            "specproof-bug-capsules/capsule-AUTH-01.zip",
            "capsule:file=capsule-AUTH-01.zip",
        ]

    def test_create_capsule_upload_failure_still_reports_local_name(self) -> None:
        refs = _stage_artifact_refs("create_capsule", {
            "capsule_refs": [],
            "capsules": ["/workspace/out/capsule-AUTH-01.zip"],
        })
        assert refs == ["capsule:file=capsule-AUTH-01.zip"]

    def test_generate_counterexamples_reports_test_name(self) -> None:
        refs = _stage_artifact_refs("generate_counterexamples", {
            "generated_tests_path": "/workspace/src/test/java/com/specproof/AuthSuite.java",
        })
        assert refs == ["counterexample_test:AuthSuite.java"]

    def test_publish_report_reports_report_name(self) -> None:
        refs = _stage_artifact_refs("publish_report", {"report_path": "/reports/v-report.html"})
        assert refs == ["report:v-report.html"]

    def test_unrelated_stage_or_garbage_update_reports_nothing(self) -> None:
        assert _stage_artifact_refs("preflight", {"foo": "bar"}) == []
        assert _stage_artifact_refs("create_capsule", None) == []
        assert _stage_artifact_refs("publish_report", {"report_path": "  "}) == []


class TestSsePayload:
    def test_progress_payload_passes_artifacts_through(self) -> None:
        from api.routes import jobs as jobs_module

        payload = jobs_module._progress_payload(
            "job-1", 0,
            {"node": "create_capsule", "status": "completed", "at": "2026-08-18T00:00:02Z",
             "percent": "80.0", "message": "2 artifact(s)",
             "artifacts": ["bucket/out.zip"]},
        )
        assert payload["artifacts"] == ["bucket/out.zip"]

    def test_progress_payload_legacy_entry_defaults_to_empty_list(self) -> None:
        from api.routes import jobs as jobs_module

        payload = jobs_module._progress_payload(
            "job-1", 5,
            {"node": "preflight", "status": "completed", "at": "2026-08-18T00:00:00Z",
             "percent": "0.0", "message": ""},
        )
        assert payload["artifacts"] == []
