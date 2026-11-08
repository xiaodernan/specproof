"""specproof doctor — operator-facing preflight probe.

The pipeline runs this same probe inline before a verification job (in the
preflight stage) and refuses to prepare workspaces when its blocking checks
fail. The same probe, exposed as a first-class CLI subcommand, answers the
on-duty question "is this machine ready to run a verification?".

Exit codes:
    0  — preflight passed (errors: none; warnings may still print)
    1  — one or more blocking errors detected
    2  — the probe itself could not run (e.g., path does not exist)
"""

from __future__ import annotations

import json
import os
import sys

import click

from agent.preflight import format_preflight_report, run_preflight


@click.command("doctor")
@click.argument(
    "repo",
    type=click.Path(exists=True, dir_okay=True, file_okay=False),
    default=".",
    required=False,
)
@click.option("--json", "as_json", is_flag=True, help="emit the full preflight dict")
@click.option("--require-jdk", type=int, default=None, help="demand a minimum JDK major")
def doctor_cmd(repo: str, as_json: bool, require_jdk: int | None) -> None:
    """Run the environment preflight this pipeline would run inline."""
    if require_jdk is not None:
        os.environ["SPECPROOF_REQUIRE_JDK"] = str(require_jdk)

    try:
        result = run_preflight(repo)
    except Exception as exc:  # noqa: BLE001 - the probe itself must not crash the shell
        click.echo(f"preflight could not run: {exc}", err=True)
        sys.exit(2)

    if as_json:
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False))
    else:
        click.echo(format_preflight_report(result))

    if result.errors:
        sys.exit(1)
    sys.exit(0)
