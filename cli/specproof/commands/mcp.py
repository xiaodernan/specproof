"""specproof mcp - expose SpecProof verification tools to external agents.

Runs an MCP server (protocol 2024-11-05) over stdio JSON-RPC so Claude Code /
Codex style agents can call SpecProof tools directly. The only implemented
transport is stdio (one JSON-RPC message per line); no external runtime
service is required.
"""

from __future__ import annotations

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
