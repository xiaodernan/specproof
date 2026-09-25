"""specproof baseline — measure the "reviewer reads only the diff" baseline.

PRODUCTION_SPEC 第 20 节 Go/No-Go #14: SpecProof 的语义回归发现率必须比
"直接让模型看 Diff"基线高 >= 25 个百分点。本命令在同一批金案例上测量
基线, 并与 SpecProof 的 eval 结果 (eval 的 eval-results.json sidecar)
逐案对比 — 同一个判定规则 (contract id / evidence 子串匹配; 负样本任何
finding 都算误报), 所以差异只能来自验证能力本身, 而不是打分口径。

基线审阅者只看 diff 文本 (截断到上限), 两种模式:
  - --mode diff-reader (默认, 亦可用 --no-llm): 确定性 diff-reader —
    保守静态规则。规则只对 "被删除且未在附近重加" 的行生效
    (删除才怀疑, 修改不怀疑), 与真实静态审阅者同等的保守假设;
    无法验证语义, 也没有执行证据。
  - --mode llm (亦可用 --llm): 把脱敏后的 diff + 需求摘要发给 LLM,
    要求以严格 JSON 信封 (或 report_findings 工具调用) 返回 findings
    (contract_id/severity/confidence/evidence 摘要)。网关降级沿用
    providers/openai_compatible.py 的 JSON Action Envelope 路径。

诚实性: 基线是独立程序, 不读取 SpecProof 的任何中间产物; 两个数字
只在同一 case 集合上对比, 且报告里明确标注基线模式。LLM 模式在
LLM_API_KEY 未配置、网关探测失败或单案调用失败时打印
"LLM baseline unavailable: ..." 并以非零码退出, 绝不编造数字;
补测步骤见 docs/eval/go-nogo.md 门槛 #14。
"""
from __future__ import annotations

import asyncio
import difflib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import click

from cli.specproof.case_set import (
    empty_pool_message,
    plan_case_dirs,
    pool_mismatch,
)
from evidence.acceptance import MetricCounts, fmt_metric, score

_DIFF_CAP_CHARS = 80_000
_LLM_TIMEOUT = 90.0
_SIMILARITY_THRESHOLD = 0.65

# Removed-line rules: (contract_id, severity, pattern on the removed line).
_REMOVED_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("AUTH-01", "BLOCKER", re.compile(r"@PreAuthorize")),
    ("TRANSACTION-01", "MAJOR", re.compile(r"@Transactional")),
    (
        "UNIQUE-01",
        "MAJOR",
        re.compile(r"(?:if\s*\(|&&|\|\|).*(?:existsBy|findBy|unique)"),
    ),
    (
        "TOKEN_INVALIDATION-01",
        "MAJOR",
        re.compile(r"(?:invalidate\w*\(|deleteToken|revokeToken)"),
    ),
    (
        "BACKWARD_COMPATIBLE-01",
        "MAJOR",
        re.compile(r"public\s+[\w<>,\s]+\s+(?:get|set)[A-Z]\w*\s*\("),
    ),
)

# Added-line rules: (contract_id, severity, pattern on the added line).
_ADDED_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "EVENT_ONCE-01",
        "MAJOR",
        re.compile(r"(?:convertAndSend|rabbitTemplate\.publish|\.publish\(|producer\.send)"),
    ),
)

# Tool schema handed to the provider: a capable gateway returns real tool
# calls; a gateway without tool_calls gets the same schema injected as the
# JSON Action Envelope prompt by the provider (see _inject_tool_prompt in
# providers/openai_compatible.py). Both shapes parse identically.
_FINDINGS_TOOL: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "report_findings",
            "description": "Report the findings of the diff-only review baseline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "contract_id": {"type": "string"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["BLOCKER", "MAJOR", "MINOR"],
                                },
                                "confidence": {"type": "number"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["contract_id", "severity"],
                        },
                    },
                },
                "required": ["findings"],
            },
        },
    },
]

_LLM_BASELINE_PROMPT = """你是代码审查基线: 只看下面的 git diff 与需求摘要, 判断该 PR 是否引入回归。
只报告 findings; 每条 finding 含 contract_id、severity (BLOCKER|MAJOR|MINOR)、
confidence (0-1 浮点数, 你对结论的把握) 与 evidence (你在 diff 中看到的证据摘要)。
可以调用 report_findings 工具, 或输出 JSON:
{{"findings":[{{"contract_id":"...","severity":"...","confidence":0.8,"evidence":"..."}}]}}。
没有发现问题就输出 {{"findings":[]}}。不要输出任何解释。

需求摘要:
{spec_text}

Diff:
{diff_text}
"""


def capture_diff(
    repo: str, base_ref: str, head_ref: str, cap: int = _DIFF_CAP_CHARS,
) -> str:
    """Capture the base..head diff text (truncated). Empty on failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "diff", base_ref + ".." + head_ref],
            capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout[:cap]


def _diff_lines(diff_text: str) -> tuple[list[str], list[str]]:
    removed = [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    added = [
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return removed, added


def _is_modification(removed_line: str, added_lines: list[str]) -> bool:
    """Deletion vs modification: a near-identical added line exists?"""
    normalized = removed_line.strip()
    if not normalized:
        return False
    for added in added_lines:
        if not added.strip():
            continue
        ratio = difflib.SequenceMatcher(None, normalized, added.strip()).ratio()
        if ratio >= _SIMILARITY_THRESHOLD:
            return True
    return False


def deterministic_baseline(diff_text: str) -> list[dict[str, Any]]:
    """Conservative static diff-reader (no contracts, no execution)."""
    removed, added = _diff_lines(diff_text)
    findings: list[dict[str, Any]] = []
    for contract_id, severity, pattern in _REMOVED_RULES:
        for line in removed:
            if not pattern.search(line):
                continue
            if _is_modification(line, added):
                continue
            findings.append({
                "contract_id": contract_id,
                "severity": severity,
                "description": "static diff-reader: removed line "
                + repr(line.strip()[:120]),
                "evidence_type": "java_source_diff",
            })
            break
    for contract_id, severity, pattern in _ADDED_RULES:
        for line in added:
            if not pattern.search(line):
                continue
            findings.append({
                "contract_id": contract_id,
                "severity": severity,
                "description": "static diff-reader: added publish call "
                + repr(line.strip()[:120]),
                "evidence_type": "java_source_diff",
            })
            break
    return findings


def _normalize_finding(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize one model-reported finding (never raises)."""
    finding: dict[str, Any] = {}
    contract_id = raw.get("contract_id") or raw.get("id") or raw.get("contract")
    if isinstance(contract_id, str) and contract_id:
        finding["contract_id"] = contract_id
    severity = raw.get("severity")
    if isinstance(severity, str) and severity:
        finding["severity"] = severity.upper()
    confidence = raw.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        finding["confidence"] = float(confidence)
    evidence = raw.get("evidence") or raw.get("description")
    if isinstance(evidence, str) and evidence:
        finding["evidence"] = evidence
    return finding


def _json_window(content: str) -> Any:
    """First JSON object/array in the content, or None."""
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end])
        except (json.JSONDecodeError, TypeError):
            pass
    start = content.find("[")
    end = content.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(content[start:end])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _extract_findings(
    content: str, tool_calls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Parse findings from tool calls or the JSON Action Envelope.

    Returns (findings, note): note is "" on a clean parse, otherwise a
    degradation note. Never raises — an unparseable model reply counts as
    "no findings reported" (an honest baseline result, not an error).
    """
    for tool_call in tool_calls or []:
        fn = tool_call.get("function") or {}
        if fn.get("name") != "report_findings":
            continue
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(args, dict) and isinstance(args.get("findings"), list):
            raw = args["findings"]
            return [
                _normalize_finding(f) for f in raw if isinstance(f, dict)
            ], ""

    parsed = _json_window(content)
    if parsed is None:
        return [], "unparseable response (no JSON found)"
    if isinstance(parsed, dict) and isinstance(parsed.get("action"), str):
        params = parsed.get("params")
        raw = params.get("findings") if isinstance(params, dict) else None
    elif isinstance(parsed, dict):
        raw = parsed.get("findings")
    elif isinstance(parsed, list):
        raw = parsed
    else:
        raw = None
    if not isinstance(raw, list):
        return [], "unparseable response (no findings list)"
    return [
        _normalize_finding(f) for f in raw if isinstance(f, dict)
    ], ""


async def llm_baseline(
    diff_text: str, spec_text: str, provider: Any,
) -> tuple[list[dict[str, Any]], str]:
    """LLM reads the (redacted) diff and reports findings.

    Reuses the provider's degradation logic: tools are passed to chat(),
    so a gateway without tool_calls gets the JSON Action Envelope prompt
    injected by the provider, while a capable gateway returns real tool
    calls — both shapes parse identically in _extract_findings.
    Returns (findings, parse_note).
    """
    from providers.base import LLMMessage
    from providers.redaction import redact_text

    safe_diff, _scrubbed = redact_text(diff_text[:_DIFF_CAP_CHARS])
    prompt = _LLM_BASELINE_PROMPT.format(
        spec_text=spec_text[:2000], diff_text=safe_diff,
    )
    response = await provider.chat(
        messages=[LLMMessage(role="user", content=prompt)],
        tools=_FINDINGS_TOOL,
        response_format={"type": "json_object"},
        timeout=_LLM_TIMEOUT,
    )
    return _extract_findings(
        response.content or "", list(response.tool_calls or [])
    )


def _get_provider() -> Any | None:
    import os

    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:
        return None


async def preflight_probe(provider: Any) -> str:
    """Run the gateway capability probe before the LLM baseline campaign.

    Returns "" when the chat capability is usable, otherwise a human
    readable reason (gateway unreachable / HTTP error / probe exception).
    """
    try:
        probe = await provider.run_probe()
    except Exception as exc:
        return f"gateway probe raised: {exc}"
    if not probe.passed("chat"):
        detail = "; ".join(str(e) for e in probe.errors) or (
            "chat capability check failed"
        )
        return f"gateway probe failed: {detail}"
    return ""


def judge_case(
    case_name: str, gt: dict[str, Any], findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply the SAME judging rules as specproof eval (contract/evidence
    matching; negative cases count ANY finding as a false positive)."""
    should_detect = bool(gt.get("should_detect", False))
    expected_contract = gt.get("expected_contract")
    expected_evidence = gt.get("expected_evidence_type", "UNKNOWN")
    min_findings = int(gt.get("expected_min_findings", 1))
    matched = [
        f for f in findings
        if (
            expected_contract and f.get("contract_id") == expected_contract
        ) or (
            expected_evidence
            and (
                expected_evidence in str(f.get("evidence_type", ""))
                or expected_evidence
                in str(f.get("contract_id", "")).lower()
            )
        )
    ]
    if should_detect:
        if len(matched) >= min_findings:
            verdict, detected = "PASS", True
        elif matched:
            verdict, detected = "PARTIAL", True
        else:
            verdict, detected = "MISS", False
    else:
        if findings:
            verdict, detected = "FALSE_POSITIVE", False
        else:
            verdict, detected = "PASS", False
    # Detection-only view: did the reviewer report ANY finding on a
    # should-detect case? Live-fire measurement (gateway fagougou,
    # 2026-08-18) showed the model finds the regression but returns
    # free-form contract ids; strict-id recall understates the semantic
    # discovery rate. Both metrics are reported; the gate uses strict.
    detected_any = bool(findings) if should_detect else False
    return {
        "case": case_name,
        "verdict": verdict,
        "should_detect": should_detect,
        "detected": detected,
        "detected_any": detected_any,
        "false_positive": verdict == "FALSE_POSITIVE",
        "matched_findings": len(matched),
        "contracts_found": sorted({str(f.get("contract_id")) for f in findings}),
        "findings": findings,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    """Aggregate recall/precision/F1 over judged rows (eval-compatible).

    Delegates the metric math to evidence.acceptance so an empty/degenerate
    sample yields ``None`` (undefined), never a misleading ``100.0``.
    """
    should_total = sum(1 for r in rows if r["should_detect"])
    detected = sum(1 for r in rows if r["detected"])
    false_positives = sum(1 for r in rows if r["false_positive"])
    negative_cases = sum(1 for r in rows if not r["should_detect"])
    detected_any = sum(1 for r in rows if r.get("detected_any"))
    metrics = score(
        MetricCounts(
            should_detect=should_total,
            detected=detected,
            false_positives=false_positives,
            negative_cases=negative_cases,
            detected_any=detected_any,
        )
    )
    return {
        "total_cases": len(rows),
        "should_detect": should_total,
        "detected": detected,
        "detected_any": detected_any,
        "false_positives": false_positives,
        "negative_cases": negative_cases,
        "precision": metrics.precision,
        "recall": metrics.recall,
        "recall_any": metrics.recall_any,
        "f1": metrics.f1,
    }


def _load_specproof_results(path: str) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _opt_float(value: Any) -> float | None:
    """Coerce a sidecar/summary metric that may be None, int, float or str.

    A JSON sidecar now carries ``null`` for metrics undefined on the sample;
    reading it into a delta must yield ``None``, not a TypeError or a fake 0.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _delta_pp(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 1)


def _pp_or_dash(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}pp"


def render_report(
    baseline_rows: list[dict[str, Any]],
    baseline_summary: dict[str, float | int | None],
    specproof: dict[str, Any] | None,
    mode: str,
    parse_failures: int = 0,
    case_set_note: str | None = None,
) -> str:
    """Markdown comparison report.

    `case_set_note` carries why the two sides are *not* the same case
    pool (computed by the caller from both sidecars' labels). It turns
    the deltas into "not comparable" rather than dropping them.
    """
    lines = [
        "# SpecProof vs 只看 Diff 基线 (Go/No-Go #14)",
        "",
        f"- 基线模式: {mode}",
        f"- 案例数: {baseline_summary['total_cases']}",
    ]
    if parse_failures > 0:
        lines.append(
            f"- LLM 解析失败案例: {parse_failures} "
            "(按无发现计分, 未编造数字)"
        )
    lines += [
        "",
        "| Case | Ground truth | Baseline verdict | Baseline contracts |",
        "|---|---|---|---|",
    ]
    for row in baseline_rows:
        lines.append(
            f"| {row['case']} | {'should-detect' if row['should_detect'] else 'negative'} "
            f"| {row['verdict']} | {', '.join(row['contracts_found']) or '—'} |"
        )
    lines.append("")
    if specproof is not None:
        sp_recall = _opt_float(specproof.get("recall"))
        base_recall = _opt_float(baseline_summary.get("recall"))
        sp_precision = _opt_float(specproof.get("precision"))
        base_precision = _opt_float(baseline_summary.get("precision"))
        sp_f1 = _opt_float(specproof.get("f1"))
        base_f1 = _opt_float(baseline_summary.get("f1"))
        d_recall = _delta_pp(sp_recall, base_recall)
        d_precision = _delta_pp(sp_precision, base_precision)
        d_f1 = _delta_pp(sp_f1, base_f1)

        def _delta_cell(value: float | None) -> str:
            return "跨池不可比" if case_set_note else _pp_or_dash(value)
        lines += [
            (
                "## 对比 (案例池不一致 — 差值不是增益)"
                if case_set_note
                else "## 对比 (同一 case 集合)"
            ),
            "",
            "| Metric | SpecProof | Baseline | Delta |",
            "|---|---|---|---|",
            f"| Recall | {fmt_metric(sp_recall)} | {fmt_metric(base_recall)} "
            f"| {_delta_cell(d_recall)} |",
            f"| Precision | {fmt_metric(sp_precision)} "
            f"| {fmt_metric(base_precision)} | {_delta_cell(d_precision)} |",
        ]
        if sp_f1 is not None or base_f1 is not None:
            lines.append(
                f"| F1 | {fmt_metric(sp_f1)} | {fmt_metric(base_f1)} "
                f"| {_delta_cell(d_f1)} |"
            )
        lines.append("")
        if case_set_note:
            lines.append(
                f"Go/No-Go #14 (+25pp recall): **无法判定** —— {case_set_note}"
                " 跨池差值不作为增益结论。"
            )
        elif d_recall is None:
            lines.append(
                "Go/No-Go #14 (+25pp recall): **无法判定** —— Recall 因样本不足"
                "未定义；空/退化的评测集不会给出可信增益。"
            )
        else:
            gate = "PASS" if d_recall >= 25.0 else "FAIL"
            lines.append(
                f"Go/No-Go #14 (+25pp recall): **{gate}** ({d_recall:+.1f}pp)"
            )
    else:
        lines += [
            "## 对比",
            "",
            "SpecProof 结果文件缺失 — 先运行 specproof eval 生成 sidecar "
            "(eval-results.json)。",
        ]
    return "\n".join(lines)


@click.command("baseline")
@click.option(
    "--cases", "cases_dir", required=True,
    help="Path to golden-cases directory",
)
@click.option(
    "--repo", "repo_path", required=True,
    help="Repository containing the scenario base/head refs",
)
@click.option(
    "--specproof-results", "specproof_results",
    default="docs/eval/eval-report.results.json",
    help="Path to SpecProof eval sidecar (JSON)",
)
@click.option(
    "--output", default="docs/eval/baseline-report.md",
    help="Output markdown report path",
)
@click.option(
    "--mode", "mode",
    type=click.Choice(["diff-reader", "llm"], case_sensitive=False),
    default="diff-reader", show_default=True,
    help="Baseline mode: diff-reader (deterministic static rules) or "
    "llm (the model reads the diff).",
)
@click.option(
    "--llm/--no-llm", "use_llm", default=None,
    help="Backward-compatible alias: --llm = --mode llm, "
    "--no-llm = --mode diff-reader; an explicit flag wins over --mode.",
)
@click.option("--include-holdout", is_flag=True, default=False,
              help="关闭 holdout 隔离，隐藏案例一起跑（报告会标明本轮未隔离）")
@click.option("--only-holdout", is_flag=True, default=False,
              help="只跑 manifest 声明的 holdout 案例")
@click.option("--holdout-manifest", default=None,
              help="holdout manifest 路径（默认 docs/eval/holdout-manifest.json）")
def baseline_cmd(
    cases_dir: str,
    repo_path: str,
    specproof_results: str,
    output: str,
    mode: str,
    use_llm: bool | None,
    include_holdout: bool,
    only_holdout: bool,
    holdout_manifest: str | None,
) -> None:
    """Measure the diff-only reviewer baseline and compare with SpecProof.

    The baseline runs the SAME case set `specproof eval` would: the
    holdout manifest is applied here too (#78), because a gain computed
    between two different pools is an arithmetic accident, not a result.
    When the stored SpecProof sidecar disagrees about its pool, the
    Go/No-Go gain is reported as undecidable instead of being printed.
    """
    if include_holdout and only_holdout:
        raise click.ClickException("--include-holdout 与 --only-holdout 互斥")
    if use_llm is False and mode == "llm":
        raise click.UsageError("--no-llm conflicts with --mode llm")
    llm_mode = use_llm if use_llm is not None else (mode == "llm")

    cases_path = Path(cases_dir)
    if not cases_path.exists():
        click.echo(f"ERROR: Cases directory not found: {cases_path}", err=True)
        raise SystemExit(1)
    repo_resolved = str(Path(repo_path).resolve())

    provider: Any | None = None
    if llm_mode:
        provider = _get_provider()
        if provider is None:
            click.echo(
                "LLM baseline unavailable: LLM_API_KEY is not configured "
                "(or is the placeholder 'replace_me'). Set the key and "
                "retry, or run --mode diff-reader / --no-llm for the "
                "deterministic baseline.",
                err=True,
            )
            raise SystemExit(2)
        probe_reason = asyncio.run(preflight_probe(provider))
        if probe_reason:
            click.echo(f"LLM baseline unavailable: {probe_reason}", err=True)
            raise SystemExit(2)

    discovered = sorted(
        d for d in cases_path.iterdir()
        if d.is_dir() and d.name.startswith("case-")
    )
    plan = plan_case_dirs(
        discovered,
        include_holdout=include_holdout,
        only_holdout=only_holdout,
        manifest_path=holdout_manifest,
    )
    case_dirs = plan.kept
    for line in plan.header_lines():
        click.echo(line)
    if not case_dirs:
        click.echo(empty_pool_message(len(discovered), plan, cases_path))
        raise SystemExit(1)
    rows: list[dict[str, Any]] = []
    for case_dir in case_dirs:
        sc_file = case_dir / "scenario.json"
        gt_file = case_dir / "ground-truth.json"
        spec_file = case_dir / "spec.md"
        scenario = (
            json.loads(sc_file.read_text(encoding="utf-8"))
            if sc_file.exists() else {}
        )
        gt = (
            json.loads(gt_file.read_text(encoding="utf-8"))
            if gt_file.exists() else {}
        )
        spec_text = (
            spec_file.read_text(encoding="utf-8")
            if spec_file.exists() else ""
        )
        base_ref = scenario.get("base_ref", "base")
        head_ref = scenario.get("head_ref", "head-v1")

        diff_text = capture_diff(repo_resolved, base_ref, head_ref)
        if not diff_text:
            click.echo(f"  SKIP {case_dir.name}: empty diff for "
                       f"{base_ref}..{head_ref}")
            continue
        findings: list[dict[str, Any]] = []
        llm_note = ""
        if llm_mode and provider is not None:
            try:
                findings, llm_note = asyncio.run(
                    llm_baseline(diff_text, spec_text, provider)
                )
            except Exception as exc:
                click.echo(
                    f"LLM baseline unavailable: case {case_dir.name} "
                    f"failed: {exc}; no report written (refusing to "
                    f"fabricate numbers).",
                    err=True,
                )
                raise SystemExit(2) from None
        else:
            findings = deterministic_baseline(diff_text)
        row = judge_case(case_dir.name, gt, findings)
        row["llm_note"] = llm_note
        rows.append(row)
        click.echo(
            f"  [{row['verdict']}] {case_dir.name}: "
            f"{len(findings)} finding(s), "
            f"contracts {row['contracts_found']}"
        )

    summary = summarize(rows)
    parse_failures = sum(1 for r in rows if r.get("llm_note"))
    summary["parse_failures"] = parse_failures
    specproof = _load_specproof_results(specproof_results)
    case_set_note = pool_mismatch(
        plan.as_json(),
        specproof.get("case_set") if specproof else None,
    )
    if case_set_note:
        click.echo(f"  ! 案例池不一致：{case_set_note}")
    report = render_report(
        rows, summary, specproof,
        "LLM (diff + requirement)" if llm_mode
        else "deterministic diff-reader",
        parse_failures=parse_failures,
        case_set_note=case_set_note,
    )

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps(
            {
                "case_set": plan.as_json(),
                "summary": summary,
                "cases": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    click.echo(
        f"\nBaseline summary: recall={fmt_metric(_opt_float(summary['recall']))} "
        f"recall_any={fmt_metric(_opt_float(summary['recall_any']))} "
        f"precision={fmt_metric(_opt_float(summary['precision']))} "
        f"f1={fmt_metric(_opt_float(summary['f1']))} "
        f"fp={summary['false_positives']}"
    )
    if specproof is not None:
        d = _delta_pp(_opt_float(specproof.get("recall")),
                      _opt_float(summary["recall"]))
        if case_set_note:
            click.echo(
                "SpecProof recall vs 基线: — 无法求增益（"
                f"{case_set_note}）。报告中的数值仍各自如实列出。"
            )
        elif d is None:
            click.echo(
                f"SpecProof recall={fmt_metric(_opt_float(specproof.get('recall')))} "
                "— 无法与基线求增益（样本不足，指标未定义）。"
            )
        else:
            click.echo(
                f"SpecProof recall={fmt_metric(_opt_float(specproof.get('recall')))} -> "
                f"delta={d:+.1f}pp "
                f"(Go/No-Go #14: {'PASS' if d >= 25.0 else 'FAIL'})"
            )
    else:
        click.echo(f"SpecProof results missing at {specproof_results}; "
                   "run specproof eval first.")
    click.echo(f"Report written to {out}")
