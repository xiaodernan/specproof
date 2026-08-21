"""Backlog #7 攻击测试 3: 缓存投毒 (MAVEN_USER_HOME / venv; 离线假缓存).

Threat: the dependency cache the sandbox mounts (MAVEN_USER_HOME
/home/maven/.m2, or a venv) is writable shared state. A poisoned entry —
a swapped jar, tampered version metadata — would be silently consumed by
the next build: a supply-chain attack on the verification pipeline itself.

Defense under test: sandbox/cache_verify compares the cache against the
seed-time digest manifest BEFORE the next execution and fails closed
(verdict "fail": refuse to execute) or rebuilds per policy (verdict
"rebuild": delete the poisoned entries; the caller re-seeds — the sandbox
has --network none). The runner wiring (run_sandboxed cache_dir/
cache_manifest/on_poison) is asserted with a fake subprocess: poison ->
zero executions, clean -> exactly one execution.

Annotated gap: the docker-mode NAMED volume is not host-readable by the
runner, so the pre-run check covers host-accessible cache dirs (local/dev
mode and host-seeded caches); verifying the in-container volume needs a
check step inside the sandbox (documented follow-up, see
docs/operations/THREAT_TESTING.md).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import sandbox.runner as runner
from sandbox.cache_verify import (
    MAX_ENTRY_BYTES,
    CacheManifestError,
    enforce_cache_integrity,
    load_manifest,
    sha256_hex,
    verify_cache_dir,
)
from sandbox.runner import run_sandboxed


class _FakeCompleted:
    returncode = 0
    stdout = "ok"
    stderr = ""


def _write_entry(cache: Path, rel_path: str, content: bytes) -> None:
    target = cache / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _write_manifest(path: Path, entries: dict[str, bytes]) -> Path:
    payload = {rel: sha256_hex(content) for rel, content in entries.items()}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _m2_layout(cache: Path) -> None:
    """A MAVEN_USER_HOME-shaped cache: repository/org/demo/app/1.0/app-1.0.jar."""
    _write_entry(
        cache,
        "repository/org/demo/app/1.0/app-1.0.jar",
        b"legitimate demo artifact bytes",
    )
    _write_entry(cache, "repository/org/demo/lib/2.0/lib-2.0.jar", b"legit lib bytes")


def _venv_layout(cache: Path) -> None:
    _write_entry(cache, "pyvenv.cfg", b"home = /usr/bin\nversion = 3.12.0\n")
    _write_entry(
        cache,
        "lib/site-packages/demo-1.0.dist-info/METADATA",
        b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n",
    )


def _capture_runs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> _FakeCompleted:
        calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    monkeypatch.setattr(runner, "_image_ready", lambda _image: True)
    monkeypatch.setattr(runner, "_ensure_writable_target", lambda _ws: "")
    return calls


# ══════════════════════════════════════════════════════════════════
# 单元层: 摘要校验 / 版本篡改 / 缺失 / 超大 / 清单错误 / 路径逃逸
# ══════════════════════════════════════════════════════════════════

class TestCacheVerificationUnit:
    def test_poisoned_m2_artifact_digest_mismatch_detected(self, tmp_path: Path) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        jar = cache / "repository/org/demo/app/1.0/app-1.0.jar"
        jar.write_bytes(b"attacker-controlled artifact bytes")
        manifest = {
            "repository/org/demo/app/1.0/app-1.0.jar": sha256_hex(
                b"legitimate demo artifact bytes"
            )
        }
        mismatches = verify_cache_dir(cache, manifest)
        assert len(mismatches) == 1
        assert mismatches[0].rel_path == "repository/org/demo/app/1.0/app-1.0.jar"
        assert mismatches[0].expected == sha256_hex(b"legitimate demo artifact bytes")
        assert mismatches[0].actual == sha256_hex(b"attacker-controlled artifact bytes")
        check = enforce_cache_integrity(cache, manifest)
        assert check.ok is False
        assert check.verdict == "fail"
        assert "fail-closed" in check.note

    def test_version_tampered_venv_detected(self, tmp_path: Path) -> None:
        cache = tmp_path / "venv"
        _venv_layout(cache)
        original = {
            "pyvenv.cfg": b"home = /usr/bin\nversion = 3.12.0\n",
            "lib/site-packages/demo-1.0.dist-info/METADATA": (
                b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
            ),
        }
        manifest = {rel: sha256_hex(content) for rel, content in original.items()}
        # Poison: bump the recorded versions on disk.
        (cache / "pyvenv.cfg").write_bytes(b"home = /usr/bin\nversion = 99.99\n")
        (cache / "lib/site-packages/demo-1.0.dist-info/METADATA").write_bytes(
            b"Metadata-Version: 2.1\nName: demo\nVersion: 99.0.0\n"
        )
        mismatches = verify_cache_dir(cache, manifest)
        assert {m.rel_path for m in mismatches} == {
            "pyvenv.cfg",
            "lib/site-packages/demo-1.0.dist-info/METADATA",
        }
        check = enforce_cache_integrity(cache, manifest)
        assert check.ok is False
        assert check.verdict == "fail"

    def test_absent_manifest_entry_fails_closed(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        cache.mkdir()
        manifest = {"org/demo/missing.jar": "0" * 64}
        mismatches = verify_cache_dir(cache, manifest)
        assert len(mismatches) == 1
        assert mismatches[0].actual == "<absent>"
        assert enforce_cache_integrity(cache, manifest).ok is False

    def test_oversized_entry_flagged_without_hashing(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        _write_entry(cache, "repo/big.jar", b"x" * 32)
        manifest = {"repo/big.jar": sha256_hex(b"x" * 32)}
        mismatches = verify_cache_dir(cache, manifest, max_entry_bytes=16)
        assert len(mismatches) == 1
        assert mismatches[0].actual.startswith("<oversized:")
        assert MAX_ENTRY_BYTES > 0

    def test_clean_cache_verdict_use(self, tmp_path: Path) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        content = (cache / "repository/org/demo/app/1.0/app-1.0.jar").read_bytes()
        manifest = {"repository/org/demo/app/1.0/app-1.0.jar": sha256_hex(content)}
        check = enforce_cache_integrity(cache, manifest)
        assert check.ok is True
        assert check.verdict == "use"
        assert check.mismatches == ()

    @pytest.mark.parametrize(
        "payload",
        [
            '[{"not": "an object"}]',
            '{"ok.jar": "xyz"}',
            '{"ok.jar": 123}',
            '"just a string"',
        ],
    )
    def test_manifest_loader_rejects_malformed(self, tmp_path: Path, payload: str) -> None:
        path = tmp_path / "manifest.json"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(CacheManifestError):
            load_manifest(path)

    def test_manifest_path_traversal_fails_closed(self, tmp_path: Path) -> None:
        cache = tmp_path / "cache"
        cache.mkdir()
        check = enforce_cache_integrity(cache, {"../outside.txt": "0" * 64})
        assert check.ok is False
        assert check.verdict == "fail"
        assert "逃逸" in check.note

    def test_rebuild_policy_deletes_poisoned_entries(self, tmp_path: Path) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        clean = cache / "repository/org/demo/lib/2.0/lib-2.0.jar"
        poisoned = cache / "repository/org/demo/app/1.0/app-1.0.jar"
        poisoned.write_bytes(b"poisoned bytes")
        manifest = {
            "repository/org/demo/app/1.0/app-1.0.jar": sha256_hex(
                b"legitimate demo artifact bytes"
            ),
            "repository/org/demo/lib/2.0/lib-2.0.jar": sha256_hex(b"legit lib bytes"),
        }
        check = enforce_cache_integrity(cache, manifest, on_poison="rebuild")
        assert check.ok is True
        assert check.verdict == "rebuild"
        assert check.removed == ("repository/org/demo/app/1.0/app-1.0.jar",)
        assert not poisoned.exists()
        assert clean.exists()

    def test_rebuild_policy_fails_closed_when_deletion_impossible(
        self, tmp_path: Path,
    ) -> None:
        cache = tmp_path / "cache"
        dir_entry = cache / "repo/app.jar"
        dir_entry.mkdir(parents=True)
        (dir_entry / "child.txt").write_text("x", encoding="utf-8")
        manifest = {"repo/app.jar": sha256_hex(b"legit")}
        check = enforce_cache_integrity(cache, manifest, on_poison="rebuild")
        assert check.ok is False
        assert check.verdict == "fail"
        assert "重建失败" in check.note

    def test_unknown_policy_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            enforce_cache_integrity(tmp_path, {}, on_poison="wipe")


# ══════════════════════════════════════════════════════════════════
# 接线层: run_sandboxed 在执行前校验; 投毒 = 零执行 (fail-closed)
# ══════════════════════════════════════════════════════════════════

class TestCachePoisoningRunnerWiring:
    def test_poisoned_cache_blocks_execution_fail_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        (cache / "repository/org/demo/app/1.0/app-1.0.jar").write_bytes(b"poisoned")
        manifest = _write_manifest(
            tmp_path / "manifest.json",
            {"repository/org/demo/app/1.0/app-1.0.jar": b"legitimate demo artifact bytes"},
        )
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(cache),
            cache_manifest=str(manifest),
        )
        assert result.exit_code == -1
        assert result.mode == "docker"
        assert "投毒" in result.error
        assert "fail-closed" in result.error
        assert result.cache_note == result.error
        assert calls == [], "poisoned cache must block the docker run"

    def test_clean_cache_allows_execution_with_note(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        jar = cache / "repository/org/demo/app/1.0/app-1.0.jar"
        manifest = _write_manifest(
            tmp_path / "manifest.json",
            {"repository/org/demo/app/1.0/app-1.0.jar": jar.read_bytes()},
        )
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(cache),
            cache_manifest=str(manifest),
        )
        assert result.exit_code == 0
        assert result.error == ""
        assert len(calls) == 1
        assert "缓存完整性通过" in result.cache_note

    def test_rebuild_policy_deletes_poison_then_executes(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        poisoned = cache / "repository/org/demo/app/1.0/app-1.0.jar"
        poisoned.write_bytes(b"poisoned")
        manifest = _write_manifest(
            tmp_path / "manifest.json",
            {"repository/org/demo/app/1.0/app-1.0.jar": b"legitimate demo artifact bytes"},
        )
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(cache),
            cache_manifest=str(manifest),
            on_poison="rebuild",
        )
        assert result.exit_code == 0
        assert not poisoned.exists()
        assert len(calls) == 1
        assert "重建" in result.cache_note

    def test_unreadable_manifest_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(cache),
            cache_manifest=str(tmp_path / "no-such-manifest.json"),
        )
        assert result.exit_code == -1
        assert "缓存校验失败" in result.error
        assert calls == []

    def test_local_mode_also_verified_before_execution(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "venv"
        _venv_layout(cache)
        (cache / "pyvenv.cfg").write_bytes(b"version = 99.99")
        manifest = _write_manifest(
            tmp_path / "manifest.json",
            {"pyvenv.cfg": b"home = /usr/bin\nversion = 3.12.0\n"},
        )
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(
            ["python", "-m", "pytest"],
            str(tmp_path / "ws"),
            mode="local",
            cache_dir=str(cache),
            cache_manifest=str(manifest),
        )
        assert result.exit_code == -1
        assert result.mode == "local"
        assert "投毒" in result.error
        assert calls == []

    def test_invalid_policy_fails_closed_no_execution(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "m2"
        _m2_layout(cache)
        manifest = _write_manifest(tmp_path / "manifest.json", {})
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(cache),
            cache_manifest=str(manifest),
            on_poison="wipe",
        )
        assert result.exit_code == -1
        assert "cache verification failed" in result.error
        assert calls == []

    def test_verification_skipped_when_not_requested(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The check is opt-in via cache_dir+cache_manifest; callers that
        pass neither keep the legacy behaviour (documented)."""
        calls = _capture_runs(monkeypatch)
        result = run_sandboxed(["mvn", "-o", "test"], str(tmp_path / "ws"), mode="docker")
        assert result.exit_code == 0
        assert len(calls) == 1
        assert result.cache_note == ""

    def test_manifest_entry_hash_helper_stable(self) -> None:
        assert sha256_hex(b"abc") == hashlib.sha256(b"abc").hexdigest()
