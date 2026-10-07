"""W59 wiring: external MCP tools -> craft tool registry + prompt composition.

providers.mcp_bridge.build_external_tool_specs() speaks initialize +
tools/list to each configured MCP server over stdio and returns plain
registry-envelope dicts (name "mcp.<server>.<tool>", version 1, risk
"readonly", Param-shaped dicts, a handler answering ToolResult-shaped dicts
tagged "untrusted", budget_cost). By design the bridge imports only
mcp.client and never craft.* — it stays standalone, so the injection lives
here instead of inside the bridge (its wiring note points at this module).

Layering (cycle check): craft -> providers is the established direction
(craft/llm.py and craft/loop.py already import providers.*); the bridge
never imports craft, so this module keeps the import graph acyclic. A
providers-side helper would invert the bridge's standalone contract.

Contract:

- register_external_tools(registry, server_config) converts every envelope
  into a real craft.tools.ToolSpec — version 1, risk "readonly" (the bridge
  only emits readonly specs; anything else is refused here, fail-closed) —
  and registers it, returning the registered names in order. Unconfigured
  configuration (None or an empty sequence) registers nothing and returns
  []. An unreachable or misbehaving server raises MCPClientError, exactly
  like the bridge: external tools are never silently dropped.
- The handler wraps the bridge's ToolResult-shaped dict into
  ToolResult(**...); every result carries security_tags=["untrusted"] and
  the registry's full dispatch gate chain (validation / approval /
  redaction / untrusted tagging) still runs for every call.
- Schema mapping caveat (bridge documented): JSON properties of type
  "object"/"null" have no craft Param kind and map to "str" as a passthrough
  advisory. The craft gate therefore insists on a string value for those
  params (strict registry validation, 计划书 §6.4) while the external
  server stays the validation authority for its own schema.
- Prompt composition: external results are untrusted data by contract
  (craft/tools.py §6.3) and must never ride in the stable system prefix.
  external_result_section() is the single composition point — it renders one
  ToolResult and wraps it via craft.llm.wrap_data_section exactly like the
  loop wraps the tool envelope today (CraftLoop._diagnose_context). Prompt
  composers in the loop/agent surface external results through this helper.
  The tool surface needs no extra work: once the specs are registered, the
  registry envelope block (already DATA-section-wrapped by the loop)
  automatically lists the mcp.* tools.
- Observability (#211): every external call executes through the handler
  this module builds, so the mcp.* surface is metered there —
  mcp_tool_calls_total (denominator: one per handler entrance),
  mcp_tool_errors_<code>_total (every status="error" result; the word is
  read back from the bridge's documented "[CODE] " summary prefix and
  lowercased — the closed vocabulary is mcp.client's stable CODE_* set,
  and a prefix-less summary lands in the declared "unprefixed" fallback
  word instead of going uncounted) and mcp_tool_seconds (caller-visible
  latency of the whole per-call session, finally semantics). Gate
  refusals decided before the handler (unknown tool / version / arguments
  / approval) never reach this boundary — they tick tool_calls_total and
  the in-tree refusal/error families instead, so the surfaces partition
  instead of stacking. A handler raise (broken envelope dict) is a
  dispatch-level crash (tool_errors_execution_failed), not an mcp word.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from typing import Any

from observability.metrics import incr, observe_duration
from providers.mcp_bridge import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MCP_TIMEOUT,
    EXTERNAL_TOOL_PREFIX,
    TransportFactory,
    build_external_tool_specs,
)

from .llm import wrap_data_section
from .schemas import ToolResult
from .tools import Param, ToolRegistry, ToolSpec

ServerConfig = Mapping[str, Any] | Sequence[Mapping[str, Any]] | None

#: Caller-visible duration ladder for mcp_tool_seconds (#211). The
#: measured region is one whole per-call session: the bridge opens a
#: fresh stdio session per call, so spawn + initialize + tools/call +
#: close all count. 0.25s keeps sub-second local spawns resolvable; the
#: top aligns with 2x the default per-request timeout (initialize and
#: tools/call can each burn DEFAULT_MCP_TIMEOUT before the handler
#: answers), so even a double-timeout call lands in a finite bucket. A
#: custom longer timeout may overflow the top bucket (+Inf) — the
#: honest residual.
MCP_TOOL_BUCKETS: tuple[float, ...] = (
    0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 240.0,
)

#: The bridge stamps every failure summary with the documented
#: "[CODE] " prefix (the codes are mcp.client's stable set). The meter
#: reads the stamp back at this boundary; the regex is anchored to the
#: start so only a leading stamp classifies, and a prefix-less error
#: summary lands in _UNSTAMPED_WORD — a declared read-side word, never
#: a silent drop.
_STAMP = re.compile(r"^\[([A-Z][A-Z0-9_]*)\]")
_UNSTAMPED_WORD = "unprefixed"


def _error_word(summary: str) -> str:
    match = _STAMP.match(summary)
    return match.group(1).lower() if match else _UNSTAMPED_WORD


def _tool_spec_from_envelope(envelope: dict[str, Any]) -> ToolSpec:
    """One bridge envelope dict -> a real registry ToolSpec (W59)."""
    name = envelope["name"]
    if not isinstance(name, str) or not name.startswith(EXTERNAL_TOOL_PREFIX):
        raise ValueError(f"external tool name {name!r} 缺少 {EXTERNAL_TOOL_PREFIX!r} 前缀")
    if envelope.get("risk") != "readonly":
        raise ValueError(f"external tool {name!r} risk 必须为 'readonly' (fail-closed)")
    raw_handler = envelope["handler"]
    raw_cost = envelope["budget_cost"]
    params = tuple(Param(**param) for param in envelope["params"])

    def handler(arguments: dict[str, Any]) -> ToolResult:
        # #211: the external MCP surface is metered here — every mcp.*
        # call reaching this handler is one call (gate refusals happen
        # upstream in dispatch and never arrive), errors are the
        # bridge's status="error" dicts classified by their [CODE]
        # stamp, and the histogram observes the whole call with finally
        # semantics (failures and ToolResult-construction crashes stay
        # in the sequence; the crash itself is dispatch's
        # execution_failed, not an mcp word).
        incr("mcp_tool_calls_total")
        started = time.perf_counter()
        try:
            result = ToolResult(**raw_handler(arguments))
        finally:
            observe_duration(
                "mcp_tool_seconds",
                time.perf_counter() - started,
                buckets=MCP_TOOL_BUCKETS,
            )
        if result.status == "error":
            incr(f"mcp_tool_errors_{_error_word(result.summary)}_total")
        return result

    def budget_cost(arguments: dict[str, Any]) -> dict[str, int]:
        del arguments  # fixed per-call estimate, copied verbatim from the envelope
        return {"seconds": int(raw_cost["seconds"]), "bytes": int(raw_cost["bytes"])}

    return ToolSpec(
        name=name,
        version=int(envelope["version"]),
        risk="readonly",
        params=params,
        handler=handler,
        budget_cost=budget_cost,
    )


def register_external_tools(
    registry: ToolRegistry,
    server_config: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    *,
    timeout: float = DEFAULT_MCP_TIMEOUT,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    transport_factory: TransportFactory | None = None,
) -> list[str]:
    """Register every external MCP tool from server_config; return the names.

    Unconfigured configuration (None or an empty sequence) registers nothing
    and returns [] — a deliberate no-op, external tools are strictly opt-in.
    Each server is probed once (initialize + tools/list); every listed tool
    becomes a ToolSpec mcp.<server>.<tool> v1 risk="readonly" whose handler
    answers through the bridge and whose results are tagged "untrusted".
    An unreachable or misbehaving server raises MCPClientError (honest —
    the bridge never silently drops tools).
    """
    envelopes = build_external_tool_specs(
        server_config,
        timeout=timeout,
        max_output_bytes=max_output_bytes,
        transport_factory=transport_factory,
    )
    registered: list[str] = []
    for envelope in envelopes:
        spec = _tool_spec_from_envelope(envelope)
        registry.register(spec)
        registered.append(spec.name)
    return registered


def external_result_section(result: ToolResult) -> str:
    """Prompt-composition surface for one external tool result (W59).

    External results are untrusted data by contract (craft/tools.py §6.3):
    the text a prompt composer shows to the model must ride inside an
    explicit DATA section — never merged into the stable system prefix.
    This helper is the single composition point; the loop (and any agent
    surface) renders a ToolResult through it instead of formatting inline.
    """
    lines = [f"external tool result: status={result.status}"]
    if result.summary:
        lines.append(f"summary: {result.summary}")
    if result.output_head:
        lines.append("output head:")
        lines.append(result.output_head)
    if result.output_tail:
        lines.append("output tail:")
        lines.append(result.output_tail)
    if result.truncated:
        lines.append("(output was truncated)")
    if result.security_tags:
        lines.append("security_tags: " + ", ".join(result.security_tags))
    return wrap_data_section("\n".join(lines))


__all__ = [
    "MCP_TOOL_BUCKETS",
    "ServerConfig",
    "external_result_section",
    "register_external_tools",
]
