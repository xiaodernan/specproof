"""Task memory unit tests (GRAND_PLAN_V2 卷 XXI §21.1) — craft/memory.py.

Covered: add/dedupe policy per kind (error_signature merges count,
file kinds merge by detail, budget keeps latest, decisions append);
deterministic priority truncation in summarize_for_prompt; save/load
round-trip and honest corruption errors; loop wiring (facts recorded
during a run, memory.json written next to checkpoint.json); resume
restores and injects memory into the diagnose variable_data section
(never the stable prefix); memory.json never contains reasoning text
(ADR-017).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient
from craft.loop import CraftLoop
from craft.memory import MemoryError, TaskMemory
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMResponse
from providers.prompt_templates import (
    SYSTEM_BLOCK,
    TOOL_SCHEMA_BLOCK,
    assemble,
    verify_variables_after_prefix,
)

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"
REASONING_MARK = "TOP-SECRET-PRIVATE-CHAIN"


def make_clock() -> Any:
    state = {"n": 0}

    def clock() -> str:
        value = f"2026-01-01T00:00:{state['n']:02d}+00:00"
        state["n"] += 1
        return value

    return clock


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


def fix_double(editor: Any, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def noop_fix(editor: Any, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x / 2")
    return ["calc.py"]


# -- add / dedupe -----------------------------------------------------


def test_add_validates_kind_detail_and_count() -> None:
    mem = TaskMemory(now_fn=make_clock())
    entry = mem.add("decision", "步骤 s1 green", step_id="s1")
    assert entry.kind == "decision"
    assert len(mem) == 1
    with pytest.raises(MemoryError):
        mem.add("teleport", "x")
    with pytest.raises(MemoryError):
        mem.add("decision", "   ")
    with pytest.raises(MemoryError):
        mem.add("budget", "x", count=0)


def test_file_kinds_merge_by_detail_latest_observation_wins() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("file_read", "calc.py", step_id="s1")
    mem.add("file_read", "calc.py", step_id="s2")
    assert len(mem) == 1
    entry = mem.entries[0]
    assert entry.step_id == "s2"
    assert entry.count == 1  # file kinds never accumulate a counter
    mem.add("file_written", "calc.py", step_id="s3")
    assert len(mem) == 2  # different kind: no cross-kind merge


def test_remove_deletes_first_matching_entry() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("decision", "a", step_id="s1")
    mem.add("decision", "b", step_id="s1")
    assert mem.remove("decision", "a") is True
    assert [e.detail for e in mem.entries] == ["b"]
    assert mem.remove("decision", "missing") is False


def test_error_signature_merges_count() -> None:
    mem = TaskMemory(now_fn=make_clock())
    signature = "s3|assert double(4) == 8"
    for _ in range(3):
        mem.add("error_signature", signature, step_id="s3")
    assert len(mem) == 1
    assert mem.entries[0].count == 3
    # a different signature stays a separate entry
    mem.add("error_signature", "s3|NameError: x", step_id="s3")
    assert len(mem) == 2


def test_budget_keeps_only_latest_snapshot() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("budget", "tokens=1 iterations=1", step_id="s1")
    mem.add("budget", "tokens=2 iterations=2", step_id="s2")
    assert len(mem) == 1
    assert mem.entries[0].detail == "tokens=2 iterations=2"


def test_decisions_append_instead_of_merging() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("decision", "retry", step_id="s3")
    mem.add("decision", "retry", step_id="s3")
    assert len(mem) == 2


# -- summarize_for_prompt ---------------------------------------------


def test_summarize_priority_order_one_compact_line_per_entry() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("file_read", "calc.py", step_id="s1")
    mem.add("decision", "green", step_id="s1")
    mem.add("error_signature", "sig", step_id="s3")
    mem.add("file_written", "calc.py", step_id="s3")
    mem.add("budget", "tokens=1", step_id="s3")
    summary = mem.summarize_for_prompt()
    lines = summary.split("\n")
    assert len(lines) == 5
    assert lines[0].startswith("[file_written]")
    assert lines[1].startswith("[error_signature]")
    assert lines[2].startswith("[decision]")
    assert lines[3].startswith("[file_read]")
    assert lines[4].startswith("[budget]")
    assert all("(step " in line for line in lines)


def test_summarize_shows_merge_count_marker() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("error_signature", "sig", step_id="s3")
    mem.add("error_signature", "sig", step_id="s3")
    assert "x2" in mem.summarize_for_prompt()


def test_summarize_deterministic_whole_entry_truncation() -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("file_written", "A" * 60, step_id="s1")
    mem.add("error_signature", "B" * 60, step_id="s1")
    mem.add("decision", "C" * 60, step_id="s1")
    mem.add("file_read", "D" * 60, step_id="s1")
    small = mem.summarize_for_prompt(limit_tokens=20)
    assert "[file_written]" in small
    assert "[decision]" not in small
    assert small == mem.summarize_for_prompt(limit_tokens=20)  # deterministic
    with pytest.raises(MemoryError):
        mem.summarize_for_prompt(limit_tokens=0)


# -- save / load --------------------------------------------------------


def test_save_load_roundtrip(tmp_path: Path) -> None:
    mem = TaskMemory(now_fn=make_clock())
    mem.add("file_written", "calc.py", step_id="s3")
    mem.add("error_signature", "sig", step_id="s3")
    mem.add("error_signature", "sig", step_id="s3")
    path = mem.save(tmp_path)
    assert path == tmp_path / "memory.json"
    assert path.is_file()
    restored = TaskMemory.load(tmp_path)
    assert [(e.kind, e.detail, e.count) for e in restored.entries] == [
        ("file_written", "calc.py", 1),
        ("error_signature", "sig", 2),
    ]


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert len(TaskMemory.load(tmp_path / "no-jobs")) == 0


def test_load_corrupt_or_invalid_raises(tmp_path: Path) -> None:
    (tmp_path / "memory.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(MemoryError):
        TaskMemory.load(tmp_path)
    (tmp_path / "memory.json").write_text(
        '{"entries": [{"kind": "teleport", "detail": "x", "step_id": "", "ts": "", "count": 1}]}',
        encoding="utf-8",
    )
    with pytest.raises(MemoryError):
        TaskMemory.load(tmp_path)


# -- loop wiring ---------------------------------------------------------


def test_loop_writes_memory_facts_next_to_checkpoint(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-mem", fix_registry={"test": fix_double},
        exec_mode="local",
    )
    report = loop.run()
    assert report["result"] == "DONE"
    memory_path = loop.artifact_dir / "memory.json"
    assert memory_path.is_file()
    restored = TaskMemory.load(loop.artifact_dir)
    kinds = {entry.kind for entry in restored.entries}
    assert {"file_read", "file_written", "decision", "budget"} <= kinds
    assert any(
        entry.kind == "file_read" and entry.detail == "calc.py"
        for entry in restored.entries
    )
    assert any(
        entry.kind == "file_written" and entry.detail == "calc.py"
        for entry in restored.entries
    )


def test_loop_stuck_merges_error_signature_count(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-stuck", fix_registry={"test": noop_fix},
        exec_mode="local",
    )
    report = loop.run()
    assert report["result"] == "STUCK"
    restored = TaskMemory.load(loop.artifact_dir)
    signatures = [e for e in restored.entries if e.kind == "error_signature"]
    assert len(signatures) == 1
    assert signatures[0].count == 3


def test_resume_restores_memory_and_injects_into_variable_data(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-resume", fix_registry={}, exec_mode="local"
    )
    report = loop.run()
    assert report["result"] == "FAILED"  # no fix rule: honest failure
    resumed = CraftLoop.from_checkpoint(loop.artifact_dir, exec_mode="local")
    kinds = {entry.kind for entry in resumed.memory.entries}
    assert "file_read" in kinds  # recorded by the first run, restored on resume
    step = plan.steps[2]
    context = resumed._diagnose_context(step, None, "diag")
    summary = context["task_memory"]
    assert "[file_read] calc.py" in summary
    built = assemble(
        SYSTEM_BLOCK + "\n\n" + TOOL_SCHEMA_BLOCK,
        "diagnose",
        context,
        include_envelope=True,
    )
    assert summary in built.text
    assert summary not in built.stable_prefix  # 数据段, 绝不进稳定前缀
    assert verify_variables_after_prefix(built, context)


def test_interrupt_checkpoint_flushes_state_and_memory(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-int", fix_registry={}, exec_mode="local"
    )
    # run() would have written plan.json first — mirror that precondition
    plan.save(loop.artifact_dir / "plan.json")
    loop.memory.add("file_read", "calc.py", step_id="s1")
    loop.interrupt_checkpoint()
    checkpoint = json.loads(
        (loop.artifact_dir / "checkpoint.json").read_text(encoding="utf-8")
    )
    assert checkpoint["entries"][-1]["verdict"] == "interrupted"
    assert (loop.artifact_dir / "memory.json").is_file()
    assert not (loop.artifact_dir / "report.json").exists()
    # the interrupt marker does not break resume
    resumed = CraftLoop.from_checkpoint(loop.artifact_dir, exec_mode="local")
    assert resumed.last_green_step == ""


# -- ADR-017: memory.json carries no reasoning ---------------------------


def _make_response(content: str, reasoning: str | None = REASONING_MARK) -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning_content=reasoning,
        usage={
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "reasoning_tokens": 12,
        },
        model="deepseek-v4-pro",
    )


class _StubProvider:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response

    async def chat(
        self, messages: list[Any], tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None, response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False, opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> LLMResponse:
        return self.response

    async def chat_stream(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def get_capabilities(self) -> dict[str, bool]:
        return {"chat": True, "streaming": False}


def test_memory_json_never_contains_reasoning(tmp_path: Path) -> None:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    diagnose = json.dumps(
        {
            "diagnosis": "double() 把乘法写成了除法",
            "edits": [
                {"action": "apply_edit", "path": "calc.py",
                 "old": "return x / 2", "new": "return x * 2"}
            ],
        },
        ensure_ascii=False,
    )
    client = LLMClient(provider=_StubProvider(_make_response(diagnose)))
    loop = CraftLoop(
        spec, plan, tmp_path, job_id="job-reason", fix_registry={},
        exec_mode="local", client=client,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    memory_text = (loop.artifact_dir / "memory.json").read_text(encoding="utf-8")
    assert REASONING_MARK not in memory_text
    for artifact in loop.artifact_dir.rglob("*"):
        if artifact.is_file():
            text = artifact.read_text(encoding="utf-8", errors="ignore")
            assert REASONING_MARK not in text, f"reasoning leaked into {artifact}"
