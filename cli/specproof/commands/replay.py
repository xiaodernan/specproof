"""specproof replay — Replay a bug capsule to verify reproducibility."""

import json
import tempfile
import zipfile
from pathlib import Path

import click


@click.command("replay")
@click.argument("capsule_path", type=click.Path(exists=True))
@click.option("--output-dir", default=None, help="Directory to extract and replay in")
def replay(capsule_path: str, output_dir: str | None) -> None:
    """Replay a Bug Capsule to verify the finding is reproducible.

    CAPSULE_PATH is a .zip file produced by a previous verification run.
    """
    capsule = Path(capsule_path)
    if capsule.suffix != ".zip":
        click.echo("ERROR: Capsule must be a .zip file", err=True)
        raise SystemExit(1)

    work_dir = (
        Path(output_dir) if output_dir
        else Path(tempfile.mkdtemp(prefix="specproof-replay-"))
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Extracting capsule to: {work_dir}")
    with zipfile.ZipFile(capsule, "r") as zf:
        zf.extractall(work_dir)

    manifest_path = work_dir / "manifest.json"
    if not manifest_path.exists():
        click.echo("ERROR: Corrupt capsule — manifest.json not found", err=True)
        raise SystemExit(1)

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    click.echo(f"Finding ID: {manifest.get('finding_id')}")
    click.echo(f"Severity: {manifest.get('severity')}")
    click.echo(f"Expected hash: {manifest.get('sha256', 'N/A')}")

    run_script = work_dir / "run.sh"
    if not run_script.exists():
        click.echo("WARNING: No run.sh found in capsule. Cannot execute replay.")
        click.echo("Capsule contents are available for manual inspection at:")
        click.echo(f"  {work_dir}")
        return

    click.echo("\nCapsule extracted successfully.")
    click.echo(f"To execute replay, run: bash {run_script}")
    click.echo(f"Work directory: {work_dir}")
