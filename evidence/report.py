"""HTML report renderer for SpecProof Phase 0."""
from datetime import UTC, datetime
from html import escape
from typing import Any

from evidence.acceptance import MetricCounts, fmt_metric, score
from evidence.verdict import evaluate_verification


def _render_preflight(preflight: dict[str, Any] | None, safe: Any) -> str:
    """Render the environment preflight section (roadmap Phase 1.4).

    The report is the artifact people archive and diff months later, so it
    must record the environment the verdict was produced in — otherwise a
    FAILED verdict is unreadable ("did the code fail, or the machine?").

    Only facts that were actually probed are rendered. When the pipeline
    skipped preflight (upstream input error) the report says so instead of
    implying a healthy environment.
    """
    if not isinstance(preflight, dict) or not preflight:
        return ""

    checks = [c for c in (preflight.get("checks") or []) if isinstance(c, dict)]
    errors = [str(e) for e in (preflight.get("errors") or [])]
    warnings = [str(w) for w in (preflight.get("warnings") or [])]
    skipped = [str(s) for s in (preflight.get("skipped") or [])]
    language = str(preflight.get("language") or "unknown")
    not_run = str(preflight.get("not_run") or "")

    if not checks and not errors and not warnings:
        reason = {
            "upstream_errors": (
                "Input validation failed before the environment was probed."
            ),
            "probe_error": (
                "The environment probe itself failed; the pipeline continued."
            ),
            "disabled_by_SPECPROOF_PREFLIGHT": (
                "Environment preflight was disabled by configuration."
            ),
        }.get(not_run, "Environment preflight did not run.")
        return (
            '<section><h2>Environment Preflight</h2>'
            f'<p class="unverified">{safe(reason)}</p></section>'
        )

    ok = not errors
    status_html = (
        '<span class="pass">satisfied</span>' if ok
        else '<span class="fail">not satisfied</span>'
    )

    def _row(cell: dict[str, Any]) -> str:
        status = str(cell.get("status", ""))
        css = {"PASS": "pass", "FAIL": "fail"}.get(status, "unverified")
        return (
            f'<tr><td>{safe(cell.get("check", ""))}</td>'
            f'<td class="{css}">{safe(status)}</td>'
            f'<td>{safe(cell.get("detail", ""))}</td></tr>'
        )

    rows = "".join(_row(c) for c in checks)
    table = (
        "<table><thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        if rows else ""
    )

    errors_html = ""
    if errors:
        items = "".join(f"<li>{safe(e)}</li>" for e in errors)
        errors_html = f'<h3 class="fail">Blocking ({len(errors)})</h3><ul>{items}</ul>'
    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{safe(w)}</li>" for w in warnings)
        warnings_html = f"<h3>Warnings ({len(warnings)})</h3><ul>{items}</ul>"
    skipped_html = ""
    if skipped:
        items = ", ".join(safe(s) for s in sorted(set(skipped)))
        skipped_html = (
            f'<p class="unverified">Not applicable to a {safe(language)} project '
            f"(deliberately not run): {items}</p>"
        )

    return f"""<section>
        <h2>Environment Preflight</h2>
        <p>Detected project type: <strong>{safe(language)}</strong> — environment {status_html}</p>
        {table}
        {errors_html}
        {warnings_html}
        {skipped_html}
    </section>"""


def render_verification_report(
    repo: str,
    base_ref: str,
    head_ref: str,
    matrix: dict[str, Any],
    findings: list[dict[str, Any]],
    errors: list[str] | None = None,
    generated_at: str | None = None,
    preflight: dict[str, Any] | None = None,
) -> str:
    """Render the full HTML Verification Report.

    generated_at is the caller-supplied report timestamp; when it is passed
    the render is a pure function of its arguments (same inputs ->
    byte-identical HTML), which keeps report rendering deterministic for
    tests and replay. When omitted the legacy behavior is preserved: the
    renderer stamps the current UTC time itself.
    """
    def safe(value: Any) -> str:
        return escape(str(value), quote=True)

    raw_rows = matrix.get("rows")
    rows = (
        [r for r in raw_rows if isinstance(r, dict)]
        if isinstance(raw_rows, (list, tuple)) else []
    )
    now = (
        generated_at
        if generated_at is not None
        else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    rows_html = ""
    for r in rows:
        result_class = {
            "PASS": "pass",
            "FAIL": "fail",
            "UNVERIFIED": "unverified",
        }.get(r.get("result", ""), "")
        symbols = ", ".join(r.get("changed_symbols", [])) or "—"
        # Base-vs-head comparison and WHERE it ran. Both are omitted when the
        # pipeline recorded nothing: an absent differential must not render as
        # a passing one, and a run without a sandbox must say so. The surface
        # token is kept verbatim (audit) and never rounded to "sandboxed".
        if r.get("base_result") or r.get("head_result"):
            differential = (
                f"{safe(r.get('base_result', '') or '?')} → "
                f"{safe(r.get('head_result', '') or '?')}"
            )
            if r.get("attribution"):
                differential += f" ({safe(r.get('attribution'))})"
            if r.get("execution_surface"):
                differential += (
                    '<br /><small class="surface">'
                    f"{safe(r.get('execution_surface'))}</small>"
                )
        else:
            differential = '<span class="muted">not run</span>'
        rows_html += f"""<tr class="{result_class}">
            <td>{safe(r.get("contract_id", ""))}</td>
            <td class="req">{safe(r.get("requirement", ""))}</td>
            <td>{safe(symbols)}</td>
            <td>{safe(r.get("experiment", ""))}</td>
            <td class="diff">{differential}</td>
            <td class="{result_class}">{safe(r.get("result", ""))}</td>
            <td>{safe(r.get("evidence", ""))}</td>
        </tr>"""

    findings_html = ""
    for f in findings:
        findings_html += f"""<div class="finding {safe(f.get("severity", "").lower())}">
            <h3>[{safe(f.get("severity", ""))}] {safe(f.get("contract_id", ""))}</h3>
            <p>{safe(f.get("description", ""))}</p>
            <p>Confidence: {f.get("confidence", 0):.0%} |
            Type: {safe(f.get("evidence_type", ""))}</p>
        </div>"""

    error_list = errors or []
    decision = evaluate_verification(matrix, findings=findings, errors=error_list)
    passed, failed, unverified, total = (
        decision.passed, decision.failed, decision.unverified, decision.total,
    )
    verdict = decision.status
    if verdict == "BLOCKED" and not findings and not failed:
        verdict = "NEEDS REVIEW"
    coverage_html = (
        '<section><h2>验收结论说明</h2><ul>'
        + "".join(f"<li>{safe(reason)}</li>" for reason in decision.reasons)
        + "</ul></section>"
        if decision.reasons else ""
    )

    verdict_class = {
        "FAILED": "blocked",
        "BLOCKED": "blocked",
        "NEEDS REVIEW": "blocked",
        "VERIFIED": "verified",
    }[verdict]

    errors_html = ""
    if error_list:
        items = "".join(f"<li>{safe(e)}</li>" for e in error_list)
        errors_html = (
            f'<section><h2 style="color:#ff7b72;">Pipeline Errors ({len(error_list)})</h2>'
            f"<ul>{items}</ul></section>"
        )

    preflight_html = _render_preflight(preflight, safe)

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
        .diff {{ white-space: nowrap; }}
        /* The execution surface is a safety disclosure: a run without a
           container sandbox executed the change's own tests on the host. */
        .diff .surface {{ color: #d29922; font-family: ui-monospace, SFMono-Regular, monospace; }}
        .muted {{ color: #8b949e; }}
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
            <div>Repository: {safe(repo)}</div>
            <div>Base: {safe(base_ref)}</div>
            <div>Head: {safe(head_ref)}</div>
            <div>Generated: {safe(now)}</div>
        </div>
        <div class="verdict {verdict_class}">{verdict}</div>
        <div class="summary" style="margin-top: 12px;">
            <div>Contracts: {total}</div>
            <div style="color: #7ee787;">Passed: {passed}</div>
            <div style="color: #ff7b72;">Failed: {failed}</div>
            <div style="color: #8b949e;">Unverified: {unverified}</div>
        </div>
    </header>

    {errors_html}
    {coverage_html}
    {preflight_html}

    <section>
        <h2>Requirement-to-Evidence Matrix</h2>
        <table>
            <thead>
                <tr>
                    <th>Contract ID</th>
                    <th>Requirement</th>
                    <th>Changed Symbols</th>
                    <th>Experiment</th>
                    <th>Differential</th>
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
        else ('<p style="color: #8b949e;">No findings confirmed by the Review Court. '
              'See the matrix above for per-contract results.</p>')
    }
    </section>

    <footer>
        SpecProof v0.1.0 | SHA-256 evidence digests included where available |
        No API keys stored in this report
    </footer>
</body>
</html>"""


def render_eval_report(results: list[dict[str, Any]]) -> str:
    """Render evaluation results HTML page with precision/recall."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Compute summary stats via the single honest source (evidence.acceptance):
    # a metric is None when its sample denominator is 0 — never a fake 100%.
    total = len(results)
    detected = sum(1 for r in results if r.get("verdict") in ("PASS", "PARTIAL"))
    should = sum(1 for r in results if r.get("should_detect"))
    fp = sum(1 for r in results if r.get("verdict") == "FALSE_POSITIVE")
    neg = sum(1 for r in results if not r.get("should_detect"))
    _m = score(MetricCounts(should_detect=should, detected=detected,
                            false_positives=fp, negative_cases=neg))
    precision_txt = fmt_metric(_m.precision, undefined="样本不足")
    recall_txt = fmt_metric(_m.recall, undefined="样本不足")
    f1_txt = fmt_metric(_m.f1, undefined="样本不足")

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
            <div class="value" style="color:#58a6ff">{precision_txt}</div>
            <div class="label">Precision</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#7ee787">{recall_txt}</div>
            <div class="label">Recall</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#d29922">{f1_txt}</div>
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
