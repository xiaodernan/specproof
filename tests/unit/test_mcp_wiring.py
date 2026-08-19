"""W59 wiring tests: bridge envelopes -> registry ToolSpecs + prompt wrapping.

Everything runs in-process: FakeTransport plays the MCP server side of the
stdio framing contract behind the bridge's real JSON-RPC client (no
subprocess, no network), and the registry under test is the real
ToolRegistry on a tmp_path workspace, so the wiring has to survive the full
dispatch gate chain (validation / redaction / untrusted tagging).
"""

from __future__ import annotations

import json
import queue
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from craft.executor import Executor
from craft.llm import DATA_SECTION_BEGIN, DATA_SECTION_END
from craft.mcp_wiring import external_result_section, register_external_tools
from craft.schemas import ToolCall
from craft.tools import (
    CODE_INVALID_ARGUMENTS,
    CODE_UNKNOWN_TOOL,
    ToolError,
    ToolRegistry,
)

SERVER_CONFIG: dict[str, Any] = {"name": "demo", "command": ["fake", "serve"]}

ECHO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "count": {"type": "integer"},
        "ratio": {"type": "number"},
        "flag": {"type": "boolean"},
        "tags": {"type": "array"},
        "options": {"type": "object"},
        "note": {"type": "null"},
    },
    "required": ["text"],
}

ECHO_TOOL: dict[str, Any] = {
    "name": "echo",
    "description": "Echo back the arguments.",
    "inputSchema": ECHO_SCHEMA,
}


class FakeTransport:
    """Synchronous in-process MCPTransport backed by a scripted responder."""

    def __init__(self, responder: Callable[[dict[str, Any]], dict[str, Any] | None]) -> None:
        self.responder = responder
        self.sent: list[dict[str, Any]] = []
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._closed = False

    def send(self, line: str) -> None:
        if self._closed:
            raise EOFError("transport closed")
        message = json.loads(line)
        self.sent.append(message)
        response = self.responder(message)
        if response is not None:
            self._responses.put(json.dumps(response, separators=(",", ":")))

    def recv(self) -> str:
        item = self._responses.get()
        if item is None:
            raise EOFError("transport closed")
        return item

    def close(self) -> None:
        self._closed = True
        self._responses.put(None)


def scripted_responder(
    tools: list[dict[str, Any]],
    call_text: Callable[[dict[str, Any]], str] | str = "ok",
    call_error: dict[str, Any] | None = None,
    record: list[dict[str, Any]] | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Responder for initialize / tools/list / tools/call with id matching."""

    def responder(message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        if record is not None and msg_id is not None:
            record.append(message)
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05"}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}
        if method == "tools/call":
            if call_error is not None:
                return {"jsonrpc": "2.0", "id": msg_id, "error": call_error}
            arguments = message["params"]["arguments"]
            text = call_text(arguments) if callable(call_text) else call_text
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"isError": False, "content": [{"type": "text", "text": text}]},
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"method not found: {method!r}"},
        }

    return responder


def make_registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(tmp_path, executor=Executor(tmp_path, mode="local"))


def register_echo(
    registry: ToolRegistry,
    *,
    tools: list[dict[str, Any]] | None = None,
    call_text: Callable[[dict[str, Any]], str] | str = "ok",
    call_error: dict[str, Any] | None = None,
    record: list[dict[str, Any]] | None = None,
) -> None:
    """Register one fake demo server through the real wiring path."""
    responder = scripted_responder(tools or [ECHO_TOOL], call_text, call_error, record)

    def factory(command: list[str], cwd: str | None, env: dict[str, str] | None) -> FakeTransport:
        del command, cwd, env
        return FakeTransport(responder)

    names = register_external_tools(
        registry, SERVER_CONFIG, timeout=5.0, max_output_bytes=4096, transport_factory=factory
    )
    assert names == ["mcp.demo.echo"]


# -- wiring surface --------------------------------------------------------------


def test_unconfigured_registration_is_a_noop(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    baseline = registry.tool_names()
    assert register_external_tools(registry, None) == []
    assert register_external_tools(registry, []) == []
    assert registry.tool_names() == baseline
    assert registry.dispatch_count == 0


def test_specs_are_readonly_versioned_and_listed_in_the_envelope(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    register_echo(registry)
    spec = registry.get("mcp.demo.echo")
    assert spec is not None
    assert spec.version == 1
    assert spec.risk == "readonly"
    assert registry.budget_estimate("mcp.demo.echo", {}) == {"seconds": 5, "bytes": 4096}
    assert "mcp.demo.echo v1 [readonly, approval_default=no]" in registry.envelope_block()


def test_param_mapping_including_object_and_null_to_str(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    register_echo(registry)
    spec = registry.get("mcp.demo.echo")
    assert spec is not None
    params = {param.name: param for param in spec.params}
    assert params["text"].kind == "str"
    assert params["text"].required is True
    assert params["count"].kind == "int"
    assert params["count"].required is False
    assert params["ratio"].kind == "int"  # JSON number has no float Param kind
    assert params["flag"].kind == "bool"
    assert params["tags"].kind == "list[str]"
    # object / null properties have no craft Param kind: they map to "str"
    # as a passthrough advisory (the external server validates its schema).
    assert params["options"].kind == "str"
    assert params["note"].kind == "str"


# -- dispatch through the real registry gate chain --------------------------------


def test_dispatch_returns_untrusted_marked_result_and_wrapped_section(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    record: list[dict[str, Any]] = []
    register_echo(
        registry,
        call_text=lambda args: f"echo:{args['text']}:{args.get('count')}",
        record=record,
    )
    result = registry.dispatch(
        registry.build_tool_call("mcp.demo.echo", {"text": "hello", "count": 2})
    )
    assert result.status == "ok"
    assert result.output_head == "echo:hello:2"
    assert "untrusted" in result.security_tags
    section = external_result_section(result)
    assert section.startswith("--- " + DATA_SECTION_BEGIN)
    assert DATA_SECTION_END in section
    assert "echo:hello:2" in section
    assert "summary: mcp.demo.echo ok" in section
    call = next(message for message in record if message.get("method") == "tools/call")
    assert call["params"]["arguments"] == {"text": "hello", "count": 2}


def test_dispatch_error_stays_untrusted_with_stable_code(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    register_echo(registry, call_error={"code": -32602, "message": "Invalid params"})
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    assert "untrusted" in result.security_tags
    section = external_result_section(result)
    assert DATA_SECTION_BEGIN in section
    assert CODE_INVALID_ARGUMENTS in section


def test_registry_gate_chain_applies_to_external_tools(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    register_echo(registry)
    unknown = registry.dispatch(ToolCall(tool="mcp.demo.missing", version=1, call_id="c1"))
    assert unknown.status == "error"
    assert unknown.summary.startswith(f"[{CODE_UNKNOWN_TOOL}]")
    missing = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {}))
    assert missing.status == "error"
    assert missing.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    bogus = registry.dispatch(
        registry.build_tool_call("mcp.demo.echo", {"text": "x", "bogus": 1})
    )
    assert bogus.status == "error"
    assert bogus.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")


def test_object_param_str_caveat_is_enforced_by_the_registry(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    record: list[dict[str, Any]] = []
    register_echo(
        registry,
        call_text=lambda args: f"options={args.get('options')!r}",
        record=record,
    )
    # object-typed properties map to Param kind "str": a JSON object value is
    # refused by the registry gate (the server's own schema stays its job).
    refused = registry.dispatch(
        registry.build_tool_call("mcp.demo.echo", {"text": "x", "options": {"a": 1}})
    )
    assert refused.status == "error"
    assert refused.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    # a JSON-serialized string passes through untouched (passthrough advisory).
    passed = registry.dispatch(
        registry.build_tool_call("mcp.demo.echo", {"text": "x", "options": '{"a": 1}'})
    )
    assert passed.status == "ok"
    assert passed.output_head == "options='{\"a\": 1}'"


def test_duplicate_external_registration_is_refused(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    register_echo(registry)
    with pytest.raises(ToolError, match="重复注册"):
        register_echo(registry)
