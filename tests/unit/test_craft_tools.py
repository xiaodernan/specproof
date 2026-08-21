"""craft/tools.py unit tests — registry, envelope, dispatch gates, redaction,
approval, path containment + the loop -> registry wiring (计划书 §22-2)."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from craft.editor import sha256_digest
from craft.executor import Executor
from craft.llm import DATA_SECTION_BEGIN, LLMClient
from craft.loop import CraftLoop
from craft.planner import compile_plan
from craft.schemas import Approval, ToolCall, ToolResult
from craft.spec import parse_spec_text
from craft.tools import (
    CODE_APPROVAL_REQUIRED,
    CODE_COMMAND_NOT_ALLOWED,
    CODE_INVALID_ARGUMENTS,
    CODE_NOT_A_GIT_REPO,
    CODE_PATH_ESCAPE,
    CODE_PATH_OUT_OF_RANGE,
    CODE_STALE_CONTEXT,
    CODE_UNKNOWN_TOOL,
    CODE_VERSION_MISMATCH,
    ENVELOPE_VERSION,
    ToolRegistry,
    redact_text,
)
from providers.base import LLMResponse

EXPECTED_TOOLS = [
    "apply_patch",
    "ast_edit",
    "create_file",
    "git_diff",
    "git_status",
    "glob",
    "grep",
    "read_file",
    "run_build",
    "run_lint",
    "run_test",
    "run_typecheck",
    "symbol_search",
    "tree",
]


def make_registry(tmp_path: Path, **kwargs: Any) -> ToolRegistry:
    kwargs.setdefault("executor", Executor(tmp_path, mode="local"))
    return ToolRegistry(tmp_path, **kwargs)


def call(registry: ToolRegistry, tool: str, arguments: dict[str, Any]) -> ToolResult:
    return registry.dispatch(registry.build_tool_call(tool, arguments))


# -- registry surface -----------------------------------------------------------


def test_registry_lists_exact_toolset(tmp_path: Path) -> None:
    assert make_registry(tmp_path).tool_names() == sorted(EXPECTED_TOOLS)
    assert len(make_registry(tmp_path).tool_names()) == len(EXPECTED_TOOLS)


def test_risk_grading_matches_ladder(tmp_path: Path) -> None:
    specs = make_registry(tmp_path).specs()
    for name in ("read_file", "tree", "glob", "grep", "symbol_search", "git_status", "git_diff"):
        assert specs[name].risk == "readonly"
    for name in ("apply_patch", "ast_edit", "create_file"):
        assert specs[name].risk == "low_write"
    for name in ("run_test", "run_build", "run_lint", "run_typecheck"):
        assert specs[name].risk == "controlled_exec"
    assert not any(spec.risk == "high" for spec in specs.values())
    assert all(spec.version >= 1 for spec in specs.values())


def test_envelope_is_versioned_stable_and_result_free(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("secret line\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    first = registry.envelope_block()
    assert f"TOOL REGISTRY ENVELOPE v{ENVELOPE_VERSION}" in first
    for name in EXPECTED_TOOLS:
        assert name in first
    for risk in ("readonly", "low_write", "controlled_exec"):
        assert risk in first
    result = call(registry, "read_file", {"path": "f.txt"})
    assert result.status == "ok"
    second = registry.envelope_block()
    assert first == second
    assert "secret line" not in first  # result data never leaks into the envelope


def test_register_rejects_duplicates_and_bad_risk(tmp_path: Path) -> None:
    from craft.tools import ToolError, ToolSpec, _fixed_cost

    registry = make_registry(tmp_path)
    with pytest.raises(ToolError, match="重复注册"):
        registry.register(
            ToolSpec("read_file", 1, "readonly", (), registry._h_read_file, _fixed_cost(1, 1))
        )
    with pytest.raises(ToolError, match="risk"):
        registry.register(
            ToolSpec("shell", 1, "nuclear", (), registry._h_tree, _fixed_cost(1, 1))
        )


# -- dispatch gate chain ---------------------------------------------------------


def test_dispatch_unknown_tool(tmp_path: Path) -> None:
    result = make_registry(tmp_path).dispatch(
        ToolCall(tool="shell", version=1, call_id="c1")
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_UNKNOWN_TOOL}]")


def test_dispatch_version_mismatch(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    result = registry.dispatch(
        ToolCall(tool="read_file", version=2, call_id="c1", arguments={"path": "f.txt"})
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_VERSION_MISMATCH}]")


def test_dispatch_invalid_arguments_never_executes(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    cases = [
        {"path": "f.txt", "limit": 3000},  # above cap
        {"path": "f.txt", "bogus": 1},  # unknown key
        {},  # missing required
        {"path": "f.txt", "offset": "one"},  # wrong type
    ]
    for arguments in cases:
        result = call(registry, "read_file", arguments)
        assert result.status == "error", arguments
        assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]"), arguments
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "x\n"


def test_reason_key_is_accepted_but_must_be_string(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    ok = call(registry, "read_file", {"path": "f.txt", "reason": "诊断需要"})
    assert ok.status == "ok"
    bad = call(registry, "read_file", {"path": "f.txt", "reason": 7})
    assert bad.status == "error"
    assert bad.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")


def test_dispatch_counts_invocations(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    assert registry.dispatch_count == 0
    call(registry, "read_file", {"path": "f.txt"})
    call(registry, "read_file", {"path": "f.txt"})
    assert registry.dispatch_count == 2


# -- path containment -------------------------------------------------------------


def test_path_escape_is_denied(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    outside = tmp_path.parent / "evil.txt"
    outside.write_text("user data\n", encoding="utf-8")
    for arguments in (
        {"path": "../evil.txt", "old": "a", "new": "b"},
        {"path": str(outside), "old": "a", "new": "b"},
    ):
        result = call(registry, "apply_patch", arguments)
        assert result.status == "denied", arguments
        assert result.summary.startswith(f"[{CODE_PATH_ESCAPE}]"), arguments
    assert outside.read_text(encoding="utf-8") == "user data\n"


def test_write_outside_owned_paths_is_denied(tmp_path: Path) -> None:
    registry = make_registry(tmp_path, owned_paths=["src/**"])
    denied = call(registry, "create_file", {"path": "other.txt", "content": "x\n"})
    assert denied.status == "denied"
    assert denied.summary.startswith(f"[{CODE_PATH_OUT_OF_RANGE}]")
    assert not (tmp_path / "other.txt").exists()
    allowed = call(registry, "create_file", {"path": "src/a.txt", "content": "x\n"})
    assert allowed.status == "ok"
    assert (tmp_path / "src" / "a.txt").exists()


def test_owned_paths_subtree_matching(tmp_path: Path) -> None:
    registry = make_registry(tmp_path, owned_paths=["src/**", "tests/**"])
    assert call(registry, "create_file", {"path": "src/x.py", "content": ""}).status == "ok"
    assert call(registry, "create_file", {"path": "src_other.py", "content": ""}).status == "denied"
    assert call(registry, "create_file", {"path": "tests/x.py", "content": ""}).status == "ok"


def test_no_owned_paths_means_no_restriction(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    result = call(registry, "create_file", {"path": "anywhere.py", "content": "x\n"})
    assert result.status == "ok"


# -- read-only tools ---------------------------------------------------------------


def test_read_file_returns_digest_and_lines(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_bytes(b"a\nb\n")
    result = call(make_registry(tmp_path), "read_file", {"path": "f.txt"})
    assert result.status == "ok"
    assert "1: a" in result.output_head
    assert sha256_digest(b"a\nb\n")[:12] in result.summary


def test_read_file_missing_is_honest(tmp_path: Path) -> None:
    result = call(make_registry(tmp_path), "read_file", {"path": "nope.txt"})
    assert result.status == "error"
    assert "[FILE_NOT_FOUND]" in result.summary


def test_tree_and_glob(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "c.txt").write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.py").write_text("", encoding="utf-8")
    registry = make_registry(tmp_path)
    tree = call(registry, "tree", {})
    assert tree.status == "ok"
    assert "F: a.py" in tree.output_head
    assert "D: sub/" in tree.output_head
    globbed = call(registry, "glob", {"pattern": "*.py"})
    assert "a.py" in globbed.output_head and "b.py" in globbed.output_head
    assert "c.txt" not in globbed.output_head
    limited = call(registry, "glob", {"pattern": "*.py", "limit": 1})
    assert limited.output_head.count("\n") == 0  # exactly one line


def test_grep_matches_and_caps(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def x():" + "pass\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("def y(): pass\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    result = call(registry, "grep", {"pattern": r"def ", "include": "*.py"})
    assert result.status == "ok"
    assert "a.py:1:" in result.output_head
    assert "b.txt" not in result.output_head
    invalid = call(registry, "grep", {"pattern": "("})
    assert invalid.status == "error"
    assert invalid.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")


def test_symbol_search_uses_repo_graph_read_only(tmp_path: Path) -> None:
    (tmp_path / "Foo.java").write_text(
        "package com.demo;\n"
        "public class Foo {\n"
        "    public int bar(int x) { return baz(x); }\n"
        "    public int baz(int x) { return x * 2; }\n"
        "}\n",
        encoding="utf-8",
    )
    result = call(make_registry(tmp_path), "symbol_search", {"query": "bar"})
    assert result.status == "ok"
    payload = json.loads(result.output_head)
    assert "com.demo.Foo.bar" in payload["resolved"]
    assert "com.demo.Foo.baz" in payload["neighbors"]


def test_git_status_and_diff_on_real_repo(tmp_path: Path) -> None:
    from git import Actor, Repo

    repo = Repo.init(str(tmp_path))
    (tmp_path / "tracked.txt").write_text("v1\n", encoding="utf-8")
    repo.index.add(["tracked.txt"])
    repo.index.commit("init", author=Actor("t", "t@x"), committer=Actor("t", "t@x"))
    (tmp_path / "untracked.txt").write_text("new\n", encoding="utf-8")
    (tmp_path / "tracked.txt").write_text("v2\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    status = call(registry, "git_status", {})
    assert status.status == "ok"
    assert "?? untracked.txt" in status.output_head
    assert " M tracked.txt" in status.output_head
    diff = call(registry, "git_diff", {})
    assert diff.status == "ok"
    assert "v2" in diff.output_head


def test_git_tools_on_non_repo_are_honest(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    for tool in ("git_status", "git_diff"):
        result = call(registry, tool, {})
        assert result.status == "error"
        assert result.summary.startswith(f"[{CODE_NOT_A_GIT_REPO}]")


# -- controlled exec ---------------------------------------------------------------


def test_run_test_ok_and_failing_exit_code(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    ok = call(registry, "run_test", {"command": [sys.executable, "-c", "print('ok')"]})
    assert ok.status == "ok"
    assert ok.exit_code == 0
    assert "exit code 0" in ok.summary
    failing = call(
        registry, "run_test", {"command": [sys.executable, "-c", "import sys; sys.exit(3)"]}
    )
    assert failing.status == "ok"  # the tool executed; the command failed
    assert failing.exit_code == 3


def test_run_command_outside_whitelist_is_denied(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    result = call(registry, "run_test", {"command": ["rm", "-rf", "/"]})
    assert result.status == "denied"
    assert result.summary.startswith(f"[{CODE_COMMAND_NOT_ALLOWED}]")


def test_run_command_bad_shape_is_invalid_arguments(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    result = call(registry, "run_test", {"command": "pytest"})
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")


# -- redaction ----------------------------------------------------------------------


def test_redact_text_redacts_sk_bearer_and_pem() -> None:
    text = "token sk-abcdef123456\nAuthorization: Bearer eyJhbGciOiJIUz\n"
    text += "-----BEGIN RSA PRIVATE KEY-----\nMIIB\n-----END RSA PRIVATE KEY-----\n"
    redacted, changed = redact_text(text)
    assert changed is True
    assert "sk-abcdef123456" not in redacted
    assert "sk-***" in redacted
    assert "eyJhbGciOiJIUz" not in redacted
    assert "Bearer ***" in redacted
    assert "MIIB" not in redacted
    assert "[REDACTED PRIVATE KEY]" in redacted


def test_dispatch_redacts_secrets_in_command_output(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    result = call(
        registry,
        "run_test",
        {"command": [sys.executable, "-c", "print('sk-abcdef123456')"]},
    )
    assert result.status == "ok"
    assert "sk-abcdef123456" not in result.output_head + result.output_tail
    assert "sk-***" in result.output_head
    assert "untrusted" in result.security_tags
    assert "redacted" in result.security_tags


def test_dispatch_redacts_secrets_in_file_reads(tmp_path: Path) -> None:
    (tmp_path / "secrets.txt").write_text("key sk-secret12345678\n", encoding="utf-8")
    result = call(make_registry(tmp_path), "read_file", {"path": "secrets.txt"})
    assert "sk-secret12345678" not in result.output_head
    assert "sk-***" in result.output_head
    assert "redacted" in result.security_tags


def test_every_result_carries_untrusted_tag(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    ok = call(registry, "read_file", {"path": "f.txt"})
    denied = call(registry, "apply_patch", {"path": "../x", "old": "a", "new": "b"})
    assert "untrusted" in ok.security_tags
    assert "untrusted" in denied.security_tags


# -- approval ------------------------------------------------------------------------


def test_approval_policy_can_require_approval_for_run_test(tmp_path: Path) -> None:
    registry = make_registry(
        tmp_path,
        approval_policy=lambda tool, _args: tool == "run_test",
    )
    assert registry.requires_approval("run_test", {}) is True
    assert registry.requires_approval("read_file", {}) is False
    denied = call(registry, "run_test", {"command": [sys.executable, "-c", "pass"]})
    assert denied.status == "denied"
    assert denied.summary.startswith(f"[{CODE_APPROVAL_REQUIRED}]")
    registry.grant(Approval(action="run_test", state="approved"))
    allowed = call(registry, "run_test", {"command": [sys.executable, "-c", "pass"]})
    assert allowed.status == "ok"
    registry.revoke("run_test")
    denied_again = call(registry, "run_test", {"command": [sys.executable, "-c", "pass"]})
    assert denied_again.status == "denied"


def test_approval_policy_fails_closed(tmp_path: Path) -> None:
    def boom(_tool: str, _args: dict[str, Any]) -> bool:
        raise RuntimeError("policy broken")

    registry = make_registry(tmp_path, approval_policy=boom)
    assert registry.requires_approval("apply_patch", {}) is True
    result = call(registry, "create_file", {"path": "x.py", "content": ""})
    assert result.status == "denied"
    assert result.summary.startswith(f"[{CODE_APPROVAL_REQUIRED}]")


def test_pending_approval_is_not_a_grant(tmp_path: Path) -> None:
    registry = make_registry(tmp_path, approval_policy=lambda tool, _args: tool == "run_test")
    registry.approvals["run_test"] = Approval(action="run_test", state="pending")
    result = call(registry, "run_test", {"command": [sys.executable, "-c", "pass"]})
    assert result.status == "denied"


def test_build_tool_call_fills_envelope_fields(tmp_path: Path) -> None:
    registry = make_registry(tmp_path, approval_policy=lambda tool, _args: tool == "run_test")
    built = registry.build_tool_call("run_test", {"command": [sys.executable, "-c", "pass"]})
    assert built.tool == "run_test"
    assert built.version == 1
    assert built.call_id
    assert built.budget_cost["seconds"] > 0
    assert built.requires_approval is True


# -- writes through the registry -------------------------------------------------------


def test_apply_patch_and_create_file_through_dispatch(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_bytes(b"a\nb\n")
    registry = make_registry(tmp_path)
    patch = call(registry, "apply_patch", {"path": "f.txt", "old": "b", "new": "X"})
    assert patch.status == "ok"
    assert (tmp_path / "f.txt").read_bytes() == b"a\nX\n"
    created = call(registry, "create_file", {"path": "new.py", "content": "x = 1\n"})
    assert created.status == "ok"
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "x = 1\n"


def test_dispatch_stale_context_maps_to_stable_code(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_bytes(b"user version\n")
    registry = make_registry(tmp_path)
    result = call(
        registry,
        "apply_patch",
        {
            "path": "f.txt",
            "old": "user version",
            "new": "x",
            "expected_digest": sha256_digest(b"old\n"),
        },
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_STALE_CONTEXT}]")
    assert (tmp_path / "f.txt").read_bytes() == b"user version\n"


def test_dispatch_edit_rejection_is_honest(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("a\na\n", encoding="utf-8")
    result = call(make_registry(tmp_path), "apply_patch", {"path": "f.txt", "old": "a", "new": "x"})
    assert result.status == "error"
    assert "[EDIT_REJECTED]" in result.summary
    assert (tmp_path / "f.txt").read_text(encoding="utf-8") == "a\na\n"


# -- loop wiring ------------------------------------------------------------------------


class StubProvider:
    """Deterministic provider stub — the edit proposal is fixed."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[list[Any]] = []

    async def chat(
        self,
        messages: list[Any],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, Any] | None = None,
        thinking: bool | dict[str, Any] = False,
        opts: dict[str, Any] | None = None,
        timeout: float = 180.0,
    ) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(
            content=self.reply,
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            model="stub",
        )


_OPEN_CLIENTS: list[LLMClient] = []


@pytest.fixture(autouse=True)
def _close_clients() -> Iterator[None]:
    yield
    for client in _OPEN_CLIENTS:
        client.close()
    _OPEN_CLIENTS.clear()


def _write_fixture_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def double(x):\n    return x / 2\n", encoding="utf-8"
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import double\n\n\ndef test_double():\n    assert double(4) == 8\n",
        encoding="utf-8",
    )


FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"


def test_loop_diagnose_path_routes_edits_through_registry(tmp_path: Path) -> None:
    from craft.editor import Editor

    _write_fixture_repo(tmp_path)
    proposal = json.dumps(
        {
            "diagnosis": "除法应为乘法",
            "edits": [
                {
                    "action": "apply_edit",
                    "path": "calc.py",
                    "old": "return x / 2",
                    "new": "return x * 2",
                }
            ],
        }
    )
    provider = StubProvider(proposal)
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    artifact_dir = tmp_path / ".specraft" / "jobs" / "wire-1"
    job_editor = Editor(
        tmp_path,
        backup_dir=artifact_dir / "backup",
        audit_path=artifact_dir / "audit.jsonl",
    )
    registry = ToolRegistry(
        tmp_path,
        editor=job_editor,
        executor=Executor(tmp_path, mode="local"),
        owned_paths=["calc.py"],
    )
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        exec_mode="local",
        job_id="wire-1",
        client=client,
        tool_registry=registry,
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert registry.dispatch_count >= 1
    assert report["tool_registry"]["present"] is True
    assert report["tool_registry"]["tools"] == registry.tool_names()
    assert report["tool_registry"]["dispatches"] == registry.dispatch_count
    # one shared editor -> the audit trail stays coherent with the report
    assert loop.editor is job_editor
    assert report["diff_stat"]["files"] == ["calc.py"]
    assert provider.calls
    prompt = provider.calls[0][0].content
    assert "TOOL REGISTRY ENVELOPE" in prompt
    assert DATA_SECTION_BEGIN in prompt


def test_loop_without_registry_keeps_legacy_editor_surface(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    provider = StubProvider(json.dumps({"diagnosis": "x", "edits": []}))
    client = LLMClient(provider=provider)
    _OPEN_CLIENTS.append(client)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(spec, plan, tmp_path, exec_mode="local", job_id="wire-2", client=client)
    report = loop.run()
    assert report["result"] == "STUCK"  # no edits proposed, same error 3x -> M1 semantics
    assert "tool_registry" not in report
    assert provider.calls
    prompt = provider.calls[0][0].content
    assert "可用编辑工具" in prompt  # legacy _EDITOR_API_BLOCK
    assert "TOOL REGISTRY ENVELOPE" not in prompt
