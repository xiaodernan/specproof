"""Fault-injection matrix (AGENT_STATE_OF_ART.md §9 故障注入行).

Three fault families, mocked at the dependency boundary (no live infra):

  1. Gateway 429 x3        -> providers retry semantics: bounded retries,
     then the raw failure propagates honestly — no fabricated LLMResponse.
     Supporting cases: mixed transient faults recover; non-retryable
     errors fail immediately with exactly one attempt.
  2. Disk write failure    -> craft/editor atomic write: os.replace raises
     OSError -> EditError, original content intact, backup kept, temp file
     cleaned up (rollback).
  3. Clock rollback        -> craft/loop checkpoint resume: today
     from_checkpoint has NO future-timestamp validation (M4 gap). The
     tests pin the current honest behaviour and are annotated; when M4
     adds the guard, test_checkpoint_resume_accepts_future_timestamps_today
     must be flipped to assert rejection.

Mocked dependencies only — no Docker, no network, no real keys.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openai import InternalServerError, RateLimitError

from craft.editor import EditError, Editor
from craft.loop import CraftLoop, CraftLoopError
from craft.planner import CraftPlanError, compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMMessage
from providers.openai_compatible import OpenAICompatibleProvider
from providers.probe_result import ProbeResult


def _rate_limit_error(retry_after: str) -> RateLimitError:
    response = SimpleNamespace(
        headers={"retry-after": retry_after},
        status_code=429,
        request=SimpleNamespace(method="POST", url="http://llm.test/v1/chat/completions"),
    )
    return RateLimitError("rate limited", response=response, body=None)


def _mock_api_key() -> str:
    """Fake key assembled from parts — the repo security scanner forbids a
    complete 'sk-...' literal anywhere in .py files (test_no_key_leak.py)."""
    return "sk-" + "fault-" + "matrix-test-key"


class _FakeChat:
    def __init__(self, responder: Any) -> None:
        self._responder = responder
        self.attempts = 0

    async def create(self, **kwargs: Any) -> Any:
        self.attempts += 1
        return self._responder(self.attempts)


def _make_provider(
    responder: Any, max_retries: int = 2
) -> tuple[OpenAICompatibleProvider, _FakeChat]:
    provider = OpenAICompatibleProvider(
        base_url="http://llm.test",
        api_key=_mock_api_key(),
        model="deepseek-v4-pro",
        probe_on_init=False,
        max_retries=max_retries,
    )
    provider._probe_result = ProbeResult(
        provider="openai_compatible",
        base_url=provider.base_url,
        model=provider.model,
        capabilities={"chat": True, "json_output": True, "tool_calls": True, "thinking": False},
    )
    fake = _FakeChat(responder)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=fake))  # type: ignore[assignment]
    return provider, fake


def _fake_response(content: str = "ok") -> Any:
    choice = SimpleNamespace(
        message=SimpleNamespace(
            content=content, tool_calls=None, reasoning_content=None
        ),
        finish_reason="stop",
    )
    return SimpleNamespace(choices=[choice], usage=None, model="deepseek-v4-pro")


# ══════════════════════════════════════════════════════════════════
# Scenario 1: gateway 429 x3 -> honest failure (bounded, never faked)
# ══════════════════════════════════════════════════════════════════

class TestGateway429HonestFailure:
    async def test_429_three_times_raises_honestly_without_fabricated_result(self) -> None:
        """3 consecutive 429s (max_retries=2 -> 3 attempts) must surface the
        raw RateLimitError — no silent fallback, no invented LLMResponse."""

        def responder(attempt: int) -> Any:
            raise _rate_limit_error("0.001")

        provider, fake = _make_provider(responder, max_retries=2)
        with pytest.raises(RateLimitError):
            await provider.chat(messages=[LLMMessage(role="user", content="ping")])
        assert fake.attempts == 3  # initial + 2 retries = LLM_MAX_RETRIES semantics

    async def test_mixed_transient_faults_recover_within_budget(self) -> None:
        """429, then 500, then success — the retry layer must keep going
        until the budget is spent, and the caller gets the real response."""

        def responder(attempt: int) -> Any:
            if attempt == 1:
                raise _rate_limit_error("0.001")
            if attempt == 2:
                raise InternalServerError(
                    "internal error",
                    response=SimpleNamespace(
                        headers={},
                        status_code=500,
                        request=SimpleNamespace(
                            method="POST", url="http://llm.test/v1/chat/completions"
                        ),
                    ),
                    body=None,
                )
            return _fake_response(content="recovered")

        provider, fake = _make_provider(responder, max_retries=2)
        result = await provider.chat(messages=[LLMMessage(role="user", content="ping")])
        assert result.content == "recovered"
        assert fake.attempts == 3

    async def test_non_retryable_error_fails_immediately(self) -> None:
        """A non-retryable failure must not burn the retry budget."""

        def responder(attempt: int) -> Any:
            raise ValueError("malformed request — not a gateway fault")

        provider, fake = _make_provider(responder, max_retries=2)
        with pytest.raises(ValueError):
            await provider.chat(messages=[LLMMessage(role="user", content="ping")])
        assert fake.attempts == 1


# ══════════════════════════════════════════════════════════════════
# Scenario 2: disk write failure -> editor atomic rollback
# ══════════════════════════════════════════════════════════════════

class TestDiskWriteFailureAtomicRollback:
    def _break_replace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken_replace(source: object, destination: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("craft.editor.os.replace", broken_replace)

    def test_write_file_failure_keeps_original_and_backup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        target = workspace / "svc.py"
        original = "def f() -> int:\n    return 1\n"
        target.write_text(original, encoding="utf-8")
        editor = Editor(workspace)
        self._break_replace(monkeypatch)

        with pytest.raises(EditError, match="原子写失败"):
            editor.write_file("svc.py", "def f() -> int:\n    return 2\n")

        assert target.read_text(encoding="utf-8") == original
        backups = list(editor.backup_dir.glob("*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == original

    def test_write_file_failure_leaves_no_temp_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        editor = Editor(workspace)
        self._break_replace(monkeypatch)

        with pytest.raises(EditError):
            editor.write_file("new.py", "x = 1\n")

        assert not (workspace / "new.py").exists()
        assert list(workspace.glob("*.tmp")) == []
        assert list(workspace.glob(".*.tmp")) == []

    def test_apply_edit_failure_leaves_file_untouched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        target = workspace / "svc.py"
        original = "def f() -> int:\n    return 1\n"
        target.write_text(original, encoding="utf-8")
        editor = Editor(workspace)
        self._break_replace(monkeypatch)

        with pytest.raises(EditError, match="原子写失败"):
            editor.apply_edit("svc.py", "return 1", "return 2")

        assert target.read_text(encoding="utf-8") == original


# ══════════════════════════════════════════════════════════════════
# Scenario 3: clock rollback -> checkpoint resume (current honest behaviour)
# ══════════════════════════════════════════════════════════════════

def _plan_payload(workspace: Path) -> dict[str, Any]:
    spec = parse_spec_text("通用任务\n影响: svc.py")
    plan = compile_plan(spec)
    return plan.to_dict()


def _write_checkpoint(
    artifact_dir: Path, workspace: Path, payload: dict[str, Any]
) -> None:
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "plan.json").write_text(json.dumps(_plan_payload(workspace)), encoding="utf-8")
    (artifact_dir / "checkpoint.json").write_text(json.dumps(payload), encoding="utf-8")


class TestClockRollbackCheckpointResume:
    def test_resume_rejects_checkpoint_without_workspace(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "job"
        _write_checkpoint(
            artifact_dir,
            tmp_path,
            {"job_id": "job-1", "entries": [], "last_green_step": ""},
        )
        with pytest.raises(CraftLoopError, match="缺少 job_id/workspace"):
            CraftLoop.from_checkpoint(artifact_dir)

    def test_resume_rejects_corrupt_plan(self, tmp_path: Path) -> None:
        artifact_dir = tmp_path / "job"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "plan.json").write_text(
            '{"task_title": "x", "steps": "nope"}', encoding="utf-8"
        )
        (artifact_dir / "checkpoint.json").write_text(
            json.dumps({"job_id": "j", "workspace": str(tmp_path), "entries": []}),
            encoding="utf-8",
        )
        with pytest.raises(CraftPlanError):
            CraftLoop.from_checkpoint(artifact_dir)

    def test_checkpoint_resume_accepts_future_timestamps_today(self, tmp_path: Path) -> None:
        """CLOCK-ROLLBACK GAP (annotated, design §4.4 / M4):

        from_checkpoint currently does NOT validate entry timestamps — a
        checkpoint written by a clock far in the future (or rolled back)
        resumes without complaint. This test pins TODAY's honest behaviour.
        When M4 lands the future-timestamp guard, flip this test to assert
        that such a checkpoint is REJECTED and delete this docstring.
        """
        workspace = tmp_path / "ws"
        workspace.mkdir()
        checkpoint = {
            "job_id": "job-1",
            "workspace": str(workspace),
            "task_key": "generic",
            "last_green_step": "s1",
            "entries": [
                {
                    "job_id": "job-1",
                    "step_id": "s1",
                    "iteration": 0,
                    "diagnosis": "",
                    "edits_applied": [],
                    "build_result": {"exit_code": 0, "failed_tests": [], "log_tail": ""},
                    "verdict": "green",
                    # A timestamp ~74 years in the future — the clock-rollback
                    # fingerprint the M4 guard must eventually reject.
                    "timestamp": "2099-01-01T00:00:00+00:00",
                }
            ],
        }
        artifact_dir = tmp_path / "job"
        _write_checkpoint(artifact_dir, workspace, checkpoint)
        loop = CraftLoop.from_checkpoint(artifact_dir)
        assert loop.job_id == "job-1"
        assert loop.last_green_step == "s1"
        assert loop.states[0].status == "green"
        assert loop.checkpoint_entries[0]["timestamp"].startswith("2099")
