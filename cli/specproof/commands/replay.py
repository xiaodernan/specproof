"""specproof replay — Replay a bug capsule to verify reproducibility.

§A task 7: the capsule is resolved through the object metadata store
FIRST. The argument may be a legacy .zip path, an object id (32-hex
uuid4) or a payload digest (64-hex sha256, optionally sha256:-prefixed).
Pre-existing artifacts without a metadata record fall back to the legacy
path-based lookup, so capsules produced before the store existed keep
working unchanged. A successful replay writes replay-report.json and
records it as a replay_report object in the same store.
"""

import json
import re
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click

_UUID4HEX_RE = re.compile(r"^[0-9a-f]{32}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _open_store() -> Any | None:
    """The default object metadata store, or None when unavailable."""
    try:
        from storage.object_metadata import default_object_metadata_store

        return default_object_metadata_store()
    except Exception:  # noqa: BLE001 — legacy path fallback
        return None


def _looks_like_object_reference(reference: str) -> bool:
    """True when the reference can only be a metadata-store reference."""
    stripped = reference.strip().lower()
    if stripped.startswith("sha256:"):
        stripped = stripped[len("sha256:"):]
    return bool(_UUID4HEX_RE.fullmatch(stripped) or _HEX64_RE.fullmatch(stripped))


def _resolve_capsule(reference: str) -> tuple[Path, Any | None]:
    """Metadata store FIRST, legacy path lookup as the fallback.

    Returns (capsule_path, metadata_record_or_None). A record with a
    path_hint that no longer exists is an honest error — the store knows
    about the capsule but the payload moved.
    """
    store = _open_store()
    if store is not None:
        from storage.object_metadata import resolve_object

        found = resolve_object(store, reference)
        if found is not None:
            hint = Path(found.path_hint) if found.path_hint else None
            if hint is not None and hint.exists():
                return hint, found
            click.echo(
                "ERROR: metadata record found for the capsule, but the "
                f"recorded path no longer exists: {found.path_hint!r}",
                err=True,
            )
            raise SystemExit(1)
        if _looks_like_object_reference(reference):
            click.echo(
                "ERROR: no object metadata record matches reference "
                f"{reference!r} and it is not a file path",
                err=True,
            )
            raise SystemExit(1)
    # Legacy fallback: pre-existing artifacts live at a plain path.
    capsule = Path(reference)
    if not capsule.exists():
        click.echo(
            f"ERROR: capsule not found in the metadata store or on disk: {reference}",
            err=True,
        )
        raise SystemExit(1)
    return capsule, None


@click.command("replay")
@click.argument("capsule_ref", type=str)
@click.option("--output-dir", default=None, help="Directory to extract and replay in")
def replay(capsule_ref: str, output_dir: str | None) -> None:
    """Replay a Bug Capsule to verify the finding is reproducible.

    CAPSULE_REF is a capsule .zip path, an object id, or a payload digest.
    """
    capsule, metadata = _resolve_capsule(capsule_ref)
    if capsule.suffix != ".zip":
        click.echo("ERROR: Capsule must be a .zip file", err=True)
        raise SystemExit(1)

    # §A task 7: when the store has a record, verify the payload digest
    # before anything is extracted. Legacy capsules (no record) skip the
    # check — backward compatible.
    if metadata is not None:
        from storage.object_metadata import normalize_payload_digest, payload_sha256_of_file

        actual = normalize_payload_digest(payload_sha256_of_file(capsule))
        expected = normalize_payload_digest(
            metadata.digests.get("payload_sha256", ""),
        )
        if actual != expected:
            click.echo(
                f"ERROR: capsule payload digest mismatch for {capsule} "
                f"(expected {expected[:12]}..., got {actual[:12]}...) — "
                "the capsule was modified after it was recorded",
                err=True,
            )
            raise SystemExit(1)
        click.echo(f"Payload digest verified: {actual}")

    work_dir = (
        Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="specproof-replay-"))
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

    report_path = _write_replay_report(work_dir, capsule, manifest, metadata)
    click.echo(f"Replay report: {report_path}")

    run_script = work_dir / "run.sh"
    if not run_script.exists():
        click.echo("WARNING: No run.sh found in capsule. Cannot execute replay.")
        click.echo("Capsule contents are available for manual inspection at:")
        click.echo(f"  {work_dir}")
        return

    click.echo("\nCapsule extracted successfully.")
    click.echo(f"To execute replay, run: bash {run_script}")
    click.echo(f"Work directory: {work_dir}")


def _write_replay_report(
    work_dir: Path, capsule_path: Path, manifest: dict[str, Any], metadata: Any | None,
) -> str:
    """Write replay-report.json and record it as a replay_report object.

    The report inherits job_id / contract_ids from the capsule's metadata
    record when one exists, so by_job / by_contract queries keep working
    across the replay boundary.
    """
    from storage.object_metadata import (
        new_object_id,
        payload_sha256_of_file,
        record_file_object_best_effort,
    )

    report: dict[str, Any] = {
        "object_id": new_object_id(),
        "kind": "replay_report",
        "capsule_path": str(capsule_path),
        "capsule_object_id": metadata.object_id if metadata is not None else None,
        "capsule_payload_sha256": payload_sha256_of_file(capsule_path),
        "manifest_digest": str(manifest.get("manifest_digest") or ""),
        "finding_id": manifest.get("finding_id"),
        "severity": manifest.get("severity"),
        "job_id": str(metadata.job_id) if metadata is not None else "",
        "contract_ids": list(metadata.contract_ids) if metadata is not None else [],
        "status": "extracted",
        "replayed_at": datetime.now(UTC).isoformat(),
    }
    report_path = work_dir / "replay-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    record_file_object_best_effort(
        "replay_report",
        report_path,
        job_id=str(report["job_id"]),
        contract_ids=[str(cid) for cid in report["contract_ids"]],
    )
    return str(report_path)
