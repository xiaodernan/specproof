"""`specproof mcp tools` prints the catalog an external agent is about to call.

The MCP server is the surface an agent probes before calling a tool. This
command lets the same probing happen without spawning the server — the
`--json` output must be byte-for-byte the same as what `serve` would answer
`tools/list` with, or an operator wiring an MCP client gets a different
contract than the running server provides.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from cli.specproof.commands.mcp import mcp_cmd
from mcp.tools import TOOLS


def test_tools_lists_every_declared_tool() -> None:
    runner = CliRunner()
    result = runner.invoke(mcp_cmd, ["tools"])
    assert result.exit_code == 0, result.output
    for tool in TOOLS:
        assert tool["name"] in result.output
    assert "specproof_verify" in result.output
    assert "specproof_replay_info" in result.output


def test_tools_json_output_matches_the_server_catalog() -> None:
    runner = CliRunner()
    result = runner.invoke(mcp_cmd, ["tools", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == TOOLS


def test_tools_output_names_required_and_optional_args() -> None:
    runner = CliRunner()
    result = runner.invoke(mcp_cmd, ["tools"])
    assert result.exit_code == 0
    assert "repo (required)" in result.output
    assert "spec_text (required)" in result.output
    assert "capsule_name (required)" in result.output


def test_tools_help_lists_the_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(mcp_cmd, ["tools", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output
