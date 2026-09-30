"""#136: the cache-poisoning defense had no producer, an arm that
self-disarmed on a half-configuration, and a verdict field nobody read.

Measured in the shipped tree before this batch:

1. nothing produced a seed-time digest manifest. `sandbox/cache_verify.py`
   documented "Manifest format (JSON, produced by the seed step)" while
   `scripts/seed_sandbox_cache.ps1`, `seed_npm_cache.ps1` and
   `seed_pip_wheelhouse.ps1` hash nothing (grep for manifest|sha256|
   Get-FileHash: 0 hits in all three). The operator could not make the
   artifact the guard consumes.
2. no shipped caller passed cache_dir/cache_manifest, and passing exactly
   one of them fell through the `if cache_dir and cache_manifest is not
   None` gate and EXECUTED anyway — a half-configured deployment was
   fail-open.
3. `SandboxResult.cache_note` had no reader outside the fault suite, so
   even a verified run could not reach a job record. Closing the silent
   half: the field now carries a state on every cache-mounting run, so a
   future reader can tell verified / not verified apart. Wiring a shipped
   caller still needs the compose/seed decision (owed, not done here).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import sandbox.runner as runner
from sandbox.cache_verify import (
    CacheManifestError,
    build_digest_manifest,
    enforce_cache_integrity,
    load_manifest,
    main,
    save_digest_manifest,
)
from sandbox.runner import NODE_PROFILE, run_sandboxed

REPO_ROOT = Path(__file__).resolve().parents[2]


def _seeded_cache(tmp_path: Path) -> Path:
    cache = tmp_path / "cache"
    nested = cache / "repository" / "group"
    nested.mkdir(parents=True)
    (nested / "a.jar").write_bytes(b"artifact-a")
    (nested / "b.pom").write_bytes(b"<project/>")
    return cache


class _NoExecution:
    """Record any attempt to actually run the workload, then fail the guard's
    own test: a refusal must happen BEFORE a command is spawned."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def arm(self, monkeypatch: pytest.MonkeyPatch) -> _NoExecution:
        def fake_docker(command, workspace, timeout, profile=None):
            self.calls.append(("docker", *command))
            return runner.SandboxResult(exit_code=0, stdout="", stderr="", mode="docker")

        def fake_local(command, workspace, timeout, mode):
            self.calls.append((mode, *command))
            return runner.SandboxResult(exit_code=0, stdout="", stderr="", mode=mode)

        monkeypatch.setattr(runner, "_run_docker", fake_docker)
        monkeypatch.setattr(runner, "_run_local", fake_local)
        return self


class TestProducer:
    def test_seeded_manifest_verifies_against_the_tree_it_came_from(self, tmp_path) -> None:
        cache = _seeded_cache(tmp_path)
        manifest = build_digest_manifest(cache)
        assert load_manifest(save_digest_manifest(manifest, tmp_path / "m.json")) == manifest
        manifest_path = save_digest_manifest(manifest, tmp_path / "m.json")
        assert main(["verify", "--cache-dir", str(cache), "--manifest", str(manifest_path)]) == 0

    def test_keys_are_posix_relative_and_values_the_files_own_bytes(self, tmp_path) -> None:
        manifest = build_digest_manifest(_seeded_cache(tmp_path))
        assert set(manifest) == {"repository/group/a.jar", "repository/group/b.pom"}
        assert manifest["repository/group/a.jar"] == hashlib.sha256(b"artifact-a").hexdigest()

    def test_a_swapped_artifact_is_the_entry_reported(self, tmp_path) -> None:
        cache = _seeded_cache(tmp_path)
        manifest = build_digest_manifest(cache)
        (cache / "repository" / "group" / "a.jar").write_bytes(b"backdoored")
        check = enforce_cache_integrity(cache, manifest)
        assert check.ok is False and check.verdict == "fail"
        assert [m.rel_path for m in check.mismatches] == ["repository/group/a.jar"]

    def test_an_empty_cache_refuses_instead_of_writing_a_manifest_that_checks_nothing(
        self, tmp_path
    ) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(CacheManifestError, match="拒绝写出空清单"):
            build_digest_manifest(tmp_path / "empty")

    def test_a_missing_cache_dir_refuses(self, tmp_path) -> None:
        with pytest.raises(CacheManifestError, match="缓存目录不存在"):
            build_digest_manifest(tmp_path / "never-seeded")

    def test_oversized_entries_are_left_out_of_the_manifest(self, tmp_path) -> None:
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "small.txt").write_bytes(b"1234")
        (cache / "huge.bin").write_bytes(b"123456789")
        assert set(build_digest_manifest(cache, max_entry_bytes=5)) == {"small.txt"}

    def test_saving_leaves_no_temp_file_behind(self, tmp_path) -> None:
        seeded = build_digest_manifest(_seeded_cache(tmp_path))
        out = save_digest_manifest(seeded, tmp_path / "m.json")
        assert out.read_text(encoding="utf-8").startswith("{")
        assert list(out.parent.glob("*.tmp")) == []


class TestCli:
    def test_seed_then_poison_reports_1_and_the_fail_closed_note(self, tmp_path, capsys) -> None:
        cache = _seeded_cache(tmp_path)
        out = tmp_path / "m.json"
        assert main(["seed", "--cache-dir", str(cache), "--out", str(out)]) == 0
        assert "2 entries" in capsys.readouterr().out
        (cache / "repository" / "group" / "b.pom").write_bytes(b"<project/><!--evil-->")
        assert main(["verify", "--cache-dir", str(cache), "--manifest", str(out)]) == 1
        assert "拒绝执行 (fail-closed)" in capsys.readouterr().out

    def test_a_malformed_manifest_exits_2_and_never_0(self, tmp_path, capsys) -> None:
        cache = _seeded_cache(tmp_path)
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"repository/group/a.jar": "not-a-sha256"}), encoding="utf-8")
        assert main(["verify", "--cache-dir", str(cache), "--manifest", str(bad)]) == 2
        assert "refused" in capsys.readouterr().err

    def test_the_documented_subcommands_exist(self, tmp_path) -> None:
        for action in ("seed", "verify"):
            with pytest.raises(SystemExit) as excinfo:
                main([action])  # no --cache-dir: argparse usage error, not a wrong verdict
            assert excinfo.value.code == 2

    def test_the_module_is_runnable_as_an_entry_point(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "sandbox.cache_verify", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(REPO_ROOT),
            timeout=120,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        assert proc.returncode == 0
        assert "usage: python -m sandbox.cache_verify" in proc.stdout


class TestArm:
    def test_manifest_without_cache_dir_refuses_and_names_it(self, tmp_path, monkeypatch) -> None:
        guard = _NoExecution().arm(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_manifest={"a.jar": hashlib.sha256(b"x").hexdigest()},
        )
        assert result.exit_code == -1
        assert "给了 cache_manifest" in result.error and "缺 cache_dir" in result.error
        assert guard.calls == []

    def test_cache_dir_without_manifest_refuses_and_names_it(self, tmp_path, monkeypatch) -> None:
        guard = _NoExecution().arm(monkeypatch)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(_seeded_cache(tmp_path)),
        )
        assert result.exit_code == -1
        assert "给了 cache_dir" in result.error and "缺 cache_manifest" in result.error
        assert guard.calls == []

    def test_a_fully_armed_clean_cache_runs_and_reports_pass(self, tmp_path, monkeypatch) -> None:
        guard = _NoExecution().arm(monkeypatch)
        cache = _seeded_cache(tmp_path)
        result = run_sandboxed(
            ["mvn", "-o", "test"],
            str(tmp_path / "ws"),
            mode="docker",
            cache_dir=str(cache),
            cache_manifest=build_digest_manifest(cache),
        )
        assert result.exit_code == 0 and len(guard.calls) == 1
        assert "缓存完整性通过" in result.cache_note
        assert "NOT VERIFIED" not in result.cache_note

    def test_a_cache_mounting_profile_reports_not_verified(self, tmp_path, monkeypatch) -> None:
        _NoExecution().arm(monkeypatch)
        result = run_sandboxed(["mvn", "-o", "test"], str(tmp_path / "ws"), mode="docker")
        assert "NOT VERIFIED" in result.cache_note
        assert result.cache_note.count(runner.MAVEN_PROFILE.cache_mount) == 1

    def test_a_profile_without_a_cache_volume_stays_silent(self, tmp_path, monkeypatch) -> None:
        assert NODE_PROFILE.cache_mount == ""
        _NoExecution().arm(monkeypatch)
        result = run_sandboxed(
            ["npm", "test"], str(tmp_path / "ws"), mode="docker", profile=NODE_PROFILE
        )
        assert result.cache_note == ""
