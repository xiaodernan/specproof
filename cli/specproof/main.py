"""SpecProof CLI — main entry point.

Commands:
    specproof probe      Run LLM provider capability probe
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


@click.group()
@click.version_option(version="0.1.0", prog_name="specproof")
def cli() -> None:
    """SpecProof — Independent Acceptance Verification for Agent-Generated Changes."""


from cli.specproof.commands.eval import eval_cmd  # noqa: E402
from cli.specproof.commands.probe import probe  # noqa: E402
from cli.specproof.commands.replay import replay  # noqa: E402
from cli.specproof.commands.verify import verify  # noqa: E402

cli.add_command(probe)
cli.add_command(verify)
cli.add_command(replay)
cli.add_command(eval_cmd)


if __name__ == "__main__":
    cli()
