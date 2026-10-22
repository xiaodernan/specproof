"""HTML report renderer for SpecProof Phase 0."""
from datetime import UTC, datetime
from html import escape
from typing import Any

from evidence.acceptance import (
    AcceptanceResult,
    MetricCounts,
    fmt_metric,
    score,
    severity_reconciliation,
)
from evidence.verdict import VERDICT_NEEDS_REVIEW, evaluate_verification


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


def _render_deep_evidence(
    deep: dict[str, Any] | None, note: str, safe: Any
) -> str:
    """Render the DEEP tier's own disclosures (backlog #7/#136/#138).

    DEEP runs the mutation campaign and the state-delta experiment against a
    seeded cache volume. The sandbox therefore produces a cache-integrity
    statement that used to die at the node boundary: the archived HTML report
    — the artifact a reviewer opens months later — said nothing about it, so
    an honest "NOT VERIFIED" was unreadable and looked like a clean run.

    Absent disclosure is rendered as absent, never as verified. When DEEP was
    not requested the section says which tier ran instead of implying a deep
    campaign that never happened.
    """
    payload = deep if isinstance(deep, dict) else {}
    tier_note = str(note or "").strip()
    if not payload and "DEEP" not in tier_note:
        return ""

    cache = str(payload.get("cache_integrity") or "").strip()
    if cache:
        cache_html = f'<p class="unverified">Cache integrity: {safe(cache)}</p>'
    elif payload:
        # The campaign ran and said nothing about the cache. Saying "clean"
        # here would be a fabrication, so the absence itself is the finding.
        cache_html = (
            '<p class="unverified">Cache integrity: not disclosed by this run '
            "(no cache note was recorded on the deep test runs).</p>"
        )
    else:
        cache_html = ""

    report_file = str(payload.get("deep_report_file") or "").strip()
    file_html = (
        f'<p class="muted">Sidecar evidence: {safe(report_file)}</p>'
        if report_file
        else ""
    )

    return f"""<section>
        <h2>Deep Verification</h2>
        {f'<p class="muted">{safe(tier_note)}</p>' if tier_note else ""}
        {cache_html}
        {file_html}
    </section>"""


def _gate_verdict(entry: Any, safe: Any) -> tuple[str, str, str]:
    """One gate row as (css class, verdict word, detail text).

    The verdict word comes from the recorded ``passed`` flag and nothing else:
    a gate whose entry carries no flag is rendered 未判定, because inventing
    "passed" for a gate the pipeline never judged is exactly the lie this
    section exists to prevent.
    """
    if isinstance(entry, list):
        # A gate that checked a set has to disclose the set, including the
        # empty one: "0 capsules checked" is not "capsules are intact".
        if not entry:
            return "unverified", "未判定", "没有条目可校验（该门没有获得任何证据）"
        checked = len(entry)
        failed = [
            item
            for item in entry
            if not (isinstance(item, dict) and item.get("digest_ok") is True)
        ]
        detail = "; ".join(_capsule_line(item, safe) for item in entry)
        if failed:
            return "fail", "未通过", f"{len(failed)}/{checked} 条不符: {detail}"
        return "pass", "通过", f"{checked} 条全部相符: {detail}"
    if isinstance(entry, dict):
        if "passed" not in entry:
            return "unverified", "未判定", _detail_of(entry, safe)
        ok = bool(entry["passed"])
        return ("pass", "通过", _detail_of(entry, safe)) if ok else (
            "fail", "未通过", _detail_of(entry, safe)
        )
    return "unverified", "未判定", safe(str(entry))


def _capsule_line(item: Any, safe: Any) -> str:
    if not isinstance(item, dict):
        return str(safe(str(item)))
    capsule = safe(str(item.get("capsule", "?")))
    if item.get("digest_ok") is True:
        return f"{capsule} 摘要相符"
    if item.get("digest_ok") is False:
        return f"{capsule} 摘要不符"
    return f"{capsule} 无法打开: {safe(str(item.get('error', '')))}"


def _detail_of(entry: dict[str, Any], safe: Any) -> str:
    """Render whatever the gate recorded besides its own verdict."""
    parts = [
        f"{safe(str(key))}={safe(str(value))}"
        for key, value in sorted(entry.items())
        if key != "passed" and value not in (None, "")
    ]
    return "; ".join(parts) if parts else "该门未记录任何细节"


def _render_release_gates(
    release: dict[str, Any] | None, note: str, safe: Any
) -> str:
    """Render the RELEASE tier's own gates (backlog #150).

    ``--depth RELEASE`` is a shipped CLI choice and ``run_release_checks`` runs
    on every graph execution, recomputing reproducibility and every capsule
    digest. Their verdict used to die at the node boundary: the archived report
    — the artifact a reviewer opens, and diffs months later — said nothing about
    them, so a RELEASE campaign that failed to reproduce its own evidence looked
    exactly like one that passed.

    Absent gates are rendered as absent, never as passed. When RELEASE was not
    requested the section carries the node's own note and produces no per-gate
    verdict at all.
    """
    payload = release if isinstance(release, dict) else {}
    tier_note = str(note or "").strip()
    if not payload and "RELEASE" not in tier_note:
        return ""
    if not payload:
        return f"""<section>
        <h2>Release Gates 发布门</h2>
        {f'<p class="muted">{safe(tier_note)}</p>' if tier_note else ""}
        <p class="unverified">本次没有执行任何发布门: 该档位未请求, "未跑"不等于"已通过"。</p>
    </section>"""

    gates = payload.get("gates")
    gate_rows = gates if isinstance(gates, dict) else {}
    rendered = sorted(
        (name, _gate_verdict(entry, safe)) for name, entry in gate_rows.items()
    )
    flag_passed = payload.get("passed") is True
    # The tier's own summary flag cannot certify the headline by itself (#152): a
    # gate that checked an empty roster, or recorded no flag, reads 未判定 in its row,
    # and "未判定" may never support an acceptance — not in the verdict policy, and
    # not as the first sentence a reviewer reads here. So the headline and the
    # verdict answer to the same rule, and one run cannot look passed in one and
    # blocked in the other.
    # The slot is a gate row's word, not the report's `verdict` field: naming it
    # `verdict` here would claim this file compares that field against a Chinese word
    # outside its declared scale (the #109 channel gate reads identifiers, not intent).
    uncredited = [name for name, (_, word, _) in rendered if word != "通过"]
    if not flag_passed:
        overall, overall_word = "fail", "未通过"
    elif uncredited:
        # safe() on the names: the headline carries strings the payload supplied, and
        # this section's rule is that everything from a run stays text (#150 case 7).
        names = "、".join(str(safe(name)) for name in uncredited)
        overall, overall_word = "fail", f"未通过（有门未判定或未通过: {names}）"
    else:
        overall, overall_word = "pass", "通过"
    rows = "".join(
        f'<li class="{css}">{safe(name)}: {word} — {detail}</li>'
        for name, (css, word, detail) in rendered
    )
    if not rows:
        # The tier ran yet recorded no gate: the reader has to be able to tell
        # that from a campaign whose gates all passed.
        rows = '<li class="unverified">该档位没有记录任何一道门</li>'
    return f"""<section>
        <h2>Release Gates 发布门</h2>
        {f'<p class="muted">{safe(tier_note)}</p>' if tier_note else ""}
        <p class="{overall}">发布门总判定: {overall_word}</p>
        <ul class="gates">{rows}</ul>
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
    deep: dict[str, Any] | None = None,
    deep_note: str = "",
    release: dict[str, Any] | None = None,
    release_note: str = "",
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
            if r.get("dependency_install"):
                differential += (
                    '<br /><small class="surface">deps: '
                    f"{safe(r.get('dependency_install'))}</small>"
                )
        else:
            differential = '<span class="muted">not run</span>'
        # What the external observation could NOT say for this contract
        # (#365). Rendered under the row, because it qualifies what the
        # verdict rests on: a reader who sees PASS must be able to tell
        # whether the outside of the JVM was compared at all, and where
        # that comparison stopped. Capture-only — it never changes the
        # result word.
        limits = r.get("observation_limits") or []
        if isinstance(limits, (list, tuple)):
            for limit in limits:
                differential += (
                    '<br /><small class="surface">'
                    f"{safe(limit)}</small>"
                )
        # WHERE the evidence for this contract can be fetched from, and in
        # what state (#366b / #367). The row's verdict says what was
        # decided; this says where the bytes that back it live, what
        # their digest is, and whether an index row points at them. A
        # durable-but-unindexed capsule is rendered as the ghost it is.
        artifact_records = r.get("artifact_records") or []
        if isinstance(artifact_records, (list, tuple)):
            for record in artifact_records:
                if not isinstance(record, dict):
                    continue
                ref = str(record.get("ref") or "")
                digest = str(record.get("sha256") or "")
                size = int(record.get("size_bytes") or 0)
                if ref:
                    detail = f"artifact: {ref}"
                    if digest:
                        detail += f" (sha256 {digest[:16]}…, {size} bytes)"
                    differential += (
                        '<br /><small class="surface">'
                        f"{safe(detail)}</small>"
                    )
                else:
                    differential += (
                        '<br /><small class="surface">'
                        "artifact: not uploaded — the capsule is a local file "
                        "only</small>"
                    )
                note = str(record.get("note") or "")
                if note:
                    differential += (
                        '<br /><small class="surface">'
                        f"{safe(note)}</small>"
                    )
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
        # #261: render the in-flight evidence run_differential captures
        # (behavioral_evidence / db_violation_evidence / db_state_detail) so the
        # user-facing report explains *why* a (possibly scaffold-wiped) verdict
        # was reached. Capture-only: these never change the verdict, they only
        # make the already-captured signal visible. Emitted only when present.
        detail_bits: list[str] = []
        db_detail = f.get("db_state_detail")
        if db_detail:
            detail_bits.append(
                f'<p class="finding-detail">DB state: {safe(db_detail)}</p>'
            )
        db_v = f.get("db_violation_evidence") or {}
        if db_v.get("head_observed"):
            detail_bits.append(
                '<p class="finding-detail">In-flight DB-state violation observed '
                f'(marker: {safe(db_v.get("marker", ""))}, '
                f'head-only: {safe(str(db_v.get("head_only", False)))})</p>'
            )
        beh = f.get("behavioral_evidence") or {}
        if beh.get("captured"):
            detail_bits.append(
                '<p class="finding-detail">Behavioral regression captured '
                f'in-flight: {safe(beh.get("note", ""))}</p>'
            )
        detail_html = "".join(detail_bits)
        findings_html += (
            f'<div class="finding {safe(f.get("severity", "").lower())}">'
            f'<h3>[{safe(f.get("severity", ""))}] {safe(f.get("contract_id", ""))}</h3>'
            f'<p>{safe(f.get("description", ""))}</p>'
            f'<p>Confidence: {f.get("confidence", 0):.0%} | '
            f'Type: {safe(f.get("evidence_type", ""))}</p>'
            f'{detail_html}'
            f'</div>'
        )

    error_list = errors or []
    decision = evaluate_verification(matrix, findings=findings, errors=error_list)
    passed, failed, unverified, total = (
        decision.passed, decision.failed, decision.unverified, decision.total,
    )
    verdict = decision.status
    if verdict == VERDICT_NEEDS_REVIEW:
        # The policy now says NEEDS_REVIEW in its own spelling; THIS
        # channel's canonical spelling has a space (the notify channel
        # folds it to the underscore form on read). One spelling per
        # channel — that is the whole point of the channel registry.
        verdict = "NEEDS REVIEW"
    elif verdict == "BLOCKED" and not findings and not failed:
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
        # The report channel's spelling has a SPACE (the notify channel
        # folds it to the underscore form on read) — the verdict is
        # normalised to it above, so the underscore spelling is deliberately
        # NOT a key here: a key nothing can reach is a dead word.
        "NEEDS REVIEW": "pending",
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
    deep_html = _render_deep_evidence(deep, deep_note, safe)
    release_html = _render_release_gates(release, release_note, safe)

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
        .verdict.pending {{ background: #3d2e00; color: #e3b341; border: 1px solid #e3b341; }}
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
    {deep_html}
    {release_html}

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


def render_eval_report(
    results: list[dict[str, Any]],
    acceptance: AcceptanceResult | None = None,
) -> str:
    """Render evaluation results HTML page with precision/recall.

    ``acceptance`` is the verdict the CLI decided (``evidence.acceptance``);
    when supplied, the page states it and — for an unpinned PASS — says what
    that PASS does and does not assert (#223). This report is the artifact CI
    uploads, so a reader must not have to consult the job log to learn that
    "PASS" meant "the sample was large enough".
    """
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Compute summary stats via the single honest source (evidence.acceptance):
    # a metric is None when its sample denominator is 0 — never a fake 100%.
    total = len(results)
    detected = sum(1 for r in results if r.get("verdict") in ("PASS", "PARTIAL"))
    should = sum(1 for r in results if r.get("should_detect"))
    fp = sum(1 for r in results if r.get("verdict") == "FALSE_POSITIVE")
    neg = sum(1 for r in results if not r.get("should_detect"))
    # The cases that were NEVER MEASURED. They are out of the recall
    # denominator (a case nobody judged is not a case nobody found), so
    # without this number a run with one unmeasured case would read
    # "51/51 - 100%" and hide the fact that a case was never compared
    # (ledger #399). The number has to be ON the page.
    not_measured = sum(1 for r in results if r.get("verdict") == "NOT_RUN")
    not_measured_cases = [r for r in results if r.get("verdict") == "NOT_RUN"]
    not_measured_color = "#d29922" if not_measured else "#c9d1d9"
    _m = score(MetricCounts(should_detect=should, detected=detected,
                            false_positives=fp, negative_cases=neg))
    sev = severity_reconciliation(results)
    sev_agree_txt = fmt_metric(sev["severity_agreement"], undefined="样本不足")
    sev_prec_txt = fmt_metric(sev["severe_precision"], undefined="样本不足")
    precision_txt = fmt_metric(_m.precision, undefined="样本不足")
    recall_txt = fmt_metric(_m.recall, undefined="样本不足")
    f1_txt = fmt_metric(_m.f1, undefined="样本不足")

    acceptance_card = ""
    acceptance_note = ""
    if acceptance is not None:
        acc_color = {"PASS": "#7ee787", "FAIL": "#ff7b72"}.get(
            acceptance.status, "#d29922"
        )
        acceptance_card = (
            '<div class="stat">'
            f'<div class="value" style="color:{acc_color}">{acceptance.status}</div>'
            '<div class="label">Acceptance</div>'
            "</div>"
        )
        if acceptance.status == "PASS" and not acceptance.floors_pinned:
            acceptance_note = (
                '<p class="meta">Acceptance PASS 仅表示<b>样本充足</b>：'
                "未设 recall / precision / f1 下限，这三个指标不构成合格判据。"
                "</p>"
            )
        else:
            reasons = [*acceptance.insufficient, *acceptance.failures]
            if reasons:
                acceptance_note = (
                    '<p class="meta">Acceptance 判据：'
                    + "；".join(escape(r) for r in reasons)
                    + "</p>"
                )

    verdict_color = {
        "PASS": "#7ee787",
        "PARTIAL": "#d29922",
        "MISS": "#ff7b72",
        "FALSE_POSITIVE": "#ff7b72",
        # "Not measured" is neither a pass nor a failure: the case was
        # never compared. It gets its own colour so a reader does not
        # have to guess whether amber means "partial" or "not run".
        "NOT_RUN": "#d29922",
    }

    # The cases that were never measured, and WHY. A row that only says
    # NOT_RUN leaves the reader with no way to act on it; the reason and
    # the failing side's own output are the diagnosis (ledger #399).
    not_measured_html = ""
    if not_measured_cases:
        blocks = []
        for r in not_measured_cases:
            reason = escape(str(r.get("errors") or "")) or "(no reason recorded)"
            tail = str(r.get("base_output") or "")
            tail_html = (
                f'<pre style="white-space:pre-wrap;font-size:12px;'
                f'background:#161b22;border:1px solid #30363d;padding:8px;'
                f'border-radius:6px">{escape(tail[-800:])}</pre>'
                if tail else ""
            )
            blocks.append(
                f'<li><b>{escape(str(r.get("case", "")))}</b> — {reason}'
                f"{tail_html}</li>"
            )
        not_measured_html = (
            '<h2 style="font-size:16px;margin-top:28px">'
            f"Not measured ({len(not_measured_cases)})</h2>"
            '<p class="meta">这些案例<b>没有被比较过</b>：证据那一条路回来的是'
            '「判不了」（NON_REPRODUCIBLE）。它们<b>不在</b> Recall 的分母里，'
            '也<b>不是</b>「没查出来」。</p>'
            f"<ul>{''.join(blocks)}</ul>"
        )

    rows_html = ""
    for r in results:
        v = r.get("verdict", "")
        color = verdict_color.get(v, "#c9d1d9")
        sev_color = (
            "#ff7b72" if r.get("severity_match") is False else "#c9d1d9"
        )
        rows_html += f"""<tr>
            <td>{r.get("case", "")}</td>
            <td style="color:{color};font-weight:700">{v}</td>
            <td>{r.get("expected_contract", "")}</td>
            <td>{r.get("expected_severity", "")}</td>
            <td>{r.get("expected_evidence", "")}</td>
            <td>{r.get("matched_findings", 0)}</td>
            <td style="color:{sev_color}">{r.get("matched_severities", "")}</td>
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
        </div>        <div class="stat">
            <div class="value">{fp}</div>
            <div class="label">False Positives</div>
        </div>
        <div class="stat">
            <div class="value" style="color:{not_measured_color}">{not_measured}</div>
            <div class="label">Not Measured</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#79c0ff">{sev_agree_txt}</div>
            <div class="label">Severity Agreement</div>
        </div>
        <div class="stat">
            <div class="value" style="color:#79c0ff">{sev_prec_txt}</div>
            <div class="label">Severe Precision</div>
        </div>
        {acceptance_card}
    </div>
    {acceptance_note}

    <table>
        <thead><tr>
            <th>Case</th><th>Verdict</th><th>Expected Contract</th>
            <th>Expected Severity</th><th>Expected Evidence</th>
            <th>Matched</th><th>Severities</th><th>Contracts Found</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table>
    {not_measured_html}
</body></html>"""
