"""HTML report renderer for SpecProof Phase 0."""

from datetime import UTC, datetime
from typing import Any


def render_verification_report(
    repo: str,
    base_ref: str,
    head_ref: str,
    matrix: dict[str, Any],
    findings: list[dict],
) -> str:
    """Render the full HTML Verification Report."""
    rows = matrix.get("rows", [])
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    rows_html = ""
    for r in rows:
        result_class = {
            "PASS": "pass",
            "FAIL": "fail",
            "UNVERIFIED": "unverified",
        }.get(r.get("result", ""), "")
        symbols = ", ".join(r.get("changed_symbols", [])) or "—"
        rows_html += f"""<tr class="{result_class}">
            <td>{r.get("contract_id", "")}</td>
            <td class="req">{r.get("requirement", "")}</td>
            <td>{symbols}</td>
            <td>{r.get("experiment", "")}</td>
            <td class="{result_class}">{r.get("result", "")}</td>
            <td>{r.get("evidence", "")}</td>
        </tr>"""

    findings_html = ""
    for f in findings:
        findings_html += f"""<div class="finding {f.get("severity", "").lower()}">
            <h3>[{f.get("severity", "")}] {f.get("contract_id", "")}</h3>
            <p>{f.get("description", "")}</p>
            <p>Confidence: {f.get("confidence", 0):.0%} | Type: {f.get("evidence_type", "")}</p>
        </div>"""

    passed = matrix.get("passed", 0)
    failed = matrix.get("failed", 0)
    total = matrix.get("total_rows", len(rows))
    verdict = "VERIFIED" if failed == 0 else "BLOCKED"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SpecProof Verification Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               max-width: 1200px; margin: 0 auto; padding: 40px 20px;
               background: #0d1117; color: #c9d1d9; }}
        header {{ border-bottom: 1px solid #30363d; padding-bottom: 20px; margin-bottom: 30px; }}
        header h1 {{ font-size: 24px; color: #58a6ff; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
        .summary div {{ background: #161b22; border: 1px solid #30363d;
                        padding: 12px 20px; border-radius: 6px; }}
        .verdict {{ font-size: 18px; font-weight: 700; padding: 10px 20px; border-radius: 6px;
                    display: inline-block; }}
        .verdict.blocked {{ background: #490202; color: #ff7b72; border: 1px solid #ff7b72; }}
        .verdict.verified {{ background: #04260f; color: #7ee787; border: 1px solid #7ee787; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
        th {{ background: #161b22; color: #8b949e; font-weight: 600; }}
        tr:hover {{ background: #1c2128; }}
        .req {{ max-width: 300px; }}
        .pass {{ color: #7ee787; }}
        .fail {{ color: #ff7b72; background: #1a0505; }}
        .unverified {{ color: #8b949e; }}
        .finding {{ background: #161b22; border: 1px solid #30363d;
                    padding: 16px; margin: 12px 0; border-radius: 6px; }}
        .finding.blocker {{ border-left: 3px solid #ff7b72; }}
        .finding.major {{ border-left: 3px solid #d29922; }}
        footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #30363d;
                  color: #484f58; font-size: 12px; }}
    </style>
</head>
<body>
    <header>
        <h1>SpecProof Verification Report</h1>
        <div class="summary">
            <div>Repository: {repo}</div>
            <div>Base: {base_ref}</div>
            <div>Head: {head_ref}</div>
            <div>Generated: {now}</div>
        </div>
        <div class="verdict {verdict.lower()}">{verdict}</div>
        <div class="summary" style="margin-top: 12px;">
            <div>Contracts: {total}</div>
            <div style="color: #7ee787;">Passed: {passed}</div>
            <div style="color: #ff7b72;">Failed: {failed}</div>
        </div>
    </header>

    <section>
        <h2>Requirement-to-Evidence Matrix</h2>
        <table>
            <thead>
                <tr>
                    <th>Contract ID</th>
                    <th>Requirement</th>
                    <th>Changed Symbols</th>
                    <th>Experiment</th>
                    <th>Result</th>
                    <th>Evidence</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </section>

    <section>
        <h2>Findings ({len(findings)})</h2>
        {
        findings_html
        if findings
        else ('<p style="color: #7ee787;">No findings. All contracts passed.</p>')
    }
    </section>

    <footer>
        SpecProof v0.1.0 | Evidence hashes not available offline |
        No API keys stored in this report
    </footer>
</body>
</html>"""


def render_eval_report(results: list[dict]) -> str:
    """Render evaluation results HTML page with precision/recall."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Compute summary stats
    total = len(results)
    detected = sum(1 for r in results if r.get("verdict") in ("PASS", "PARTIAL"))
    should = sum(1 for r in results if r.get("should_detect"))
    fp = sum(1 for r in results if r.get("verdict") == "FALSE_POSITIVE")
    precision = detected / (detected + fp) * 100 if (detected + fp) > 0 else 100.0
    recall = detected / should * 100 if should > 0 else 100.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    verdict_color = {
        "PASS": "#7ee787",
        "PARTIAL": "#d29922",
        "MISS": "#ff7b72",
        "FALSE_POSITIVE": "#ff7b72",
    }

    rows_html = ""
    for r in results:
        v = r.get("verdict", "")
        color = verdict_color.get(v, "#c9d1d9")
        rows_html += f"""<tr>
            <td>{r.get("case", "")}</td>
            <td style="color:{color};font-weight:700">{v}</td>
            <td>{r.get("expected_contract", "")}</td>
            <td>{r.get("expected_severity", "")}</td>
            <td>{r.get("expected_evidence", "")}</td>
            <td>{r.get("matched_findings", 0)}</td>
            <td>{r.get("matched_severities", "")}</td>
            <td>{r.get("contracts_found", "")}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>SpecProof Evaluation Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 1100px; margin: 0 auto; padding: 40px 20px;
           background: #0d1117; color: #c9d1d9; }}
    h1 {{ color: #58a6ff; margin-bottom: 10px; }}
    .meta {{ color: #8b949e; margin-bottom: 24px; }}
    .stats {{ display: flex; gap: 16px; margin: 20px 0; flex-wrap: wrap; }}
    .stat {{ background: #161b22; border: 1px solid #30363d;
             padding: 12px 20px; border-radius: 6px; text-align: center; }}
    .stat .value {{ font-size: 24px; font-weight: 700; }}
    .stat .label {{ font-size: 12px; color: #8b949e; }}
    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #30363d; }}
    th {{ background: #161b22; color: #8b949e; font-weight: 600; font-size: 13px; }}
    tr:hover {{ background: #1c2128; }}
</style></head>
<body>
    <h1>SpecProof Evaluation Report</h1>
    <p class="meta">Generated: {now} | Cases: {total}</p>

    <div class="stats">
        <div class="stat">
            <div class="value" style="color:#58a6ff">{precision:.0f}%</div>
            <div class="label">Precision</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#7ee787">{recall:.0f}%</div>
            <div class="label">Recall</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#d29922">{f1:.0f}%</div>
            <div class="label">F1 Score</div>
        </div>
        <div class="stat">
            <div class="value">{detected}/{should}</div>
            <div class="label">Detected / Should Detect</div>
        </div>
        <div class="stat">
            <div class="value">{fp}</div>
            <div class="label">False Positives</div>
        </div>
    </div>

    <table>
        <thead><tr>
            <th>Case</th><th>Verdict</th><th>Expected Contract</th>
            <th>Expected Severity</th><th>Expected Evidence</th>
            <th>Matched</th><th>Severities</th><th>Contracts Found</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
</body></html>"""
