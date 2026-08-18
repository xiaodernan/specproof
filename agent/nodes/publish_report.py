
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

    html = render_verification_report(
        repo=repo_path,
        base_ref=base_ref,
        head_ref=head_ref,
        matrix=matrix,
        findings=confirmed_findings,
        errors=errors,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
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
