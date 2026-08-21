
"""publish_report node — generate the HTML verification report + lineage."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from agent.state import Phase0State


def publish_report_node(state: Phase0State) -> dict[str, Any]:
    """Generate the HTML Verification Report into state["output_dir"].

    Renders pipeline errors and UNVERIFIED contracts honestly — the report
    is the user-facing evidence artifact, so it must not invent results.

    §18.1 (Contract Lineage): the same call builds the evidence DAG from the
    real digests recorded in state (requirement text, contracts, static
    findings, differential results, per-contract evidence refs, confirmed
    findings, capsule manifests) and writes it to a standalone
    reports/<job>-lineage.json document. That document carries the complete
    DAG plus its root hash and replays independently: verify_lineage()
    recomputes every edge hash and the root from the file alone. The root
    hash is returned in state ("lineage_root") for the certificate issuer,
    and any certificate already present in state gets its extension updated.
    """
    raw_state: dict[str, Any] = cast(dict[str, Any], state)
    matrix = raw_state.get("matrix", {})
    confirmed_findings = raw_state.get("confirmed_findings", [])
    errors = raw_state.get("errors", [])
    repo_path = raw_state.get("repo_path", "")
    base_ref = raw_state.get("base_ref", "")
    head_ref = raw_state.get("head_ref", "")
    output_dir = raw_state.get("output_dir", "reports")

    from evidence.report import render_verification_report

    # The clock is read once here, at the I/O boundary; the renderer itself
    # stays a pure function of its arguments (timestamp passed in by the
    # caller, never read inside — backlog #2).
    now = datetime.now(UTC)
    html = render_verification_report(
        repo=repo_path,
        base_ref=base_ref,
        head_ref=head_ref,
        matrix=matrix,
        findings=confirmed_findings,
        errors=errors,
        generated_at=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%d-%H%M%S")
    report_path = out / f"verification-report-{timestamp}.html"
    report_path.write_text(html, encoding="utf-8")

    # ── §18.1 Contract Lineage evidence chain ─────────────────────
    from evidence.lineage import build_lineage, lineage_to_json

    dag, lineage_root = build_lineage(raw_state, built_at=now.isoformat())
    job_slug = str(raw_state.get("job_id") or "")[:8] or timestamp
    lineage_path = out / f"{job_slug}-lineage.json"
    lineage_path.write_text(lineage_to_json(dag, lineage_root), encoding="utf-8")

    result: dict[str, Any] = {
        "report_path": str(report_path.resolve()),
        "lineage_path": str(lineage_path.resolve()),
        "lineage_root": lineage_root,
        "lineage_nodes": len(dag["nodes"]),
        "lineage_edges": len(dag["edges"]),
    }

    # §A task 7: the replay evidence (lineage document + HTML report)
    # becomes locatable through the object metadata store by
    # job_id / kind / digest / contract_id. Best effort — a missing store
    # leaves the artifacts as legacy path-based objects.
    _record_replay_report_metadata(
        lineage_path=lineage_path,
        report_path=report_path,
        job_id=str(raw_state.get("job_id") or ""),
        contracts=list(raw_state.get("contracts") or []),
    )

    # Attach the lineage root to a certificate already present in state
    # (the issuer may then sign the document unchanged).
    existing_certificate = raw_state.get("certificate")
    if isinstance(existing_certificate, dict) and existing_certificate:
        certificate = dict(existing_certificate)
        extension = dict(certificate.get("extension") or {})
        extension.update({
            "lineage_root": lineage_root,
            "lineage_nodes": len(dag["nodes"]),
            "lineage_edges": len(dag["edges"]),
        })
        certificate["extension"] = extension
        result["certificate"] = certificate

    return result


def _record_replay_report_metadata(
    lineage_path: Path,
    report_path: Path,
    job_id: str,
    contracts: list[Any],
) -> None:
    """Record replay_report metadata for the lineage + HTML report.

    Both artifacts share the job's contract ids; each gets its own object
    record with its own payload digest. Recording failures are logged and
    swallowed — evidence artifacts must never be lost to metadata plumbing.
    """
    import logging

    try:
        from storage.object_metadata import record_file_object_best_effort
    except Exception:  # noqa: BLE001 — metadata is best effort
        logging.getLogger(__name__).warning("object metadata import failed")
        return
    contract_ids = [
        str(c.get("id") or "") for c in contracts if isinstance(c, dict) and c.get("id")
    ]
    for path in (lineage_path, report_path):
        if path.exists():
            record_file_object_best_effort(
                "replay_report",
                path,
                job_id=job_id,
                contract_ids=contract_ids,
            )
