"""MCP stdio client (JSON-RPC 2.0, protocol 2024-11-05, stdlib only).

Mirrors the framing contract of mcp/server.py: one JSON-RPC message per
line, newline-delimited UTF-8, responses on stdout only, logging on stderr.
The default transport spawns the server command as a subprocess; any
MCPTransport can be injected instead (tests, in-process bridges), so the
wire logic is fully exercisable without subprocess flakiness.

Hardening contract (M10):
- every request carries a JSON-RPC id and only a response with the SAME id
  is delivered to the waiter; late or unmatched responses are dropped;
- every call runs under a per-call timeout (DEFAULT_TIMEOUT); a silent
  server is answered with MCPClientError(code=MCP_TIMEOUT);
- tool output is capped at max_output_bytes with TRUNCATION_MARKER appended
  (UTF-8-safe cut; the omitted byte count rides in MCPToolResult);
- failures map to stable codes: MCP_TIMEOUT / MCP_CONNECTION_ERROR /
  MCP_PROTOCOL_ERROR / MCP_SERVER_ERROR / INVALID_ARGUMENTS / UNKNOWN_TOOL.
  INVALID_ARGUMENTS and UNKNOWN_TOOL reuse the registry's stable codes
  (craft/tools.py) so a bridge handler can prefix its summary with [CODE];
- after a connection or framing failure the client refuses further
  requests (fail-fast); callers rebuild the session.

Threading model: one daemon reader thread consumes transport lines and
routes them by id into per-request queues; requests wait on their queue
with a timeout. close() is idempotent and unblocks every waiter.
"""

from __future__ import annotations

import itertools
import json
import logging
import os
import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import IO, Any, Protocol, cast

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "specproof-mcp-client"
CLIENT_VERSION = "0.1.0"

_JSONRPC = "2.0"

DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_OUTPUT_BYTES = 1_000_000
TRUNCATION_MARKER = "…[TRUNCATED]"

CODE_TIMEOUT = "MCP_TIMEOUT"
CODE_CONNECTION = "MCP_CONNECTION_ERROR"
CODE_PROTOCOL = "MCP_PROTOCOL_ERROR"
CODE_SERVER_ERROR = "MCP_SERVER_ERROR"
CODE_INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
CODE_UNKNOWN_TOOL = "UNKNOWN_TOOL"

_UNKNOWN_TOOL_MARKERS = ("unknown tool",)
_INVALID_ARGUMENTS_MARKERS = (
    "missing required argument",
    "must be a json object",
    "requires a string",
    "unknown key",
    "invalid arguments",
    "invalid params",
    "参数非法",
)


class MCPClientError(RuntimeError):
    """A client-side MCP failure carrying a stable code (see module doc)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def __str__(self) -> str:
        return str(self.args[0]) if self.args else super().__str__()


@dataclass(frozen=True)
class MCPToolResult:
    """One successful tools/call answer, already capped and marked."""

    text: str
    truncated: bool = False
    truncated_bytes: int = 0
    duration: float = 0.0


class MCPTransport(Protocol):
    """Line-framed JSON-RPC transport (the stdio contract of mcp/server.py)."""

    def send(self, line: str) -> None: ...

    def recv(self) -> str:
        """Block for one line; raise EOFError/OSError when the pipe closes."""
        ...

    def close(self) -> None: ...


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _map_jsonrpc_error(code: int) -> str:
    if code == -32602:
        return CODE_INVALID_ARGUMENTS
    if code in (-32700, -32600, -32601):
        return CODE_PROTOCOL
    return CODE_SERVER_ERROR


def _map_tool_error(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in _UNKNOWN_TOOL_MARKERS):
        return CODE_UNKNOWN_TOOL
    if any(marker in lowered for marker in _INVALID_ARGUMENTS_MARKERS):
        return CODE_INVALID_ARGUMENTS
    return CODE_SERVER_ERROR


def _truncate_text(text: str, max_bytes: int) -> tuple[str, bool, int]:
    """Cap text at max_bytes (UTF-8-safe) and mark the cut honestly."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False, 0
    marker = TRUNCATION_MARKER.encode("utf-8")
    head = raw[: max_bytes - len(marker)].decode("utf-8", errors="ignore")
    omitted = len(raw) - len(head.encode("utf-8"))
    return f"{head}{TRUNCATION_MARKER}", True, omitted


class StdioTransport:
    """MCPTransport over a server subprocess: stdin/stdout pipes, UTF-8."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError(f"MCP server command must be non-empty strings: {command!r}")
        merged_env: dict[str, str] | None = None
        if env:
            merged_env = dict(os.environ)
            merged_env.update(env)
        self._proc: subprocess.Popen[str] = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            encoding="utf-8",
            bufsize=1,
            cwd=cwd,
            env=merged_env,
        )

    def send(self, line: str) -> None:
        proc = self._proc
        stdin = cast(IO[str] | None, proc.stdin)
        if stdin is None or proc.poll() is not None:
            raise EOFError(f"MCP server exited early with code {proc.returncode}")
        stdin.write(line + "\n")
        stdin.flush()

    def recv(self) -> str:
        stdout = cast(IO[str] | None, self._proc.stdout)
        if stdout is None:
            raise EOFError("MCP server stdout is unavailable")
        line = stdout.readline()
        if line == "":
            raise EOFError(f"MCP server closed stdout (exit code {self._proc.poll()})")
        return line

    def close(self) -> None:
        proc = self._proc
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5.0)
        for stream in (proc.stdin, proc.stdout):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    logger.debug("closing MCP stdio pipe failed", exc_info=True)


class MCPClient:
    """MCP client over stdio: initialize / tools/list / tools/call / ping.

    Construct with any MCPTransport (tests inject fakes); connect_stdio()
    is the convenience factory over a server subprocess.
    """

    def __init__(
        self,
        transport: MCPTransport,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout:g}")
        min_bytes = len(TRUNCATION_MARKER.encode("utf-8")) + 1
        if max_output_bytes < min_bytes:
            raise ValueError(
                f"max_output_bytes must be >= {min_bytes} (truncation marker), "
                f"got {max_output_bytes}"
            )
        self.timeout = timeout
        self.max_output_bytes = max_output_bytes
        self._transport = transport
        self._ids = itertools.count(1)
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._failure: tuple[str, str] | None = None
        self._closed = False
        self._reader = threading.Thread(
            target=self._read_loop, name="mcp-client-reader", daemon=True
        )
        self._reader.start()

    @classmethod
    def connect_stdio(
        cls,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> MCPClient:
        return cls(
            StdioTransport(command, cwd=cwd, env=env),
            timeout=timeout,
            max_output_bytes=max_output_bytes,
        )

    # -- context management -----------------------------------------------

    def __enter__(self) -> MCPClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
            self._failure = (CODE_CONNECTION, "MCP client closed")
        for item in pending:
            item.put({"ok": False, "code": CODE_CONNECTION, "message": "MCP client closed"})
        self._transport.close()
        self._reader.join(timeout=5.0)

    # -- wire surface ------------------------------------------------------

    def initialize(self, *, timeout: float | None = None) -> dict[str, Any]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
            timeout if timeout is not None else self.timeout,
        )
        self.notify("notifications/initialized", {})
        return result

    def notify(self, method: str, params: dict[str, Any]) -> None:
        failure = self._failure
        if failure is not None:
            raise MCPClientError(failure[0], failure[1])
        message = {"jsonrpc": _JSONRPC, "method": method, "params": params}
        try:
            self._transport.send(_dumps(message))
        except (OSError, EOFError) as exc:
            raise MCPClientError(
                CODE_CONNECTION, f"{method}: sending the notification failed: {exc}"
            ) from exc

    def list_tools(self, *, timeout: float | None = None) -> list[dict[str, Any]]:
        result = self._request("tools/list", {}, timeout if timeout is not None else self.timeout)
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise MCPClientError(CODE_PROTOCOL, "tools/list result carries no 'tools' array")
        return tools

    def call_tool(
        self, name: str, arguments: dict[str, Any], *, timeout: float | None = None
    ) -> MCPToolResult:
        if not isinstance(name, str) or not name:
            raise ValueError("tool name must be a non-empty string")
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be a JSON object")
        started = time.perf_counter()
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout if timeout is not None else self.timeout,
        )
        text, is_error = self._extract_text(result)
        text, truncated, omitted = _truncate_text(text, self.max_output_bytes)
        duration = time.perf_counter() - started
        if is_error:
            raise MCPClientError(_map_tool_error(text), f"{name}: {text}")
        return MCPToolResult(
            text=text, truncated=truncated, truncated_bytes=omitted, duration=duration
        )

    def ping(self, *, timeout: float | None = None) -> None:
        self._request("ping", {}, timeout if timeout is not None else self.timeout)

    # -- request plumbing --------------------------------------------------

    def _request(self, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        failure = self._failure
        if failure is not None:
            raise MCPClientError(failure[0], failure[1])
        if timeout <= 0:
            raise ValueError(f"timeout must be positive, got {timeout:g}")
        msg_id = next(self._ids)
        pending: queue.Queue[dict[str, Any]] = queue.Queue()
        with self._lock:
            self._pending[msg_id] = pending
        message = {"jsonrpc": _JSONRPC, "id": msg_id, "method": method, "params": params}
        try:
            self._transport.send(_dumps(message))
        except (OSError, EOFError) as exc:
            with self._lock:
                self._pending.pop(msg_id, None)
            raise MCPClientError(
                CODE_CONNECTION, f"{method}: sending the request failed: {exc}"
            ) from exc
        try:
            response = pending.get(timeout=timeout)
        except queue.Empty as exc:
            with self._lock:
                self._pending.pop(msg_id, None)
            raise MCPClientError(
                CODE_TIMEOUT, f"{method} timed out after {timeout:g} seconds"
            ) from exc
        if not response["ok"]:
            raise MCPClientError(response["code"], f"{method}: {response['message']}")
        return cast(dict[str, Any], response["result"])

    def _read_loop(self) -> None:
        while not self._closed:
            try:
                line = self._transport.recv()
            except (EOFError, OSError) as exc:
                self._fail_all(CODE_CONNECTION, f"MCP server connection closed: {exc}")
                return
            except Exception as exc:  # noqa: BLE001 - the reader must never die silently
                self._fail_all(
                    CODE_PROTOCOL,
                    f"MCP transport read failed: {type(exc).__name__}: {exc}",
                )
                return
            if self._closed or not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                self._fail_all(CODE_PROTOCOL, f"MCP server sent an unparseable line: {exc}")
                continue
            if isinstance(message, list):
                for item in message:
                    self._route(item)
                continue
            self._route(message)

    def _route(self, message: Any) -> None:
        if not isinstance(message, dict):
            self._fail_all(CODE_PROTOCOL, "MCP server sent a non-object JSON-RPC message")
            return
        message_id = message.get("id")
        if message_id is None:
            logger.debug("ignoring MCP message without id: %s", _dumps(message)[:200])
            return
        if "result" not in message and "error" not in message:
            logger.debug("ignoring malformed MCP response for id %r", message_id)
            return
        with self._lock:
            pending = self._pending.get(message_id)
        if pending is None:
            logger.debug("dropping late MCP response for id %r", message_id)
            return
        pending.put(self._normalize(message))

    def _normalize(self, message: dict[str, Any]) -> dict[str, Any]:
        error = message.get("error")
        if error is None:
            result = message.get("result")
            if not isinstance(result, dict):
                return {
                    "ok": False,
                    "code": CODE_PROTOCOL,
                    "message": "JSON-RPC result is not an object",
                }
            return {"ok": True, "result": result}
        if not isinstance(error, dict):
            return {"ok": False, "code": CODE_SERVER_ERROR, "message": f"{error!r}"}
        jsonrpc_code = error.get("code")
        if isinstance(jsonrpc_code, int):
            mapped = _map_jsonrpc_error(jsonrpc_code)
        else:
            mapped = CODE_SERVER_ERROR
        text = error.get("message")
        if not isinstance(text, str):
            text = _dumps(error)
        if isinstance(jsonrpc_code, int):
            text = f"{text} (JSON-RPC code {jsonrpc_code})"
        return {"ok": False, "code": mapped, "message": text}

    def _extract_text(self, result: dict[str, Any]) -> tuple[str, bool]:
        content = result.get("content")
        if not isinstance(content, list) or not content:
            raise MCPClientError(CODE_PROTOCOL, "tools/call result has no content list")
        first = content[0]
        if not isinstance(first, dict) or first.get("type") != "text":
            raise MCPClientError(CODE_PROTOCOL, "tools/call result content is not text")
        text = first.get("text")
        if not isinstance(text, str):
            raise MCPClientError(CODE_PROTOCOL, "tools/call result text is not a string")
        return text, bool(result.get("isError"))

    def _fail_all(self, code: str, message: str) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
            self._failure = (code, message)
        for item in pending:
            item.put({"ok": False, "code": code, "message": message})


__all__ = [
    "CLIENT_NAME",
    "CLIENT_VERSION",
    "CODE_CONNECTION",
    "CODE_INVALID_ARGUMENTS",
    "CODE_PROTOCOL",
    "CODE_SERVER_ERROR",
    "CODE_TIMEOUT",
    "CODE_UNKNOWN_TOOL",
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_TIMEOUT",
    "MCPClient",
    "MCPClientError",
    "MCPToolResult",
    "MCPTransport",
    "PROTOCOL_VERSION",
    "StdioTransport",
    "TRUNCATION_MARKER",
]
