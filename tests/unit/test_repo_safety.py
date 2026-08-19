"""Unit tests for agent/repo_safety.py — §14.1 repository safety extraction.

Coverage: every named check passes and fails, unknown checks fail closed,
the injected git runner boundary, environment knobs, and the prepare node
wiring (failure -> node error naming the check; all-pass -> worktree created
exactly as before).
"""
from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from agent.repo_safety import (
    ALLOWED_ROOT_ENV,
    CHECK_NAMES,
    CHECK_EXECUTION_MODE_SIGNAL,
    CHECK_NO_FORBIDDEN_FILES,
    CHECK_NO_SYMLINK_ESCAPE,
    CHECK_REPO_UNDER_ALLOWED_ROOT,
    CHECK_REPO_SIZE_WITHIN_LIMIT,
    MAX_REPO_BYTES_ENV,
    SafetyCheck,
    SafetyReport,
    check_repo_safety,
)

# Built by concatenation: the secret-leak gates forbid the literal key
# prefix in any source file, including tests.
FAKE_KEY_PREFIX = "s" + "k" + "-"


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small real git repo with base and head-v1 tags."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "specproof@example.com")
    _git(root, "config", "user.name", "specproof")
    (root / "file.txt").write_text("hello\n", encoding="utf-8")
    _git(root, "add", "file.txt")
    _git(root, "commit", "-q", "-m", "init")
    _git(root, "tag", "base")
    _git(root, "tag", "head-v1")
    return root


def _check(
    repo_path: Path,
    tmp_path: Path,
    *,
    ref: str = "base",
    **kwargs: object,
) -> SafetyReport:
    return check_repo_safety(
        str(repo_path), ref, tmp_path / "ws", **kwargs
    )


def _get(report: SafetyReport, name: str) -> SafetyCheck:
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(f"check {name!r} missing from report: {report}")


class _StubRunner:
    """Recorded git runner with scripted results."""

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "abcdef123456\n",
        stderr: str = "",
        raise_exc: Exception | None = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.raise_exc = raise_exc

    def __call__(self, argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        if self.raise_exc is not None:
            raise self.raise_exc
        return subprocess.CompletedProcess(
            list(argv), self.returncode, self.stdout, self.stderr
        )


class TestReportContract:
    def test_all_checks_pass_on_clean_repo(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path)
        assert report.ok is True
        assert report.fail_reason == ""
        assert [c.name for c in report.checks] == list(CHECK_NAMES)
        assert all(c.passed for c in report.checks)

    def test_local_mode_without_allowed_root_warns(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path)
        assert report.ok is True
        assert any("allowed root not configured" in w for w in report.warnings)
        check = _get(report, CHECK_REPO_UNDER_ALLOWED_ROOT)
        assert check.passed is True
        assert "not enforced" in check.detail

    def test_unknown_check_fails_closed(self, repo: Path, tmp_path: Path) -> None:
        report = check_repo_safety(
            str(repo), "base", tmp_path / "ws", checks=["no_such_check"],
        )
        assert report.ok is False
        assert "no_such_check" in report.fail_reason
        assert len(report.checks) == 1
        assert report.checks[0].passed is False
        assert "unknown check" in report.checks[0].detail

    def test_unknown_check_alongside_known_still_fails(
        self, repo: Path, tmp_path: Path
    ) -> None:
        report = check_repo_safety(
            str(repo), "base", tmp_path / "ws",
            checks=["ref_in_repo", "bogus-check"],
        )
        assert report.ok is False
        assert [c.name for c in report.checks] == ["ref_in_repo", "bogus-check"]
        assert report.checks[0].passed is True  # known check still ran

    def test_check_subset_runs_only_requested(
        self, repo: Path, tmp_path: Path
    ) -> None:
        report = check_repo_safety(
            str(repo), "base", tmp_path / "ws",
            checks=["worktree_target_empty"],
        )
        assert [c.name for c in report.checks] == ["worktree_target_empty"]
        assert report.ok is True


class TestRepoUnderAllowedRoot:
    def test_repo_outside_allowed_root_fails(self, repo: Path, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        report = _check(repo, tmp_path, allowed_root=allowed)
        assert report.ok is False
        check = _get(report, CHECK_REPO_UNDER_ALLOWED_ROOT)
        assert check.passed is False
        assert "outside allowed root" in check.detail

    def test_repo_inside_allowed_root_passes(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, allowed_root=tmp_path)
        assert _get(report, CHECK_REPO_UNDER_ALLOWED_ROOT).passed is True

    def test_missing_repo_fails(self, tmp_path: Path) -> None:
        report = check_repo_safety(
            str(tmp_path / "nope"), "base", tmp_path / "ws",
        )
        check = _get(report, CHECK_REPO_UNDER_ALLOWED_ROOT)
        assert check.passed is False
        assert "does not exist" in check.detail

    def test_missing_allowed_root_fails(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, allowed_root=tmp_path / "ghost")
        check = _get(report, CHECK_REPO_UNDER_ALLOWED_ROOT)
        assert check.passed is False
        assert "not a directory" in check.detail


class TestRefInRepo:
    def test_ref_resolves_pass(self, repo: Path, tmp_path: Path) -> None:
        check = _get(_check(repo, tmp_path, ref="base"), "ref_in_repo")
        assert check.passed is True
        assert "resolves" in check.detail

    def test_unknown_ref_fails(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, ref="no-such-ref")
        check = _get(report, "ref_in_repo")
        assert check.passed is False
        assert "does not belong" in check.detail
        assert report.ok is False

    def test_empty_ref_fails(self, repo: Path, tmp_path: Path) -> None:
        check = _get(_check(repo, tmp_path, ref=""), "ref_in_repo")
        assert check.passed is False

    def test_runner_exception_fails_closed(self, repo: Path, tmp_path: Path) -> None:
        runner = _StubRunner(raise_exc=RuntimeError("boom"))
        report = check_repo_safety(
            str(repo), "base", tmp_path / "ws", git_runner=runner,
        )
        check = _get(report, "ref_in_repo")
        assert check.passed is False
        assert "git runner failed" in check.detail

    def test_git_nonzero_fails_closed(self, repo: Path, tmp_path: Path) -> None:
        runner = _StubRunner(returncode=128, stdout="", stderr="fatal: bad ref")
        report = check_repo_safety(
            str(repo), "base", tmp_path / "ws", git_runner=runner,
        )
        check = _get(report, "ref_in_repo")
        assert check.passed is False
        assert "fatal: bad ref" in check.detail

    def test_injected_runner_receives_expected_argv(
        self, repo: Path, tmp_path: Path
    ) -> None:
        import os

        runner = _StubRunner()
        check_repo_safety(
            str(repo), "base", tmp_path / "ws", git_runner=runner,
        )
        expected_c = os.path.realpath(os.fspath(repo.resolve()))
        assert runner.calls == [
            ["-C", expected_c, "rev-parse", "--verify", "--quiet", "base^{commit}"],
        ]


class TestWorktreeTarget:
    def test_absent_target_passes(self, repo: Path, tmp_path: Path) -> None:
        check = _get(_check(repo, tmp_path), "worktree_target_empty")
        assert check.passed is True

    def test_empty_dir_target_passes(self, repo: Path, tmp_path: Path) -> None:
        target = tmp_path / "ws"
        target.mkdir()
        check = _get(_check(repo, tmp_path), "worktree_target_empty")
        assert check.passed is True

    def test_nonempty_target_fails(self, repo: Path, tmp_path: Path) -> None:
        target = tmp_path / "ws"
        target.mkdir()
        (target / "stray.txt").write_text("x", encoding="utf-8")
        check = _get(_check(repo, tmp_path), "worktree_target_empty")
        assert check.passed is False
        assert "not empty" in check.detail

    def test_file_target_fails(self, repo: Path, tmp_path: Path) -> None:
        target = tmp_path / "ws"
        target.write_text("x", encoding="utf-8")
        check = _get(_check(repo, tmp_path), "worktree_target_empty")
        assert check.passed is False
        assert "not a directory" in check.detail


class TestSymlinkEscape:
    def _make_junction(self, link: Path, target: Path) -> bool:
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True, text=True,
        )
        return made.returncode == 0

    def test_junction_escape_detected(self, repo: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        if not self._make_junction(repo / "escape", outside):
            pytest.skip("junction creation not permitted on this machine")
        report = _check(repo, tmp_path)
        check = _get(report, CHECK_NO_SYMLINK_ESCAPE)
        assert check.passed is False
        assert "escapes" in check.detail

    def test_junction_inside_repo_passes(self, repo: Path, tmp_path: Path) -> None:
        inner = repo / "subdir"
        inner.mkdir()
        (inner / "f.txt").write_text("x", encoding="utf-8")
        if not self._make_junction(repo / "loop", inner):
            pytest.skip("junction creation not permitted on this machine")
        report = _check(repo, tmp_path)
        assert _get(report, CHECK_NO_SYMLINK_ESCAPE).passed is True
        # The walk prunes the junction: subdir files are counted once.
        assert _get(report, CHECK_REPO_SIZE_WITHIN_LIMIT).passed is True


class TestRepoSize:
    def test_explicit_limit_too_small_fails(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, max_repo_bytes=1)
        check = _get(report, CHECK_REPO_SIZE_WITHIN_LIMIT)
        assert check.passed is False
        assert "exceeds limit" in check.detail

    def test_env_limit_overrides_default(self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(MAX_REPO_BYTES_ENV, "1")
        report = _check(repo, tmp_path)
        assert _get(report, CHECK_REPO_SIZE_WITHIN_LIMIT).passed is False

    def test_bad_env_limit_warns_and_uses_default(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(MAX_REPO_BYTES_ENV, "not-a-number")
        report = _check(repo, tmp_path)
        assert report.ok is True
        assert any("is not an integer" in w for w in report.warnings)


class TestForbiddenFiles:
    def test_env_file_fails(self, repo: Path, tmp_path: Path) -> None:
        (repo / ".env").write_text("LLM_API_KEY=replace_me\n", encoding="utf-8")
        check = _get(_check(repo, tmp_path), CHECK_NO_FORBIDDEN_FILES)
        assert check.passed is False
        assert ".env" in check.detail

    def test_key_material_name_fails(self, repo: Path, tmp_path: Path) -> None:
        (repo / "server.key").write_text("whatever\n", encoding="utf-8")
        check = _get(_check(repo, tmp_path), CHECK_NO_FORBIDDEN_FILES)
        assert check.passed is False

    def test_id_rsa_fails(self, repo: Path, tmp_path: Path) -> None:
        (repo / "id_rsa").write_text("private\n", encoding="utf-8")
        check = _get(_check(repo, tmp_path), CHECK_NO_FORBIDDEN_FILES)
        assert check.passed is False

    def test_env_local_variant_forbidden_by_name(
        self, repo: Path, tmp_path: Path
    ) -> None:
        (repo / ".env.local").write_text("A=1\n", encoding="utf-8")
        check = _get(_check(repo, tmp_path), CHECK_NO_FORBIDDEN_FILES)
        assert check.passed is False

    def test_env_example_placeholder_passes(self, repo: Path, tmp_path: Path) -> None:
        (repo / ".env.example").write_text(
            "LLM_API_KEY=replace_me\n", encoding="utf-8",
        )
        report = _check(repo, tmp_path)
        assert _get(report, CHECK_NO_FORBIDDEN_FILES).passed is True
        assert report.ok is True

    def test_env_example_with_key_token_fails(self, repo: Path, tmp_path: Path) -> None:
        fake_key = FAKE_KEY_PREFIX + ("a" * 32)
        (repo / ".env.example").write_text(
            "LLM_API_KEY=" + fake_key + "\n", encoding="utf-8",
        )
        check = _get(_check(repo, tmp_path), CHECK_NO_FORBIDDEN_FILES)
        assert check.passed is False
        assert "API-key-shaped" in check.detail

    def test_env_template_with_private_key_block_fails(
        self, repo: Path, tmp_path: Path
    ) -> None:
        (repo / ".env.template").write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nAAAA\n"
            "-----END RSA PRIVATE KEY-----\n",
            encoding="utf-8",
        )
        check = _get(_check(repo, tmp_path), CHECK_NO_FORBIDDEN_FILES)
        assert check.passed is False
        assert "private key block" in check.detail

    def test_key_token_in_ordinary_file_is_not_content_scanned(
        self, repo: Path, tmp_path: Path
    ) -> None:
        # Content scanning is scoped to name-matched .env template files:
        # ordinary files (like test fixtures) are not secret-scanned here.
        fake_key = FAKE_KEY_PREFIX + ("b" * 32)
        (repo / "notes.txt").write_text("token=" + fake_key + "\n", encoding="utf-8")
        report = _check(repo, tmp_path)
        assert _get(report, CHECK_NO_FORBIDDEN_FILES).passed is True


class TestExecutionModeSignal:
    def test_unknown_mode_fails_closed(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, exec_mode="yolo")
        check = _get(report, CHECK_EXECUTION_MODE_SIGNAL)
        assert check.passed is False
        assert "unknown execution mode" in check.detail

    def test_sandbox_without_root_fails(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, exec_mode="sandbox")
        assert _get(report, CHECK_REPO_UNDER_ALLOWED_ROOT).passed is False
        assert _get(report, CHECK_EXECUTION_MODE_SIGNAL).passed is False

    def test_sandbox_with_root_passes(self, repo: Path, tmp_path: Path) -> None:
        report = _check(repo, tmp_path, exec_mode="sandbox", allowed_root=tmp_path)
        assert report.ok is True
        assert "sandbox" in _get(report, CHECK_EXECUTION_MODE_SIGNAL).detail

    def test_env_exec_mode_respected(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SPECPROOF_EXEC_MODE", "sandbox")
        report = _check(repo, tmp_path, allowed_root=tmp_path)
        assert _get(report, CHECK_EXECUTION_MODE_SIGNAL).passed is True
        monkeypatch.setenv("SPECPROOF_EXEC_MODE", "container-typo")
        report = _check(repo, tmp_path, allowed_root=tmp_path)
        assert _get(report, CHECK_EXECUTION_MODE_SIGNAL).passed is False

    def test_env_allowed_root_respected(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ALLOWED_ROOT_ENV, str(tmp_path))
        report = _check(repo, tmp_path, exec_mode="sandbox")
        assert report.ok is True
        assert not any("not configured" in w for w in report.warnings)


class TestPrepareNodeWiring:
    def _fail_report(self, fail_reason: str) -> SafetyReport:
        return SafetyReport(
            ok=False,
            checks=[
                SafetyCheck(CHECK_NO_FORBIDDEN_FILES, False, "forbidden file"),
            ],
            warnings=[],
            fail_reason=fail_reason,
        )

    def test_prepare_base_aborts_with_check_name(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent.nodes.prepare_base as module

        monkeypatch.setattr(
            module, "check_repo_safety",
            lambda **kwargs: self._fail_report(
                "no_forbidden_files: forbidden file in repository (.env/key patterns)"
            ),
        )
        ran: list[list[str]] = []
        monkeypatch.setattr(
            module.subprocess, "run",
            lambda argv, **kwargs: ran.append(argv) or subprocess.CompletedProcess(
                argv, 0, "", ""
            ),
        )
        result = module.prepare_base_node(
            {"repo_path": str(repo), "base_ref": "base", "errors": [], "job_id": "j1"}
        )
        assert result["base_workspace"] == ""
        assert len(result["errors"]) == 1
        assert "no_forbidden_files" in result["errors"][0]
        assert ran == []  # git never invoked

    def test_prepare_head_aborts_with_check_name(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent.nodes.prepare_head as module

        monkeypatch.setattr(
            module, "check_repo_safety",
            lambda **kwargs: self._fail_report("repo_under_allowed_root: outside"),
        )
        ran: list[list[str]] = []
        monkeypatch.setattr(
            module.subprocess, "run",
            lambda argv, **kwargs: ran.append(argv) or subprocess.CompletedProcess(
                argv, 0, "", ""
            ),
        )
        result = module.prepare_head_node(
            {"repo_path": str(repo), "head_ref": "head-v1", "errors": [], "job_id": "j2"}
        )
        assert result["head_workspace"] == ""
        assert "repo_under_allowed_root" in result["errors"][0]
        assert ran == []

    def test_prepare_base_success_creates_worktree_and_marker(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        import agent.nodes.prepare_base as module
        from agent.worktree_reclaimer import MARKER_KIND, MARKER_VERSION

        temp_root = tmp_path / "tmp"
        temp_root.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

        result = module.prepare_base_node(
            {"repo_path": str(repo), "base_ref": "base", "errors": [], "job_id": "job-1"}
        )
        assert result["base_workspace"]
        workspace = Path(result["base_workspace"])
        try:
            assert (workspace / "file.txt").exists()
            markers = list(temp_root.glob(".specproof-worktree-*.json"))
            assert len(markers) == 1
            data = json.loads(markers[0].read_text(encoding="utf-8"))
            assert data["kind"] == MARKER_KIND
            assert data["version"] == MARKER_VERSION
            assert data["job_id"] == "job-1"
            assert data["worktree_path"] == str(workspace.resolve())
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force",
                 str(workspace)],
                capture_output=True, text=True, timeout=60,
            )
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "prune"],
                capture_output=True, text=True, timeout=60,
            )

    def test_prepare_head_success_creates_worktree_and_marker(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent.nodes.prepare_head as module

        temp_root = tmp_path / "tmp"
        temp_root.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

        result = module.prepare_head_node(
            {"repo_path": str(repo), "head_ref": "head-v1", "errors": [], "job_id": "job-2"}
        )
        assert result["head_workspace"]
        workspace = Path(result["head_workspace"])
        try:
            assert (workspace / "file.txt").exists()
            assert len(list(temp_root.glob(".specproof-worktree-*.json"))) == 1
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force",
                 str(workspace)],
                capture_output=True, text=True, timeout=60,
            )
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "prune"],
                capture_output=True, text=True, timeout=60,
            )

    def test_prepare_base_git_failure_cleans_up(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import agent.nodes.prepare_base as module

        temp_root = tmp_path / "tmp"
        temp_root.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
        monkeypatch.setattr(
            module.subprocess, "run",
            lambda argv, **kwargs: subprocess.CompletedProcess(argv, 128, "", "boom"),
        )
        result = module.prepare_base_node(
            {"repo_path": str(repo), "base_ref": "base", "errors": [], "job_id": "job-3"}
        )
        assert result["base_workspace"] == ""
        assert result["errors"]
        # Empty workspace dir and its marker are discarded on failure.
        assert list(temp_root.glob(".specproof-worktree-*.json")) == []
        assert list(temp_root.iterdir()) == []
