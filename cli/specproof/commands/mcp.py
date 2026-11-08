"""specproof mcp - expose SpecProof verification tools to external agents.

Runs an MCP server (protocol 2024-11-05) over stdio JSON-RPC so Claude Code /
Codex style agents can call SpecProof tools directly. The only implemented
transport is stdio (one JSON-RPC message per line); no external runtime
service is required.
"""

from __future__ import annotations

import json

import click


@click.group(name="mcp")
def mcp_cmd() -> None:
    """MCP server - external agents call SpecProof tools over stdio JSON-RPC."""


@mcp_cmd.command("serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio"], case_sensitive=False),
    default="stdio",
    show_default=True,
    help="Transport to serve (only stdio is implemented; streamable HTTP is out of scope).",
)
def serve(transport: str) -> None:
    """Run the MCP server until stdin closes."""
    if transport != "stdio":
        raise click.ClickException(
            f"transport {transport!r} is not implemented - only stdio is supported"
        )
    from mcp.server import serve_stdio

    serve_stdio()


@mcp_cmd.command("tools")
@click.option("--json", "as_json", is_flag=True, help="print the full catalog as JSON")
def tools(as_json: bool) -> None:
    """List the MCP tools an agent can call, without starting the server.

    Intended for pre-flight probing and for operators wiring an MCP client
    (Claude Code / Codex / Cursor / OpenCode / any JSON-RPC stdio client)
    and want to know the exact tool names, argument shapes and descriptions
    this checkout exposes - one `specproof mcp tools --json` prints the same
    payload the MCP server answers `tools/list` with.
    """
    from mcp.tools import TOOLS

    if as_json:
        click.echo(json.dumps(TOOLS, ensure_ascii=False, indent=2))
        return

    for tool in TOOLS:
        schema = tool.get("inputSchema", {})
        props = schema.get("properties", {})
        required = list(schema.get("required", []))
        optional = sorted(set(props) - set(required))
        desc = " ".join(str(tool.get("description", "")).split())
        click.echo(f"{tool['name']}")
        click.echo(f"  {desc}")
        if required:
            args = ", ".join(f"{name} (required)" for name in required)
            click.echo(f"  args: {args}")
        if optional:
            click.echo(f"  opts: {', '.join(optional)}")
        click.echo("")
