"""SpecProof MCP server package - verification tools for external agents.

The wire protocol (stdio JSON-RPC, MCP 2024-11-05) is hand-rolled in
mcp/server.py and mcp/tools.py with stdlib only. This package deliberately
does NOT import the third-party mcp SDK package (same name): the project
package shadows it on sys.path, and the protocol surface used here
(initialize / tools/list / tools/call / ping / notifications) is small and
stable.
"""

from mcp.server import (
    PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    SpecProofMCPServer,
    serve_stdio,
)
from mcp.tools import TOOLS, ToolError, call_tool

__all__ = [
    "PROTOCOL_VERSION",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOLS",
    "ToolError",
    "SpecProofMCPServer",
    "call_tool",
    "serve_stdio",
]
