"""Offline regression tests for the first-real-run gap fixes (no network/Docker/LLM).

Covers the two capability gaps exposed by docs/eval/swebench-llm-results.json
(the honest 0% first LLM run):

- edit-proposal generation/parsing: a code-fenced JSON proposal parses and
  applies; a non-JSON / missing-"edits" proposal arms exactly ONE repair
  instruction (ToolCallSelfCheck pattern); a second failure fails with the
  stable code LLM_PROPOSAL_INVALID; the diagnose call requests json_object
  mode and the provider sends response_format only when its capability
  probe reports json_output;
- verify no-output: run_test surfaces stderr + exit code (never a silent
  empty result), a spawn/sandbox failure rides the output, venv creation /
  missing-pytest failures are explicit errors, and the harness falls back
  to --no-venv with the reason recorded.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import sandbox.runner as sandbox_runner
from craft.executor import Executor
from craft.llm import LLMClient, extract_json_object
from craft.loop import CraftLoop
from craft.planner import compile_plan
from craft.spec import parse_spec_text
from craft.tools import ToolRegistry
from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider
from providers.probe_result import ProbeResult
from providers.toolcheck import (
    CODE_PROPOSAL_INVALID,
    EditProposalSelfCheck,
    ProposalParseFailure,
    edit_retry_instruction,
    validate_edit_proposal,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCH_SCRIPT = REPO_ROOT / "scripts" / "bench_swebench.py"

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

VALID_EDIT_JSON = json.dumps(
    {
        "diagnosis": "double() 把乘法写成了除法, 翻转操作符即可",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x / 2",
                "new": "return x * 2",
            }
        ],
    },
    ensure_ascii=False,
)


def _write_fixture_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
        '    return "hello " + name\n',
        encoding="utf-8",
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; records every prompt and
    the response_format kwarg the loop passed (the json_object contract)."""

    def __init__(self, replies: list[str], *, job_id: str = "job-fixes") -> None:
        super().__init__(provider=None, token_budget=100_000, job_id=job_id)
        self._replies = list(replies)
        self.sent_prompts: list[str] = []
        self.response_formats: list[dict[str, Any] | None] = []

    def chat_sync(
        self,
        messages: list[LLMMessage],
        *,
        label: str,
        kind: str | None = None,
        job_id: str = "",
        step_id: str = "",
        thinking: bool = False,
        response_format: dict[str, Any] | None = None,
        estimated_prompt_tokens: int = 0,
        timeout: float | None = None,
    ) -> LLMResponse:
        del kind, job_id, step_id, thinking, estimated_prompt_tokens, timeout
        self.sent_prompts.append(messages[0].content)
        self.response_formats.append(response_format)
        reply = self._replies[min(len(self.sent_prompts) - 1, len(self._replies) - 1)]
        usage = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        entry = self.budget.record(usage, label=label)
        self.calls.append({**entry, "job_id": self.job_id, "model": "fake-fixes"})
        return LLMResponse(content=reply, usage=usage, model="fake-fixes")


def _run_llm_loop(
    tmp_path: Path, replies: list[str]
) -> tuple[CraftLoop, _ScriptedClient, dict[str, Any]]:
    _write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    client = _ScriptedClient(replies)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-fixes",
        fix_registry={},
        exec_mode="local",
        client=client,
    )
    return loop, client, loop.run()


def _load_harness() -> Any:
    """Import scripts/bench_swebench.py as a fresh module for in-process runs."""
    spec = importlib.util.spec_from_file_location(
        "bench_swebench_fixes_under_test", BENCH_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _completed(command: list[str], code: int, out: str, err: str) -> Any:
    return subprocess.CompletedProcess(command, code, out, err)


# -- (a) code-fenced JSON parses and applies -----------------------------------

FENCE = chr(96) * 3


def test_extract_json_object_code_fenced() -> None:
    reply = (
        FENCE + 'json\n{"diagnosis": "d", "edits": '
        '[{"action": "write_file", "path": "x.py", "new": "x = 1"}]}\n' + FENCE
    )
    data = extract_json_object(reply)
    assert isinstance(data, dict)
    assert data["diagnosis"] == "d"
    assert data["edits"][0]["action"] == "write_file"


def test_extract_json_object_first_balanced_value_with_prose() -> None:
    reply = 'reasoning before\n{"a": 1} trailing {"b": 2}'
    assert extract_json_object(reply) == {"a": 1}


def test_loop_applies_code_fenced_proposal(tmp_path: Path) -> None:
    _loop, client, report = _run_llm_loop(
        tmp_path, [FENCE + "json\n" + VALID_EDIT_JSON + "\n" + FENCE]
    )
    assert report["result"] == "DONE"
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert len(client.sent_prompts) == 1  # valid on the first try: no repair call


# -- (b) non-JSON -> ONE repair instruction, then stable code ------------------


def test_non_json_proposal_arms_one_repair_then_fails_with_stable_code(
    tmp_path: Path,
) -> None:
    _loop, client, report = _run_llm_loop(
        tmp_path, ["not json at all", "still not json"]
    )
    assert report["result"] == "FAILED"
    failed = [step for step in report["steps"] if step["status"] == "failed"]
    assert len(failed) == 1
    reason = str(failed[0]["evidence"]["reason"])
    assert "[LLM_PROPOSAL_INVALID]" in reason
    assert len(client.sent_prompts) == 2  # exactly ONE repair round-trip
    assert "EDIT PROPOSAL SELF-CHECK" in client.sent_prompts[1]
    assert client.response_formats == [
        {"type": "json_object"},
        {"type": "json_object"},
    ]
    assert "return x / 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_missing_edits_array_repairs_then_converges(tmp_path: Path) -> None:
    bad = json.dumps({"diagnosis": "root cause", "changes": []})
    _loop, client, report = _run_llm_loop(tmp_path, [bad, VALID_EDIT_JSON])
    assert report["result"] == "DONE"
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert len(client.sent_prompts) == 2
    assert "EDIT PROPOSAL SELF-CHECK" in client.sent_prompts[1]
    assert "缺少 edits 数组" in client.sent_prompts[1]


def test_edit_proposal_self_check_one_retry_then_give_up() -> None:
    checker = EditProposalSelfCheck()
    instructions: list[str | None] = []

    def produce(instruction: str | None) -> object:
        instructions.append(instruction)
        return {"action": "apply_edit"}

    outcome = checker.check_with_retry(produce)
    assert outcome.status == "give_up"
    assert outcome.code == CODE_PROPOSAL_INVALID
    assert instructions[0] is None
    assert "[LLM_PROPOSAL_INVALID]" in (instructions[1] or "")
    assert checker.metrics()["give_ups"] == 1


def test_validate_edit_proposal_accepts_envelope_and_bare_list() -> None:
    good = {
        "diagnosis": "d",
        "edits": [{"action": "apply_edit", "path": "a.py", "old": "x", "new": "y"}],
    }
    assert validate_edit_proposal(good).status == "valid"
    bare = [{"action": "write_file", "path": "b.py", "new": "z"}]
    assert validate_edit_proposal(bare).status == "valid"


def test_edit_retry_instruction_names_the_json_schema() -> None:
    outcome = validate_edit_proposal(ProposalParseFailure("unparseable tail..."))
    text = edit_retry_instruction(outcome)
    assert "EDIT PROPOSAL SELF-CHECK" in text
    assert '"edits"' in text
    assert "json" in text.lower()  # gateway only honors json_object with JSON named


# -- (c) json_object mode when the capability allows --------------------------


def test_diagnose_requests_json_object_mode_and_names_json(tmp_path: Path) -> None:
    _loop, client, report = _run_llm_loop(tmp_path, [VALID_EDIT_JSON])
    assert report["result"] == "DONE"
    assert client.response_formats == [{"type": "json_object"}]
    prompt = client.sent_prompts[0]
    assert "JSON" in prompt
    assert '"edits"' in prompt
    assert "JSON Action Envelope" not in prompt  # the conflicting contract is gone


class _RecordingResponder:
    """Stub chat.completions.create: records kwargs, replays canned content."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content=self.content, reasoning_content=None, tool_calls=[]
                    ),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            model="fake-provider",
        )


class _FakeCompletions:
    def __init__(self, responder: _RecordingResponder) -> None:
        self._responder = responder

    async def create(self, **kwargs: Any) -> Any:
        return await self._responder(**kwargs)


class _FakeChat:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.completions = _FakeCompletions(responder)


class _FakeSDKClient:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.chat = _FakeChat(responder)

    async def close(self) -> None:
        return None


def _make_provider(
    responder: _RecordingResponder, json_cap: bool
) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(
        base_url="http://llm.test",
        api_key="fake-" + "key-1234567890abcdef",
        model="fake-model",
        probe_on_init=False,
        max_retries=0,
    )
    provider._probe_result = ProbeResult(
        provider="openai_compatible",
        base_url=provider.base_url,
        model=provider.model,
        capabilities={"chat": True, "json_output": json_cap, "thinking": False},
    )
    provider._client = _FakeSDKClient(responder)
    return provider


async def test_provider_sends_json_object_only_when_capability_present() -> None:
    responder = _RecordingResponder('{"diagnosis": "d", "edits": []}')
    provider = _make_provider(responder, json_cap=True)
    await provider.chat(
        [LLMMessage(role="user", content="Return the JSON edits proposal")],
        response_format={"type": "json_object"},
    )
    assert responder.calls[0]["response_format"] == {"type": "json_object"}

    responder_without_cap = _RecordingResponder("{}")
    provider_without_cap = _make_provider(responder_without_cap, json_cap=False)
    await provider_without_cap.chat(
        [LLMMessage(role="user", content="Return the edits proposal")],
        response_format={"type": "json_object"},
    )
    assert "response_format" not in responder_without_cap.calls[0]


# -- (d) run_test surfaces stderr + exit code instead of empty -----------------


def test_run_test_surfaces_stderr_and_exit_code(tmp_path: Path) -> None:
    registry = ToolRegistry(tmp_path, executor=Executor(tmp_path, mode="local"))
    result = registry.dispatch(
        registry.build_tool_call(
            "run_test",
            {
                "command": [
                    sys.executable,
                    "-c",
                    "import sys; print('boom', file=sys.stderr); sys.exit(3)",
                ]
            },
        )
    )
    assert result.status == "ok"
    assert result.exit_code == 3
    assert "exit code 3" in result.summary
    assert "boom" in result.output_head + result.output_tail


def test_run_test_spawn_failure_is_never_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise OSError("spawn exploded")

    monkeypatch.setattr(sandbox_runner.subprocess, "run", boom)
    registry = ToolRegistry(tmp_path, executor=Executor(tmp_path, mode="local"))
    result = registry.dispatch(
        registry.build_tool_call(
            "run_test", {"command": [sys.executable, "-c", "print(1)"]}
        )
    )
    assert result.status == "ok"
    assert result.exit_code == -1
    combined = result.output_head + result.output_tail
    assert "could not start" in combined
    assert "spawn exploded" in combined


def test_executor_injects_sandbox_error_into_output_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_local(
        command: list[str], workspace: str, timeout: int, mode: str
    ) -> sandbox_runner.SandboxResult:
        del command, workspace, timeout
        return sandbox_runner.SandboxResult(
            exit_code=-1, stdout="", stderr="", error="venv python missing", mode=mode
        )

    monkeypatch.setattr(sandbox_runner, "_run_local", fake_local)
    result = Executor(tmp_path, mode="local").run(["python", "-m", "pytest", "-q"])
    assert result.exit_code == -1
    assert "[sandbox error] venv python missing" in result.output_tail
    assert result.output_tail.strip()


def test_executor_python_override_substitutes_pytest_stem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []

    def fake_local(
        command: list[str], workspace: str, timeout: int, mode: str
    ) -> sandbox_runner.SandboxResult:
        del workspace, timeout
        captured.append(list(command))
        return sandbox_runner.SandboxResult(exit_code=0, stdout="ok", stderr="", mode=mode)

    monkeypatch.setattr(sandbox_runner, "_run_local", fake_local)
    Executor(tmp_path, mode="local", python="C:/venv/python.exe").run(
        ["python", "-m", "pytest", "-q"]
    )
    assert captured[0][0] == "C:/venv/python.exe"


# -- (e) venv failure -> explicit error + --no-venv fallback -------------------


def test_venv_creation_failure_is_explicit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_harness()

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        del kwargs
        if command[:3] == [sys.executable, "-m", "venv"]:
            raise OSError("venv bootstrap exploded")
        return _completed(command, 0, "ok", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    info = module._prepare_venv(tmp_path, enabled=True, timeout=30)
    assert info["python"] == ""
    assert "venv 创建失败" in info["error"]
    assert "venv bootstrap exploded" in info["error"]


def test_fallback_no_venv_keeps_reason_and_flags_fallback() -> None:
    module = _load_harness()
    fallback = module._fallback_no_venv(
        {"python": "", "error": "venv 创建失败: boom", "note": ""}
    )
    assert fallback["python"] == ""
    assert fallback["error"] == "venv 创建失败: boom"
    assert fallback["fallback_no_venv"] == "true"
    assert "--no-venv 回退" in fallback["note"]


def test_prepare_venv_missing_pytest_is_explicit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_harness()
    venv_dir = tmp_path / "venv"
    python_path = (
        venv_dir
        / ("Scripts" if os.name == "nt" else "bin")
        / ("python.exe" if os.name == "nt" else "python")
    )
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        del kwargs
        if "--version" in command:
            return _completed(command, 1, "", "No module named pytest")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    info = module._prepare_venv(tmp_path, enabled=True, timeout=30)
    assert info["python"] == ""
    assert "pytest 不可用" in info["error"]


def test_run_one_test_spawn_failure_is_explicit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_harness()

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise OSError("interpreter vanished")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    record = module._run_one_test(
        tmp_path, "tests/test_x.py::test_a", 30, tmp_path / "tests.log", python=None
    )
    assert record["outcome"] == "error"
    assert "could not start pytest" in record["output_tail"]
    assert "interpreter vanished" in record["output_tail"]


def test_fetch_hf_rows_retries_truncated_response_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proxy-truncated rows response (live-observed IncompleteRead) must
    retry instead of crashing the whole run; success within 3 attempts."""
    import http.client

    module = _load_harness()

    class FakeResponse:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *exc_info: object) -> None:
            del exc_info
            return None

    attempts: list[object] = []

    def fake_urlopen(url: str, timeout: int) -> FakeResponse:
        del url, timeout
        attempts.append(1)
        if len(attempts) < 3:
            raise http.client.IncompleteRead(b"partial" * 10, 200)
        return FakeResponse({"rows": [{"row": {"instance_id": "a__b-1"}}]})

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    rows = module._fetch_hf_rows("owner/name", limit=1)
    assert len(attempts) == 3
    assert [str(row["instance_id"]) for row in rows] == ["a__b-1"]


def test_fetch_hf_rows_gives_up_after_three_truncations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three consecutive truncations surface as HarnessError with the
    offline fallback spelled out — never an unhandled traceback."""
    import http.client

    module = _load_harness()

    def always_truncated(url: str, timeout: int) -> Any:
        del url, timeout
        raise http.client.IncompleteRead(b"partial", 42)

    monkeypatch.setattr(module.urllib.request, "urlopen", always_truncated)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    with pytest.raises(module.HarnessError) as excinfo:
        module._fetch_hf_rows("owner/name", limit=1)
    message = str(excinfo.value)
    assert "3 次响应截断" in message
    assert "--offline" in message
