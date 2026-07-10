"""publish_report node — generate the HTML verification report."""

from datetime import UTC, datetime
from pathlib import Path

from agent.state import Phase0State


def publish_report_node(state: Phase0State) -> dict:
    """Generate the HTML Verification Report and save to output directory."""
    matrix = state.get("matrix", {})
    confirmed_findings = state.get("confirmed_findings", [])
    repo_path = state.get("repo_path", "")
    base_ref = state.get("base_ref", "")
    head_ref = state.get("head_ref", "")

    from evidence.report import render_verification_report

    html = render_verification_report(
        repo=repo_path,
        base_ref=base_ref,
        head_ref=head_ref,
        matrix=matrix,
        findings=confirmed_findings,
    )

    output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report_path = output_dir / f"verification-report-{timestamp}.html"
    report_path.write_text(html, encoding="utf-8")

    return {"report_path": str(report_path.resolve())}
