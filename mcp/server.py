"""Hand-rolled MCP stdio server (protocol 2024-11-05, stdlib only).

Why not the mcp SDK: this project ships its own top-level package named
\"mcp\" (this one), which shadows the SDK package of the same name on
sys.path. The wire surface needed here is small and stable - initialize,
tools/list, tools/call, ping, and notifications - so a minimal JSON-RPC
implementation is safer and fully testable in-process.

Transport contract (MCP stdio):
- one JSON-RPC message per line, newline-delimited, UTF-8;
- responses go to stdout ONLY; all logging goes to stderr;
- requests carry an id and get a response; notifications (no id) get none;
- the server never exits on a bad message - protocol errors are answered
  with JSON-RPC error codes.

Tool failure contract (per task spec): a tool never crashes the server.
ToolError is answered with isError=true text content; unexpected exceptions
are converted the same way. Missing infrastructure data is a degraded
payload produced by the tool itself, never fabricated.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from mcp.tools import TOOLS, ToolError, call_tool

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "specproof"
SERVER_VERSION = "0.1.0"

_JSONRPC = "2.0"
_ERROR_PARSE = -32700
_ERROR_INVALID_REQUEST = -32600
_ERROR_METHOD_NOT_FOUND = -32601
_ERROR_INVALID_PARAMS = -32602
_KNOWN_METHODS = frozenset({"initialize", "tools/list", "tools/call", "ping"})

_INSTRUCTIONS = (
    "SpecProof exposes verification tools to external agents: specproof_verify, "
    "specproof_contracts_list, specproof_eval_summary, specproof_craft_plan, "
    "specproof_health, specproof_replay_info. All results are honest: degraded "
    "answers say so explicitly and nothing is fabricated. Long-running tools "
    "(verify/craft_plan) execute the CLI in a subprocess."
)


def _json_default(value: Any) -> Any:
    """Serialize storage-typed values (datetimes, Decimals, Paths) to JSON."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _dumps(payload: Any) -> str:
    # Compact: the stdio transport frames ONE message per line, so a
    # multi-line pretty print would corrupt the framing.
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), default=_json_default
    )


def _error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": _JSONRPC,
        "id": message_id,
        "error": {"code": code, "message": message},
    }


def _tool_error_result(message: str) -> dict[str, Any]:
    return {
        "isError": True,
        "content": [{"type": "text", "text": f"SpecProof tool error: {message}"}],
    }


class SpecProofMCPServer:
    """Stateless dispatcher for the MCP JSON-RPC method surface."""

    def handle_message(self, message: Any) -> dict[str, Any] | None:
        """Handle one parsed JSON-RPC message; None means no response to send."""
        if not isinstance(message, dict):
            return _error_response(
                None, _ERROR_INVALID_REQUEST, "request must be a JSON object"
            )
        method = message.get("method")
        message_id = message.get("id")
        if not isinstance(method, str):
            return _error_response(message_id, _ERROR_INVALID_REQUEST, "missing method")
        if method.startswith("notifications/"):
            return None
        if method not in _KNOWN_METHODS:
            return _error_response(
                message_id, _ERROR_METHOD_NOT_FOUND, f"method not found: {method!r}"
            )
        try:
            result = self._dispatch(method, message.get("params"))
        except ToolError as exc:
            result = _tool_error_result(str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server
            logger.exception("unexpected error handling %s", method)
            result = _tool_error_result(f"internal server error: {exc}")
        return {"jsonrpc": _JSONRPC, "id": message_id, "result": result}

    def _dispatch(self, method: str, params: Any) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": _INSTRUCTIONS,
            }
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return self._tools_call(params)
        if method == "ping":
            return {}
        raise ToolError(f"unknown method: {method!r}")  # pragma: no cover - guarded above

    def _tools_call(self, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            return _tool_error_result("tools/call params must be a JSON object")
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _tool_error_result("tools/call requires a string 'name'")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _tool_error_result("tools/call 'arguments' must be a JSON object")
        try:
            payload = call_tool(name, arguments)
        except ToolError as exc:
            return _tool_error_result(str(exc))
        except Exception as exc:  # noqa: BLE001 - never crash the server
            logger.exception("unexpected tool failure in %s", name)
            return _tool_error_result(f"internal server error: {exc}")
        return {
            "isError": False,
            "content": [{"type": "text", "text": _dumps(payload)}],
        }

    def process_line(self, line: str) -> str | None:
        """Parse one stdio line and return the serialized response (or None).

        Also accepts a JSON-RPC batch (a JSON array of messages).
        """
        stripped = line.strip()
        if not stripped:
            return None
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return _dumps(_error_response(None, _ERROR_PARSE, f"parse error: {exc}"))
        if isinstance(message, list):
            responses = [
                self.handle_message(item) for item in message
            ]
            if not any(responses):
                return None
            return _dumps(responses)
        response = self.handle_message(message)
        if response is None:
            return None
        return _dumps(response)


def _configure_stderr_logging() -> None:
    """Keep the stdio contract: logs to stderr, stdout carries JSON-RPC only."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.INFO)


def serve_stdio() -> None:
    """Serve MCP over stdio until stdin closes (EOF).

    Every line is one JSON-RPC message; responses are written to stdout and
    flushed immediately. The server never exits on a bad message.
    """
    _configure_stderr_logging()
    server = SpecProofMCPServer()
    stdout = sys.stdout
    for raw_line in sys.stdin:
        response = server.process_line(raw_line)
        if response is not None:
            stdout.write(response + "\n")
            stdout.flush()
    logger.info("MCP stdio transport closed (stdin EOF)")
