"""SpecProof CLI — main entry point.

Commands:
    specproof probe      Run LLM provider capability probe
    specproof craft      SpecCraft autonomous coding agent (M1 deterministic)
    specproof verify     Run a verification job
    specproof replay     Replay a bug capsule
    specproof eval       Run evaluation across golden cases
"""

import sys
from pathlib import Path

import click

# Ensure the project root is on sys.path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from cli.specproof.commands.baseline import baseline_cmd  # noqa: E402
from cli.specproof.commands.contract import contract_cmd  # noqa: E402
from cli.specproof.commands.craft import craft_cmd  # noqa: E402
from cli.specproof.commands.eval import eval_cmd  # noqa: E402
from cli.specproof.commands.fix import approve_cmd, fix_cmd  # noqa: E402
from cli.specproof.commands.mcp import mcp_cmd  # noqa: E402
from cli.specproof.commands.probe import probe  # noqa: E402
from cli.specproof.commands.replay import replay  # noqa: E402
from cli.specproof.commands.verify import verify  # noqa: E402


@click.group()
@click.version_option(version="0.1.0", prog_name="specproof")
def cli() -> None:
    """SpecProof — Independent Acceptance Verification for Agent-Generated Changes."""


cli.add_command(probe)
cli.add_command(verify)
cli.add_command(replay)
cli.add_command(eval_cmd)
cli.add_command(contract_cmd)
cli.add_command(craft_cmd)
cli.add_command(baseline_cmd)
cli.add_command(fix_cmd)
cli.add_command(approve_cmd)
cli.add_command(mcp_cmd)


if __name__ == "__main__":
    cli()
