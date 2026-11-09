"""#4.2 的第一件事：胶囊清单必须带「反例复现了没有」这个事实。

受害者：反例差分运行的那个生成测试（SpecProofGeneratedTest）。当
base_pass_head_fail 证据到达时，`counterexample_reproduction` 必须为
``reproduces_regression``；静态/探针类证据从未声称自己跑过，必须如实
写 ``not_reproduced`` ——两个词的差异才是差分运行为这只测试加上的信息。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.nodes.create_capsule import create_capsule_node


def _stub_metadata(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG001
    class _NoopRecorder:
        def __call__(self, *args, **kwargs):  # noqa: ARG002
            return None

    monkeypatch.setattr(
        "storage.object_metadata.record_file_object_best_effort", _NoopRecorder(),
    )


def _stub_object_store(monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG001
    class _MinIO:
        def put_object_with_digest(  # noqa: ARG002, ANN001, ANN201
            self, bucket, object_name, data, content_type=None, version=None
        ):
            return {
                "bucket": bucket,
                "object_name": object_name,
                "sha256": "a" * 64,
                "size_bytes": len(data),
                "content_type": content_type or "application/zip",
                "version": version,
            }

        def remove_object(self, bucket, object_name):  # noqa: ARG002
            return None

    class _Store:
        def __init__(self):
            self.recorded: list = []

        def record(self, **_kw):
            self.recorded.append(_kw)
            return True

    monkeypatch.setattr("storage.minio.MinIOClient", lambda *a, **k: _MinIO())
    monkeypatch.setattr(
        "storage.object_metadata.default_object_metadata_store", lambda: _Store(),
    )


def _read_manifest(tmp_path: Path) -> dict:
    raw = (tmp_path / "capsules" / "capsule-F1" / "manifest.json").read_text(encoding="utf-8")
    return json.loads(raw)


def _finding(evidence_type: str) -> dict:
    return {
        "id": "F1",
        "severity": "BLOCKER",
        "confidence": 0.9,
        "contract_id": "AUTH-01",
        "evidence_type": evidence_type,
        "description": "guard removed",
    }


def _state(tmp_path: Path, finding: dict) -> dict:
    tests = tmp_path / "SpecProofGeneratedTest.java"
    tests.write_text("class SpecProofGeneratedTest {}", encoding="utf-8")
    return {
        "confirmed_findings": [finding],
        "contracts": [{"id": "AUTH-01", "checker_type": "http"}],
        "requirement_text": "Unauthenticated requests must receive 401.",
        "generated_tests_path": str(tests),
        "base_ref": "base",
        "head_ref": "head-v1",
        "job_id": "job-425",
    }


def test_base_pass_head_fail_manifest_marks_the_counterexample_as_reproducing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _stub_metadata(monkeypatch)
    _stub_object_store(monkeypatch)

    out = create_capsule_node(_state(tmp_path, _finding("base_pass_head_fail")))  # type: ignore[arg-type]

    assert out["capsules"], "expected one capsule"
    manifest = _read_manifest(tmp_path)
    assert manifest["counterexample_reproduction"] == "reproduces_regression"


def test_static_evidence_manifest_marks_the_counterexample_as_not_reproduced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _stub_metadata(monkeypatch)
    _stub_object_store(monkeypatch)

    create_capsule_node(_state(tmp_path, _finding("static_regex_analysis")))  # type: ignore[arg-type]

    manifest = _read_manifest(tmp_path)
    assert manifest["counterexample_reproduction"] == "not_reproduced"
