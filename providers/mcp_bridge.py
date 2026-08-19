"""M10 external-tool bridge: MCP servers as readonly craft registry specs.

Standalone by design: this module imports only mcp.client (plus stdlib) and
never craft.* - the craft/ package is owned by another lane, so nothing is
registered here. build_external_tool_specs() speaks initialize + tools/list
to each configured MCP server over stdio and returns plain dictionaries
matching the registry envelope shape (craft.tools.ToolSpec): name / version
/ risk / params / handler / budget_cost. Each spec names its tool
mcp.<server>.<tool>, declares risk "readonly", maps the tools/list
inputSchema into Param-shaped dicts (name/kind/required) and keeps the
verbatim inputSchema for a future provider tools parameter.

Output contract: the handler answers with a ToolResult-shaped dict
(status/summary/output_head/truncated/duration/security_tags). Failures use
the stable [CODE] summary prefix (INVALID_ARGUMENTS / UNKNOWN_TOOL reuse the
registry codes); security_tags always carries "untrusted". At prompt
composition the captain's existing path must wrap result text in a DATA
section via craft.llm.wrap_data_section, exactly like every other tool
result - this module does not duplicate the delimiters.

Per-call lifecycle: each handler invocation opens a fresh stdio session
(initialize + tools/call + close). That is the no-leak default; the captain
may switch to a long-lived shared client inside the injection helper if
call latency matters.

Wiring note (captain, after the craft lane lands):

    from craft.schemas import ToolResult
    from craft.tools import Param, ToolRegistry, ToolSpec

    for spec in build_external_tool_specs(server_config):
        raw_handler = spec["handler"]
        registry.register(ToolSpec(
            name=spec["name"], version=spec["version"], risk=spec["risk"],
            params=tuple(Param(**param) for param in spec["params"]),
            handler=lambda args, h=raw_handler: ToolResult(**h(args)),
            budget_cost=lambda _args, cost=spec["budget_cost"]: dict(cost),
        ))

Registry-injection helper signature (documented, NOT wired):

    def inject_external_tools(
        registry: ToolRegistry,
        server_config: ServerConfig | Sequence[ServerConfig] | None,
        *,
        timeout: float = DEFAULT_MCP_TIMEOUT,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> list[str]:
        '''Register every spec from build_external_tool_specs; return names.'''

Schema mapping caveat: JSON properties of type "object"/"null" have no
craft Param kind and map to "str" as a passthrough advisory - the external
server stays the validation authority for its own schema.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from mcp.client import (
    CODE_SERVER_ERROR,
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_TIMEOUT,
    MCPClient,
    MCPClientError,
    MCPToolResult,
    MCPTransport,
    StdioTransport,
)

EXTERNAL_TOOL_PREFIX = "mcp."
DEFAULT_MCP_TIMEOUT = DEFAULT_TIMEOUT

_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

_JSON_KINDS: dict[str, str] = {
    "string": "str",
    "integer": "int",
    "number": "int",
    "boolean": "bool",
    "array": "list[str]",
}

TransportFactory = Callable[[Sequence[str], str | None, Mapping[str, str] | None], MCPTransport]


def _default_transport_factory(
    command: Sequence[str], cwd: str | None, env: Mapping[str, str] | None
) -> MCPTransport:
    return StdioTransport(command, cwd=cwd, env=env)


def _normalize_servers(
    server_config: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if server_config is None:
        return []
    if isinstance(server_config, Mapping):
        raw_servers = [server_config]
    elif isinstance(server_config, Sequence):
        raw_servers = list(server_config)
    else:
        raise ValueError(
            f"server_config must be a mapping or a list of mappings, "
            f"got {type(server_config).__name__}"
        )
    servers: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_servers):
        if not isinstance(raw, Mapping):
            raise ValueError(f"server config #{index} must be a JSON object")
        servers.append(_validated_server(raw, index))
    return servers


def _validated_server(raw: Mapping[str, Any], index: int) -> dict[str, Any]:
    name = raw.get("name")
    if not isinstance(name, str) or not _SERVER_NAME_RE.fullmatch(name):
        raise ValueError(
            f"server config #{index}: 'name' must match "
            f"[A-Za-z0-9][A-Za-z0-9._-]{{0,63}}, got {name!r}"
        )
    command = raw.get("command")
    if (
        not isinstance(command, (list, tuple))
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise ValueError(
            f"server config #{index} ({name!r}): 'command' must be a non-empty "
            f"list of non-empty strings"
        )
    cwd = raw.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError(f"server config #{index} ({name!r}): 'cwd' must be a string")
    env = raw.get("env")
    if env is not None and (
        not isinstance(env, Mapping)
        or not all(isinstance(key, str) and isinstance(value, str) for key, value in env.items())
    ):
        raise ValueError(
            f"server config #{index} ({name!r}): 'env' must be a string->string mapping"
        )
    return {
        "name": name,
        "command": list(command),
        "cwd": cwd,
        "env": dict(env) if env is not None else None,
    }


def _list_tools(
    server: str,
    command: Sequence[str],
    cwd: str | None,
    env: Mapping[str, str] | None,
    timeout: float,
    max_output_bytes: int,
    factory: TransportFactory,
) -> list[dict[str, Any]]:
    client = MCPClient(
        factory(command, cwd, env),
        timeout=timeout,
        max_output_bytes=max_output_bytes,
    )
    try:
        client.initialize(timeout=timeout)
        tools = client.list_tools(timeout=timeout)
    except MCPClientError as exc:
        raise MCPClientError(exc.code, f"MCP server {server!r} unavailable: {exc}") from exc
    finally:
        client.close()
    return tools


def _params_from_schema(schema: Mapping[str, Any]) -> list[dict[str, str | bool]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    required_raw = schema.get("required", [])
    required: set[str] = set()
    if isinstance(required_raw, list) and all(isinstance(item, str) for item in required_raw):
        required = set(required_raw)
    params: list[dict[str, str | bool]] = []
    for name, prop in properties.items():
        if not isinstance(name, str) or not isinstance(prop, dict):
            continue
        json_type = prop.get("type")
        kind = _JSON_KINDS.get(json_type, "str") if isinstance(json_type, str) else "str"
        params.append({"name": name, "kind": kind, "required": name in required})
    return params


def _build_handler(
    server: str,
    tool: str,
    command: Sequence[str],
    cwd: str | None,
    env: Mapping[str, str] | None,
    timeout: float,
    max_output_bytes: int,
    factory: TransportFactory,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    tool_ref = f"{EXTERNAL_TOOL_PREFIX}{server}.{tool}"

    def handler(arguments: dict[str, Any]) -> dict[str, Any]:
        client = MCPClient(
            factory(command, cwd, env),
            timeout=timeout,
            max_output_bytes=max_output_bytes,
        )
        try:
            client.initialize(timeout=timeout)
            result: MCPToolResult = client.call_tool(tool, arguments, timeout=timeout)
        except MCPClientError as exc:
            return {
                "status": "error",
                "summary": f"[{exc.code}] {exc}",
                "security_tags": ["untrusted"],
            }
        except Exception as exc:  # noqa: BLE001 - a tool failure must never crash the loop
            return {
                "status": "error",
                "summary": (
                    f"[{CODE_SERVER_ERROR}] {tool_ref} 调用失败: {type(exc).__name__}: {exc}"
                ),
                "security_tags": ["untrusted"],
            }
        finally:
            client.close()
        summary = f"{tool_ref} ok"
        if result.truncated:
            summary += f" (截断: {result.truncated_bytes} bytes 被省略)"
        return {
            "status": "ok",
            "summary": summary,
            "output_head": result.text,
            "truncated": result.truncated,
            "duration": result.duration,
            "security_tags": ["untrusted"],
        }

    return handler


def _spec_from_tool(
    server: str,
    command: Sequence[str],
    cwd: str | None,
    env: Mapping[str, str] | None,
    tool: Mapping[str, Any],
    timeout: float,
    max_output_bytes: int,
    factory: TransportFactory,
) -> dict[str, Any]:
    tool_name = tool.get("name")
    if not isinstance(tool_name, str) or not _TOOL_NAME_RE.fullmatch(tool_name):
        raise ValueError(f"MCP server {server!r} listed a tool with an invalid name: {tool_name!r}")
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError(f"MCP server {server!r} tool {tool_name!r} has no object inputSchema")
    description = tool.get("description")
    return {
        "name": f"{EXTERNAL_TOOL_PREFIX}{server}.{tool_name}",
        "version": 1,
        "risk": "readonly",
        "params": _params_from_schema(schema),
        "input_schema": dict(schema),
        "description": description if isinstance(description, str) else "",
        "budget_cost": {"seconds": int(timeout), "bytes": int(max_output_bytes)},
        "handler": _build_handler(
            server, tool_name, command, cwd, env, timeout, max_output_bytes, factory
        ),
        "output_policy": "untrusted_data_section",
        "source": {"server": server, "tool": tool_name, "command": list(command)},
    }


def build_external_tool_specs(
    server_config: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    timeout: float = DEFAULT_MCP_TIMEOUT,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    transport_factory: TransportFactory | None = None,
) -> list[dict[str, Any]]:
    """Build readonly registry-envelope specs for every external MCP tool.

    server_config is None (or an empty list) -> []. Each server entry needs
    "name" (identifier) and "command" (argv); optional "cwd" and "env".
    transport_factory injects a fake transport for tests; the default
    spawns the real subprocess. An unreachable or misbehaving server raises
    MCPClientError instead of silently dropping its tools.
    """
    factory = transport_factory if transport_factory is not None else _default_transport_factory
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for server in _normalize_servers(server_config):
        name = server["name"]
        command = list(server["command"])
        cwd = server["cwd"]
        env = server["env"]
        tools = _list_tools(name, command, cwd, env, timeout, max_output_bytes, factory)
        for tool in tools:
            spec = _spec_from_tool(
                name, command, cwd, env, tool, timeout, max_output_bytes, factory
            )
            if spec["name"] in seen:
                raise ValueError(f"duplicate external tool name: {spec['name']!r}")
            seen.add(spec["name"])
            specs.append(spec)
    return specs


__all__ = [
    "DEFAULT_MAX_OUTPUT_BYTES",
    "DEFAULT_MCP_TIMEOUT",
    "EXTERNAL_TOOL_PREFIX",
    "build_external_tool_specs",
]
