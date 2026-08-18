"""Streaming wrapper unit tests (GRAND_PLAN_V2 卷 XXI §21.3) — craft/llm.py
+ the CLI --stream / Ctrl-C lane.

Covered: stream_chat_sync native chunk order + usage aggregation;
fallback mode when the probe reports no streaming (final content yielded
once, honest stream_mode annotation); no-key honesty; BudgetExceeded
propagation; the stream_hook driving chat() with content-only callbacks
(reasoning stays in the journal); partial per-chunk usage merge; CLI
--stream without a key degrades with an honest note; Ctrl-C via a fix
module raising KeyboardInterrupt flushes an interrupted checkpoint +
memory.json and exits 130 with a resume hint.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli.specproof.commands.craft import craft_cmd
from craft.llm import LLMClient, LLMUnavailableError
from providers.base import LLMMessage, LLMResponse
from providers.budget import BudgetExceeded

REASONING_MARK = "TOP-SECRET-PRIVATE-CHAIN"
FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

_OPEN_CLIENTS: list[LLMClient] = []


@pytest.fixture(autouse=True)
def _close_clients() -> Any:
    yield
    for client in _OPEN_CLIENTS:
        client.close()
    _OPEN_CLIENTS.clear()


class StreamProvider:
    """Stub provider with a real async-generator chat_stream (no network)."""

    def __init__(
        self,
        * ,
        chunks: list[LLMResponse] | None = None,
        streaming: bool = True,
        content: str = "one-shot reply",
        usage: dict[str, Any] | None = None,
    ) -> None:
        self.chunks = chunks
        self.streaming = streaming
        self.content = content
        self.usage = usage or {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        self.chat_calls: list[dict[str, Any]] = []
        self.stream_calls = 0

    async def chat(
        self, messages: list[Any], tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None, response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False, opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> LLMResponse:
        self.chat_calls.append({
            "messages": messages,
            "response_format": response_format,
            "thinking": thinking,
            "timeout": timeout,
        })
        return LLMResponse(content=self.content, usage=dict(self.usage), model="stub")

    async def chat_stream(
        self, messages: list[Any], tools: list[dict[str, Any]] | None = None,
        thinking: bool | dict[str, Any] = False, opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> AsyncIterator[LLMResponse]:
        self.stream_calls += 1
        if self.chunks is not None:
            for chunk in self.chunks:
                yield chunk
            return
        yield LLMResponse(
            content=self.content, usage=dict(self.usage), model="stub", finish_reason="stop"
        )

    def get_capabilities(self) -> dict[str, bool]:
        return {"chat": True, "streaming": self.streaming}


def make_client(**kwargs: Any) -> tuple[LLMClient, StreamProvider]:
    provider = StreamProvider(**kwargs)
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    return client, provider


def usage_entry(client: LLMClient) -> dict[str, Any]:
    assert client.calls
    return client.calls[-1]


# -- stream_chat_sync -----------------------------------------------------


def test_stream_native_yields_chunks_in_order_and_aggregates_usage() -> None:
    chunks = [
        LLMResponse(content="Hel", model="stub"),
        LLMResponse(content="lo", model="stub"),
        LLMResponse(
            content="!",
            usage={"prompt_tokens": 100, "completion_tokens": 3, "reasoning_tokens": 7},
            model="stub",
        ),
    ]
    client, provider = make_client(chunks=chunks)
    pieces = list(
        client.stream_chat_sync([LLMMessage(role="user", content="hi")], label="t")
    )
    assert pieces == ["Hel", "lo", "!"]
    assert provider.stream_calls == 1
    assert client.last_stream_mode == "native"
    entry = usage_entry(client)
    assert entry["stream_mode"] == "native"
    assert entry["label"] == "t"
    assert entry["prompt_tokens"] == 100
    assert entry["completion_tokens"] == 3
    assert entry["reasoning_tokens"] == 7
    assert client.budget.used > 0


def test_stream_reasoning_never_reaches_yielded_pieces() -> None:
    chunks = [
        LLMResponse(content=None, reasoning_content="think-1", model="stub"),
        LLMResponse(content="answer", reasoning_content="think-2", model="stub"),
    ]
    client, _provider = make_client(chunks=chunks)
    pieces = list(
        client.stream_chat_sync([LLMMessage(role="user", content="x")], label="r")
    )
    assert pieces == ["answer"]
    assert client.reasoning_journal[0]["reasoning_content"] == "think-1think-2"


def test_stream_fallback_when_probe_has_no_streaming() -> None:
    client, provider = make_client(streaming=False, content="one-shot")
    pieces = list(
        client.stream_chat_sync(
            [LLMMessage(role="user", content="x")],
            label="fb",
            response_format={"type": "json_object"},
        )
    )
    assert pieces == ["one-shot"]
    assert client.last_stream_mode == "fallback"
    entry = usage_entry(client)
    assert entry["stream_mode"] == "fallback"
    assert provider.stream_calls == 0  # native was never attempted
    assert provider.chat_calls[0]["response_format"] == {"type": "json_object"}


def test_stream_without_key_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    client = LLMClient()
    _OPEN_CLIENTS.append(client)
    with pytest.raises(LLMUnavailableError):
        list(client.stream_chat_sync([LLMMessage(role="user", content="x")], label="t"))


def test_stream_budget_overrun_propagates() -> None:
    # Pre-call gate passes (estimate 1) but the aggregated usage overruns
    # the limit on record — BudgetExceeded must reach the consumer.
    chunks = [
        LLMResponse(
            content="ok", usage={"prompt_tokens": 1000, "completion_tokens": 1}
        )
    ]
    provider = StreamProvider(chunks=chunks)
    client = LLMClient(provider=provider, token_budget=10)
    _OPEN_CLIENTS.append(client)
    with pytest.raises(BudgetExceeded):
        list(
            client.stream_chat_sync(
                [LLMMessage(role="user", content="x")],
                label="t",
                estimated_prompt_tokens=1,
            )
        )


def test_stream_aggregates_partial_chunk_usage() -> None:
    chunks = [
        LLMResponse(content="x", usage={"prompt_tokens": 10}),
        LLMResponse(
            content="y",
            usage={"completion_tokens": 4, "prompt_cache_hit_tokens": 9},
        ),
    ]
    client, _provider = make_client(chunks=chunks)
    list(client.stream_chat_sync([LLMMessage(role="user", content="x")], label="u"))
    entry = usage_entry(client)
    assert entry["prompt_tokens"] == 10
    assert entry["completion_tokens"] == 4
    assert entry["prompt_cache_hit_tokens"] == 9


# -- stream_hook on chat() -------------------------------------------------


def test_chat_stream_hook_native_order_and_annotation() -> None:
    chunks = [
        LLMResponse(content="a", model="stub"),
        LLMResponse(content="b", model="stub"),
        LLMResponse(content="c", usage={"prompt_tokens": 3, "completion_tokens": 3}),
    ]
    provider = StreamProvider(chunks=chunks)
    received: list[str] = []
    client = LLMClient(provider=provider, stream_hook=received.append)
    _OPEN_CLIENTS.append(client)
    response = client.chat_sync([LLMMessage(role="user", content="hi")], label="hook")
    assert response.content == "abc"
    assert received == ["a", "b", "c"]
    assert usage_entry(client)["stream_mode"] == "native"
    assert client.last_stream_mode == "native"


def test_chat_stream_hook_fallback_never_fires_and_annotates() -> None:
    provider = StreamProvider(streaming=False, content="solo")
    received: list[str] = []
    client = LLMClient(provider=provider, stream_hook=received.append)
    _OPEN_CLIENTS.append(client)
    response = client.chat_sync(
        [LLMMessage(role="user", content="hi")],
        label="fb",
        response_format={"type": "json_object"},
    )
    assert response.content == "solo"
    assert received == []
    assert usage_entry(client)["stream_mode"] == "fallback"
    assert client.last_stream_mode == "fallback"


def test_chat_without_hook_stays_non_streaming() -> None:
    client, provider = make_client(streaming=True, content="plain")
    response = client.chat_sync([LLMMessage(role="user", content="hi")], label="p")
    assert response.content == "plain"
    assert provider.stream_calls == 0
    assert "stream_mode" not in usage_entry(client)
    assert client.last_stream_mode == ""


# -- CLI lane: --stream fallback note + Ctrl-C 130 -------------------------


def write_fixture_repo(tmp_path: Path) -> None:
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


def write_fix_module(tmp_path: Path, name: str, body: str) -> Path:
    mod = tmp_path / name
    mod.write_text(
        "from craft.editor import Editor\n"
        "from craft.planner import Step\n\n\n"
        + body
        + "\n\nFIXES = {'test': fix}\n",
        encoding="utf-8",
    )
    return mod


def test_cli_run_stream_without_key_notes_fallback_and_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("SPECPROOF_SANDBOX", "local")
    write_fixture_repo(tmp_path)
    (tmp_path / "task.spec").write_text(FIX_SPEC, encoding="utf-8")
    fix_mod = write_fix_module(
        tmp_path,
        "fixes_ok.py",
        "def fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:\n"
        '    editor.apply_edit("calc.py", "return x / 2", "return x * 2")\n'
        '    return ["calc.py"]',
    )
    runner = CliRunner()
    result = runner.invoke(
        craft_cmd,
        [
            "run",
            "task.spec",
            "--repo",
            str(tmp_path),
            "--fix-module",
            str(fix_mod),
            "--stream",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "--stream: 无可用 LLM" in result.output
    job_dir = next((tmp_path / ".specraft" / "jobs").iterdir())
    assert (job_dir / "memory.json").is_file()


def test_cli_run_ctrl_c_flushes_checkpoint_exits_130_with_resume_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("SPECPROOF_SANDBOX", "local")
    write_fixture_repo(tmp_path)
    (tmp_path / "task.spec").write_text(FIX_SPEC, encoding="utf-8")
    fix_mod = write_fix_module(
        tmp_path,
        "fixes_ki.py",
        "def fix(editor: Editor, step: Step, diagnosis: str) -> list[str]:\n"
        "    raise KeyboardInterrupt",
    )
    runner = CliRunner()
    result = runner.invoke(
        craft_cmd,
        [
            "run",
            "task.spec",
            "--repo",
            str(tmp_path),
            "--fix-module",
            str(fix_mod),
        ],
    )
    assert result.exit_code == 130, result.output
    assert "已中断 (Ctrl-C)" in result.output
    assert "specproof craft resume --job" in result.output
    job_dir = next((tmp_path / ".specraft" / "jobs").iterdir())
    checkpoint = json.loads((job_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["entries"][-1]["verdict"] == "interrupted"
    assert (job_dir / "memory.json").is_file()
    assert not (job_dir / "report.json").exists()


# -- terminal echo sink (TTY vs non-TTY) -----------------------------------


def test_stream_echo_non_tty_line_buffered(monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.specproof.commands import craft as craft_mod

    calls: list[tuple[str, bool]] = []

    def fake_echo(
        message: Any = None, file: Any = None, nl: bool = True,
        err: bool = False, color: Any = None,
    ) -> None:
        calls.append((str(message), nl))

    monkeypatch.setattr(craft_mod.click, "echo", fake_echo)
    sink = craft_mod._StreamEcho()
    sink._tty = False
    sink.write("hello\nwor")
    sink.write("ld\n")
    sink.flush()
    assert ("hello", True) in calls
    assert ("world", True) in calls


def test_stream_echo_tty_emits_chunks_inline(monkeypatch: pytest.MonkeyPatch) -> None:
    from cli.specproof.commands import craft as craft_mod

    calls: list[tuple[str, bool]] = []

    def fake_echo(
        message: Any = None, file: Any = None, nl: bool = True,
        err: bool = False, color: Any = None,
    ) -> None:
        calls.append((str(message), nl))

    monkeypatch.setattr(craft_mod.click, "echo", fake_echo)
    monkeypatch.setattr(craft_mod.sys.stdout, "flush", lambda: None)
    sink = craft_mod._StreamEcho()
    sink._tty = True
    sink.write("ab")
    sink.write("cd")
    assert ("[LLM 流式] ", False) in calls
    assert ("ab", False) in calls
    assert ("cd", False) in calls
