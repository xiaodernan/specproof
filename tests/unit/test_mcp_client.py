"""MCP client tests over an injected in-process transport (no subprocess).

FakeTransport plays the server side of the stdio framing contract: send()
feeds a scripted responder, recv() drains the queued response lines, close()
unblocks the reader. Every scenario is deterministic: roundtrip with id
matching, per-call timeout code, oversized output truncation with marker,
unknown tool, invalid params (isError and JSON-RPC error), connection loss,
protocol error mapping, and the bridge's unconfigured -> empty specs path.
"""

from __future__ import annotations

import json
import queue
from collections.abc import Callable
from typing import Any

import pytest

from mcp.client import (
    CODE_CONNECTION,
    CODE_INVALID_ARGUMENTS,
    CODE_PROTOCOL,
    CODE_TIMEOUT,
    CODE_UNKNOWN_TOOL,
    TRUNCATION_MARKER,
    MCPClient,
    MCPClientError,
    MCPToolResult,
)
from providers.mcp_bridge import build_external_tool_specs


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


class DeadTransport:
    """A transport whose server side is already gone (EOF on first read)."""

    def send(self, line: str) -> None:
        """Accept the write; the pipe is dead on the read side."""

    def recv(self) -> str:
        raise EOFError("MCP server closed stdout")

    def close(self) -> None:
        """Nothing to clean up."""


def scripted_responder(
    *,
    tools: list[dict[str, Any]] | None = None,
    call_result: dict[str, Any] | None = None,
    call_error: dict[str, Any] | None = None,
    call_silent: bool = False,
) -> Callable[[dict[str, Any]], dict[str, Any] | None]:
    """Responder echoing the request id for initialize/tools-list/tools-call."""

    def responder(message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "fake", "version": "0.0.1"},
                },
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools or []}}
        if method == "tools/call":
            if call_silent:
                return None
            if call_error is not None:
                return {"jsonrpc": "2.0", "id": msg_id, "error": call_error}
            result = (
                {"isError": False, "content": [{"type": "text", "text": "ok"}]}
                if call_result is None
                else call_result
            )
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"method not found: {method!r}"},
        }

    return responder


# -- client: roundtrip and framing ---------------------------------------------


def test_initialize_list_and_call_roundtrip_with_id_matching() -> None:
    def echo_responder(message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05"}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [{"name": "demo_ping", "description": "demo", "inputSchema": {}}]
                },
            }
        if method == "tools/call":
            text = f"call-id-{msg_id}"
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"isError": False, "content": [{"type": "text", "text": text}]},
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        return None

    transport = FakeTransport(echo_responder)
    with MCPClient(transport) as client:
        init = client.initialize()
        tools = client.list_tools()
        result = client.call_tool("demo_ping", {"a": 1})
        client.ping()

    assert init["protocolVersion"] == "2024-11-05"
    assert [tool["name"] for tool in tools] == ["demo_ping"]
    # The delivered text embeds the tools/call request id: only a response
    # carrying the matching id reaches the waiter.
    call_request = next(
        message for message in transport.sent if message.get("method") == "tools/call"
    )
    assert result.text == f"call-id-{call_request['id']}"
    assert result.truncated is False
    assert result.truncated_bytes == 0
    methods = [message.get("method") for message in transport.sent]
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
        "ping",
    ]
    # The initialized notification is a JSON-RPC notification: no id.
    notification = transport.sent[1]
    assert "id" not in notification
    ids = [message["id"] for message in transport.sent if "id" in message]
    assert len(ids) == len(set(ids))


def test_call_tool_success_result_shape() -> None:
    responder = scripted_responder()
    with MCPClient(FakeTransport(responder)) as client:
        result = client.call_tool("demo_ping", {})
    assert isinstance(result, MCPToolResult)
    assert result.text == "ok"
    assert result.duration >= 0.0


# -- client: per-call timeout --------------------------------------------------


def test_call_tool_timeout_maps_to_timeout_code() -> None:
    responder = scripted_responder(call_silent=True)
    with (
        MCPClient(FakeTransport(responder), timeout=0.2) as client,
        pytest.raises(MCPClientError) as exc_info,
    ):
        client.call_tool("demo_ping", {})
    assert exc_info.value.code == CODE_TIMEOUT
    assert "tools/call" in str(exc_info.value)


# -- client: output byte limit + truncation marker -----------------------------


def test_oversized_output_is_truncated_and_marked() -> None:
    big = "汉" * 300  # 900 UTF-8 bytes, far beyond the cap
    responder = scripted_responder(
        call_result={"isError": False, "content": [{"type": "text", "text": big}]}
    )
    with MCPClient(FakeTransport(responder), max_output_bytes=200) as client:
        result = client.call_tool("demo_ping", {})
    assert result.truncated is True
    assert result.text.endswith(TRUNCATION_MARKER)
    assert result.truncated_bytes > 0
    assert len(result.text.encode("utf-8")) <= 200
    # The cut never splits a multi-byte character: the head decodes cleanly.
    head = result.text[: -len(TRUNCATION_MARKER)]
    assert head.encode("utf-8").decode("utf-8") == head


# -- client: error mapping to stable codes -------------------------------------


def test_unknown_tool_maps_to_unknown_tool_code() -> None:
    responder = scripted_responder(
        call_result={
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": "SpecProof tool error: unknown tool: 'nope' (available: a, b)",
                }
            ],
        }
    )
    with MCPClient(FakeTransport(responder)) as client, pytest.raises(MCPClientError) as exc_info:
        client.call_tool("nope", {})
    assert exc_info.value.code == CODE_UNKNOWN_TOOL
    assert "nope" in str(exc_info.value)


def test_invalid_params_iserror_maps_to_invalid_arguments() -> None:
    responder = scripted_responder(
        call_result={
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": "SpecProof tool error: missing required argument repo",
                }
            ],
        }
    )
    with MCPClient(FakeTransport(responder)) as client, pytest.raises(MCPClientError) as exc_info:
        client.call_tool("demo_verify", {})
    assert exc_info.value.code == CODE_INVALID_ARGUMENTS


def test_invalid_params_jsonrpc_error_maps_to_invalid_arguments() -> None:
    responder = scripted_responder(call_error={"code": -32602, "message": "Invalid params"})
    with MCPClient(FakeTransport(responder)) as client, pytest.raises(MCPClientError) as exc_info:
        client.call_tool("demo_verify", {})
    assert exc_info.value.code == CODE_INVALID_ARGUMENTS


def test_jsonrpc_method_not_found_maps_to_protocol_error() -> None:
    responder = scripted_responder(
        call_error={"code": -32601, "message": "method not found: tools/call"}
    )
    with MCPClient(FakeTransport(responder)) as client, pytest.raises(MCPClientError) as exc_info:
        client.call_tool("demo_ping", {})
    assert exc_info.value.code == CODE_PROTOCOL


def test_transport_eof_maps_to_connection_error() -> None:
    with MCPClient(DeadTransport()) as client, pytest.raises(MCPClientError) as exc_info:
        client.call_tool("demo_ping", {})
    assert exc_info.value.code == CODE_CONNECTION


# -- bridge --------------------------------------------------------------------


def test_unconfigured_servers_build_no_specs() -> None:
    assert build_external_tool_specs(None) == []
    assert build_external_tool_specs([]) == []


def test_bridge_builds_readonly_specs_and_handler_roundtrip() -> None:
    def echo_responder(message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05"}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo the text back.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string", "description": "the text"},
                                    "count": {"type": "integer"},
                                },
                                "required": ["text"],
                            },
                        }
                    ]
                },
            }
        if method == "tools/call":
            arguments = message["params"]["arguments"]
            text = f"echo:{arguments['text']}"
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"isError": False, "content": [{"type": "text", "text": text}]},
            }
        return None

    def factory(command: list[str], cwd: str | None, env: dict[str, str] | None) -> FakeTransport:
        del command, cwd, env
        return FakeTransport(echo_responder)

    specs = build_external_tool_specs(
        {"name": "demo", "command": ["fake", "serve"]},
        timeout=5.0,
        max_output_bytes=4096,
        transport_factory=factory,
    )

    assert [spec["name"] for spec in specs] == ["mcp.demo.echo"]
    spec = specs[0]
    assert spec["version"] == 1
    assert spec["risk"] == "readonly"
    assert spec["params"] == [
        {"name": "text", "kind": "str", "required": True},
        {"name": "count", "kind": "int", "required": False},
    ]
    assert spec["budget_cost"] == {"seconds": 5, "bytes": 4096}
    assert spec["output_policy"] == "untrusted_data_section"
    handler = spec["handler"]
    result = handler({"text": "hello", "count": 2})
    assert result["status"] == "ok"
    assert result["output_head"] == "echo:hello"
    assert result["truncated"] is False
    assert result["security_tags"] == ["untrusted"]
