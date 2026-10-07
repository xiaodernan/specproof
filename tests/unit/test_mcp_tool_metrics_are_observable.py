"""#211: the external MCP tool boundary is counted at the wiring seam.

Every mcp.* tool call the product dispatches executes through the handler
craft/mcp_wiring.py::_tool_spec_from_envelope builds, so the meter lives
there: mcp_tool_calls_total (denominator — gate refusals decided in
dispatch never reach the handler), mcp_tool_errors_<code>_total (the
bridge's status="error" dicts classified by the "[CODE] " stamp the
bridge contract documents; the closed vocabulary is mcp.client's stable
CODE_* set plus the declared "unprefixed" read-side fallback word) and
mcp_tool_seconds (caller-visible latency of the whole per-call session —
fresh spawn + initialize + tools/call + close — with finally semantics).

Readings this file pins:

- The two surfaces partition: a refused call ticks tool_calls_total and
  the in-tree refusals/errors only; an executed call ticks the mcp family.
  A handler raise (broken envelope dict) is a dispatch-level crash
  (tool_errors_execution_failed) and stays out of the mcp error family.
- One case per word — the six client codes and the fallback — driven
  through the real bridge over a scripted in-process transport.
- Source censuses: exactly one meter point per name in mcp_wiring.py, all
  inside the handler (finally-placed duration, anchored stamp regex,
  unique fallback declaration), and every status="error" dict in
  providers/mcp_bridge.py is stamped with "[", its code carrier being
  either exc.code or the CODE_SERVER_ERROR constant — the dict count is
  pinned so a new error site forces this gate before shipping uncounted.
"""

from __future__ import annotations

import ast
import json
import queue
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mcp.client as mcp_client
from craft.executor import Executor
from craft.mcp_wiring import (
    MCP_TOOL_BUCKETS,
    _error_word,
    _tool_spec_from_envelope,
    register_external_tools,
)
from craft.tools import CODE_EXECUTION_FAILED, ToolRegistry
from mcp.client import (
    CODE_CONNECTION,
    CODE_INVALID_ARGUMENTS,
    CODE_PROTOCOL,
    CODE_SERVER_ERROR,
    CODE_TIMEOUT,
    CODE_UNKNOWN_TOOL,
    DEFAULT_TIMEOUT,
)
from observability import metrics as metrics_module

ROOT = Path(__file__).resolve().parents[2]

SERVER_CONFIG: dict[str, Any] = {"name": "demo", "command": ["fake", "serve"]}

ECHO_TOOL: dict[str, Any] = {
    "name": "echo",
    "description": "Echo back the arguments.",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


def _client_words() -> list[str]:
    """The six stable MCP codes, derived from the module's own __all__."""
    words = sorted(
        getattr(mcp_client, name).lower()
        for name in mcp_client.__all__
        if name.startswith("CODE_")
    )
    assert len(words) == 6, f"mcp.client code vocabulary moved: {words}"
    return words


def _fallback_word() -> str:
    """The wiring's declared read-side fallback, read from its source."""
    text = (ROOT / "craft" / "mcp_wiring.py").read_text(encoding="utf-8")
    matches = re.findall(r'^_UNSTAMPED_WORD = "([a-z_]+)"$', text, re.M)
    assert len(matches) == 1, f"_UNSTAMPED_WORD declaration not unique: {matches}"
    return matches[0]


def _error_counter_names() -> list[str]:
    return [f"mcp_tool_errors_{word}_total" for word in [*_client_words(), _fallback_word()]]


class FakeTransport:
    """Synchronous in-process MCPTransport (mirror of test_mcp_wiring).

    The responder may return a dict (JSON-encoded), a raw str (queued
    verbatim — the garbage-line case) or None (no answer — silence).
    """

    def __init__(
        self, responder: Callable[[dict[str, Any]], dict[str, Any] | str | None]
    ) -> None:
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
        if response is None:
            return
        if isinstance(response, str):
            self._responses.put(response)
        else:
            self._responses.put(json.dumps(response, separators=(",", ":")))

    def recv(self) -> str:
        item = self._responses.get()
        if item is None:
            raise EOFError("transport closed")
        return item

    def close(self) -> None:
        self._closed = True
        self._responses.put(None)


class _DeadTransport(FakeTransport):
    """Every send fails like a dead stdio server -> CODE_CONNECTION."""

    def __init__(self) -> None:
        super().__init__(lambda message: None)

    def send(self, line: str) -> None:
        raise EOFError("MCP server exited early with code 1")


class _BoomTransport(FakeTransport):
    """An exception outside the client's (OSError, EOFError) net -> the
    bridge's unexpected-exception fallback stamps CODE_SERVER_ERROR."""

    def __init__(self) -> None:
        super().__init__(lambda message: None)

    def send(self, line: str) -> None:
        raise RuntimeError("boom")


def _responder(
    *,
    call_error: dict[str, Any] | None = None,
    call_is_error: str | None = None,
    quiet_call: bool = False,
) -> Callable[[dict[str, Any]], dict[str, Any] | str | None]:
    def responder(message: dict[str, Any]) -> dict[str, Any] | str | None:
        method = message.get("method")
        msg_id = message.get("id")
        if isinstance(method, str) and method.startswith("notifications/"):
            return None
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"protocolVersion": "2024-11-05"},
            }
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [ECHO_TOOL]}}
        if method == "tools/call":
            if quiet_call:
                return None
            if call_error is not None:
                return {"jsonrpc": "2.0", "id": msg_id, "error": call_error}
            if call_is_error is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": call_is_error}],
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "isError": False,
                    "content": [{"type": "text", "text": "ok"}],
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"method not found: {method!r}"},
        }

    return responder


def _plain_factory(
    **responder_kwargs: Any,
) -> Callable[..., FakeTransport]:
    responder = _responder(**responder_kwargs)
    return lambda command, cwd, env: FakeTransport(responder)


class _SessionFactory:
    """Session 1 (the registration probe) works; later sessions are broken
    by the given builder — the per-call handler opens a fresh session."""

    def __init__(self, broken: Callable[[], FakeTransport]) -> None:
        self._broken = broken
        self.sessions = 0

    def __call__(self, command: Any, cwd: Any, env: Any) -> FakeTransport:
        self.sessions += 1
        if self.sessions == 1:
            return FakeTransport(_responder())
        return self._broken()


def _registry(tmp_path: Path) -> ToolRegistry:
    return ToolRegistry(tmp_path, executor=Executor(tmp_path, mode="local"))


def _register(
    registry: ToolRegistry, factory: Callable[..., FakeTransport], *, timeout: float = 5.0
) -> None:
    names = register_external_tools(
        registry,
        SERVER_CONFIG,
        timeout=timeout,
        max_output_bytes=4096,
        transport_factory=factory,
    )
    assert names == ["mcp.demo.echo"]


def _envelope(
    name: str, handler: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    return {
        "name": name,
        "version": 1,
        "risk": "readonly",
        "params": [],
        "handler": handler,
        "budget_cost": {"seconds": 1, "bytes": 4096},
    }


def _counter(name: str) -> float:
    return metrics_module.snapshot()["counters"].get(name, 0.0)


def _hist_count() -> float:
    hist = metrics_module.snapshot()["histograms"].get("mcp_tool_seconds")
    return hist["count"] if hist is not None else 0.0


def _before() -> dict[str, float]:
    names = ["mcp_tool_calls_total", *_error_counter_names()]
    return {name: _counter(name) for name in names}


def _assert_one_call(before: dict[str, float], word: str | None) -> None:
    """Exactly one executed call: calls +1, the named error word (or none)
    moved by exactly 1, the rest of the family stayed at 0, and the
    histogram observed the call once (finally semantics)."""
    after = metrics_module.snapshot()["counters"]
    deltas = {name: after.get(name, 0.0) - start for name, start in before.items()}
    assert deltas["mcp_tool_calls_total"] == 1.0, deltas
    wanted = f"mcp_tool_errors_{word}_total" if word is not None else None
    for name, delta in deltas.items():
        if name == "mcp_tool_calls_total":
            continue
        assert delta == (1.0 if name == wanted else 0.0), (name, deltas)
    fresh = {
        name
        for name in after
        if name.startswith("mcp_tool_errors_") and name not in before
    }
    assert not fresh, f"an out-of-vocabulary mcp error word appeared: {fresh}"


# -- ok path --------------------------------------------------------------------


def test_ok_call_moves_calls_and_duration_only(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _register(registry, _plain_factory())
    before = _before()
    hist_before = _hist_count()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "ok"
    _assert_one_call(before, None)
    assert _hist_count() - hist_before == 1.0


# -- one case per word ----------------------------------------------------------


def test_invalid_arguments_jsonrpc_error_counts_invalid_arguments(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    _register(registry, _plain_factory(call_error={"code": -32602, "message": "Invalid params"}))
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    _assert_one_call(before, "invalid_arguments")


def test_unknown_tool_marker_counts_unknown_tool(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _register(registry, _plain_factory(call_is_error="unknown tool: nope"))
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_UNKNOWN_TOOL}]")
    _assert_one_call(before, "unknown_tool")


def test_silent_call_counts_mcp_timeout(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _register(registry, _plain_factory(quiet_call=True), timeout=0.2)
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_TIMEOUT}]")
    _assert_one_call(before, "mcp_timeout")


def test_dead_session_counts_mcp_connection_error(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _register(registry, _SessionFactory(_DeadTransport))
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_CONNECTION}]")
    _assert_one_call(before, "mcp_connection_error")


def test_garbage_line_counts_mcp_protocol_error(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _register(
        registry,
        _SessionFactory(lambda: FakeTransport(lambda message: "this is not json")),
    )
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_PROTOCOL}]")
    _assert_one_call(before, "mcp_protocol_error")


def test_unexpected_wire_exception_counts_mcp_server_error(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    _register(registry, _SessionFactory(_BoomTransport))
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_SERVER_ERROR}]")
    _assert_one_call(before, "mcp_server_error")


# -- the read-side fallback -----------------------------------------------------


def test_prefix_less_error_lands_in_the_unprefixed_fallback(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    spec = _tool_spec_from_envelope(
        _envelope(
            "mcp.demo.broken",
            lambda args: {"status": "error", "summary": "the bridge forgot its stamp"},
        )
    )
    registry.register(spec)
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.broken", {}))
    assert result.status == "error"
    _assert_one_call(before, _fallback_word())


def test_stamp_is_anchored_and_lowercased(tmp_path: Path) -> None:
    # The helper itself: a leading stamp classifies and lowercases; anything
    # else — including a bracket later in the summary — is the fallback.
    fallback = _fallback_word()
    assert _error_word("[MCP_SERVER_ERROR] x") == "mcp_server_error"
    assert _error_word("x [MCP_TIMEOUT] later") == fallback
    assert _error_word("no brackets here") == fallback

    registry = _registry(tmp_path)
    spec = _tool_spec_from_envelope(
        _envelope(
            "mcp.demo.late",
            lambda args: {"status": "error", "summary": "failed: [MCP_TIMEOUT] later"},
        )
    )
    registry.register(spec)
    before = _before()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.late", {}))
    assert result.status == "error"
    _assert_one_call(before, fallback)


# -- partition witnesses --------------------------------------------------------


def test_handler_crash_is_execution_failed_not_an_mcp_word(tmp_path: Path) -> None:
    """A broken envelope dict makes ToolResult(**raw) raise inside the
    handler: the call and its duration are counted (the boundary was
    reached), but the crash is dispatch's execution_failed — the mcp error
    family carries only status="error" results."""
    registry = _registry(tmp_path)
    spec = _tool_spec_from_envelope(
        _envelope("mcp.demo.crash", lambda args: {"status": "ok", "duration": -1.0})
    )
    registry.register(spec)
    before = _before()
    exec_before = _counter("tool_errors_execution_failed_total")
    tool_calls_before = _counter("tool_calls_total")
    hist_before = _hist_count()
    result = registry.dispatch(registry.build_tool_call("mcp.demo.crash", {}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_EXECUTION_FAILED}]")
    _assert_one_call(before, None)
    assert _hist_count() - hist_before == 1.0
    assert _counter("tool_errors_execution_failed_total") - exec_before == 1.0
    assert _counter("tool_calls_total") - tool_calls_before == 1.0


def test_gate_refusal_never_reaches_the_mcp_meter(tmp_path: Path) -> None:
    """A param gate refusal is decided in dispatch: tool_calls_total and the
    in-tree error family tick, the mcp family (calls, words, duration) does
    not — the surfaces partition instead of stacking."""
    registry = _registry(tmp_path)
    _register(registry, _plain_factory())
    before = _before()
    hist_before = _hist_count()
    tool_calls_before = _counter("tool_calls_total")
    refused_before = _counter("tool_errors_invalid_arguments_total")
    result = registry.dispatch(registry.build_tool_call("mcp.demo.echo", {}))
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]")
    for name, start in before.items():
        assert _counter(name) - start == 0.0, (name, before)
    assert _hist_count() - hist_before == 0.0
    assert _counter("tool_calls_total") - tool_calls_before == 1.0
    assert _counter("tool_errors_invalid_arguments_total") - refused_before == 1.0


# -- ladder derivation ----------------------------------------------------------


def test_bucket_ladder_matches_the_constant_and_covers_the_default_timeout(
    tmp_path: Path,
) -> None:
    registry = _registry(tmp_path)
    _register(registry, _plain_factory())
    registry.dispatch(registry.build_tool_call("mcp.demo.echo", {"text": "x"}))
    bounds = metrics_module.snapshot()["histograms"]["mcp_tool_seconds"]["bounds"]
    assert bounds == list(MCP_TOOL_BUCKETS)
    assert list(MCP_TOOL_BUCKETS) == sorted(MCP_TOOL_BUCKETS)
    assert all(bound > 0 for bound in MCP_TOOL_BUCKETS)
    # The top must cover the worst default-timeout call: one session burns
    # up to 2x DEFAULT_TIMEOUT (initialize + tools/call), derived from the
    # client's own constant rather than a copied number.
    assert DEFAULT_TIMEOUT == mcp_client.DEFAULT_TIMEOUT
    assert MCP_TOOL_BUCKETS[-1] >= 2 * mcp_client.DEFAULT_TIMEOUT


# -- source censuses ------------------------------------------------------------


def _wiring_module() -> tuple[ast.Module, str]:
    text = (ROOT / "craft" / "mcp_wiring.py").read_text(encoding="utf-8")
    return ast.parse(text), text


def _emit_calls_in(node: ast.AST) -> list[ast.Call]:
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id in ("incr", "set_gauge", "observe_duration")
    ]


def test_single_meter_point_in_the_wiring_module() -> None:
    tree, text = _wiring_module()
    spec_fns = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_tool_spec_from_envelope"
    ]
    assert len(spec_fns) == 1, "the envelope builder is not a unique module function"
    handlers = [
        node
        for node in spec_fns[0].body
        if isinstance(node, ast.FunctionDef) and node.name == "handler"
    ]
    assert len(handlers) == 1, "the metered handler is not a unique nested def"
    handler = handlers[0]

    module_calls = _emit_calls_in(tree)
    handler_calls = _emit_calls_in(handler)
    assert len(handler_calls) == 3, [ast.unparse(c) for c in handler_calls]
    assert len(module_calls) == len(handler_calls), (
        "emit sites exist outside the handler: "
        f"{[ast.unparse(c) for c in module_calls]}"
    )

    by_name: dict[str, list[ast.Call]] = {}
    for call in handler_calls:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            by_name.setdefault(first.value, []).append(call)
        elif isinstance(first, ast.JoinedStr):
            head = first.values[0]
            assert isinstance(head, ast.Constant) and head.value == "mcp_tool_errors_"
            by_name.setdefault("mcp_tool_errors_", []).append(call)
        else:
            raise AssertionError(f"unreadable meter argument: {ast.unparse(call)}")
    assert sorted(by_name) == ["mcp_tool_calls_total", "mcp_tool_errors_", "mcp_tool_seconds"], (
        sorted(by_name)
    )

    # The error word must come from the stamp reader over the actual summary.
    (word_call,) = by_name["mcp_tool_errors_"]
    formatted = word_call.args[0].values[1]  # type: ignore[union-attr]
    assert isinstance(formatted, ast.FormattedValue)
    assert ast.unparse(formatted.value) == "_error_word(result.summary)"

    # Duration observes in a finally block (failures and construction
    # crashes stay in the sequence).
    (duration_call,) = by_name["mcp_tool_seconds"]
    finally_nodes = [
        stmt
        for try_node in ast.walk(handler)
        if isinstance(try_node, ast.Try)
        for stmt in try_node.finalbody
    ]
    assert any(
        duration_call in _emit_calls_in(stmt) for stmt in finally_nodes
    ), "observe_duration is not finally-placed"

    # The stamp regex is anchored to the start and the fallback declaration
    # is unique (the drift gate in the parity file derives the word from it).
    stamp_assigns = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "_STAMP" for t in node.targets
        )
    ]
    assert len(stamp_assigns) == 1, "_STAMP declaration not unique"
    stamp = stamp_assigns[0].value
    assert isinstance(stamp, ast.Call)
    assert isinstance(stamp.args[0], ast.Constant)
    assert str(stamp.args[0].value).startswith("^"), "stamp regex is not anchored"
    assert text.count("_UNSTAMPED_WORD") >= 2  # declared once, read once


def test_bridge_error_dicts_are_stamped_with_a_readable_code() -> None:
    bridge = (ROOT / "providers" / "mcp_bridge.py").read_text(encoding="utf-8")
    tree = ast.parse(bridge)

    def _dict_value(node: ast.Dict, key: str) -> ast.expr | None:
        # AST nodes compare by identity, so a fresh ast.Constant can never
        # match a key node in a dict lookup — scan the pairs by value.
        for pair_key, pair_value in zip(node.keys, node.values, strict=True):
            if isinstance(pair_key, ast.Constant) and pair_key.value == key:
                return pair_value
        return None

    error_dicts: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        status = _dict_value(node, "status")
        if isinstance(status, ast.Constant) and status.value == "error":
            error_dicts.append(node)
    assert len(error_dicts) == 2, (
        f"bridge error-dict census moved: {len(error_dicts)} status=error "
        "dicts — every one must carry the [CODE] stamp the meter reads"
    )

    carriers: list[str] = []
    for node in error_dicts:
        summary = _dict_value(node, "summary")
        assert isinstance(summary, ast.JoinedStr), ast.unparse(node)
        parts = summary.values
        assert isinstance(parts[0], ast.Constant) and parts[0].value == "["
        assert isinstance(parts[1], ast.FormattedValue)
        assert isinstance(parts[2], ast.Constant) and parts[2].value.startswith("]")
        carriers.append(ast.unparse(parts[1].value))
    assert sorted(carriers) == ["CODE_SERVER_ERROR", "exc.code"], (
        "bridge code carriers moved: "
        f"{sorted(carriers)} — the meter reads [CODE] back at the wiring seam"
    )
