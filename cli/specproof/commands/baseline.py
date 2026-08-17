"""specproof baseline — measure the "reviewer reads only the diff" baseline.

PRODUCTION_SPEC 第 20 节 Go/No-Go #14: SpecProof 的语义回归发现率必须比
"直接让模型看 Diff"基线高 >= 25 个百分点。本命令在同一批金案例上测量
基线, 并与 SpecProof 的 eval 结果 (eval 的 eval-results.json sidecar)
逐案对比 — 同一个判定规则 (contract id / evidence 子串匹配; 负样本任何
finding 都算误报), 所以差异只能来自验证能力本身, 而不是打分口径。

基线审阅者只看 diff 文本 (截断到上限), 两种模式:
  - --no-llm (默认): 确定性 diff-reader — 保守静态规则。规则只对
    "被删除且未在附近重加" 的行生效 (删除才怀疑, 修改不怀疑), 与真实
    静态审阅者同等的保守假设; 无法验证语义, 也没有执行证据。
  - --llm: 把脱敏后的 diff + 需求摘要发给 LLM, 严格 JSON 信封返回
    findings (无 Key 时诚实报错并建议 --no-llm)。

诚实性: 基线是独立程序, 不读取 SpecProof 的任何中间产物; 两个数字
只在同一 case 集合上对比, 且报告里明确标注基线模式。
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

_LLM_BASELINE_PROMPT = """你是代码审查基线: 只看下面的 git diff 与需求摘要, 判断该 PR 是否引入回归。
只输出 JSON, 格式:
{{"findings":[{{"contract_id":"...","severity":"BLOCKER|MAJOR|MINOR",
"description":"..."}}]}}。
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


async def llm_baseline(
    diff_text: str, spec_text: str, provider: Any,
) -> list[dict[str, Any]]:
    """LLM reads the (redacted) diff and returns a strict JSON envelope."""
    from providers.base import LLMMessage
    from providers.redaction import redact_text

    safe_diff, _scrubbed = redact_text(diff_text[:_DIFF_CAP_CHARS])
    prompt = _LLM_BASELINE_PROMPT.format(
        spec_text=spec_text[:2000], diff_text=safe_diff,
    )
    response = await provider.chat(
        messages=[LLMMessage(role="user", content=prompt)],
        timeout=_LLM_TIMEOUT,
    )
    content = response.content or ""
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(content[start:end])
    except json.JSONDecodeError:
        return []
    raw = data.get("findings", [])
    if not isinstance(raw, list):
        return []
    return [f for f in raw if isinstance(f, dict)]


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
    return {
        "case": case_name,
        "verdict": verdict,
        "should_detect": should_detect,
        "detected": detected,
        "false_positive": verdict == "FALSE_POSITIVE",
        "matched_findings": len(matched),
        "contracts_found": sorted({str(f.get("contract_id")) for f in findings}),
        "findings": findings,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    """Aggregate recall/precision over judged rows (eval-compatible)."""
    should_total = sum(1 for r in rows if r["should_detect"])
    detected = sum(1 for r in rows if r["detected"])
    false_positives = sum(1 for r in rows if r["false_positive"])
    precision = (
        detected / (detected + false_positives) * 100
        if (detected + false_positives) > 0 else 100.0
    )
    recall = detected / should_total * 100 if should_total > 0 else 100.0
    return {
        "total_cases": len(rows),
        "should_detect": should_total,
        "detected": detected,
        "false_positives": false_positives,
        "precision": round(precision, 1),
        "recall": round(recall, 1),
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


def render_report(
    baseline_rows: list[dict[str, Any]],
    baseline_summary: dict[str, float | int],
    specproof: dict[str, Any] | None,
    mode: str,
) -> str:
    """Markdown comparison report."""
    lines = [
        "# SpecProof vs 只看 Diff 基线 (Go/No-Go #14)",
        "",
        f"- 基线模式: {mode}",
        f"- 案例数: {baseline_summary['total_cases']}",
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
        delta_recall = round(
            float(specproof.get("recall", 0)) - float(baseline_summary["recall"]), 1
        )
        delta_precision = round(
            float(specproof.get("precision", 0))
            - float(baseline_summary["precision"]), 1
        )
        gate = "PASS" if delta_recall >= 25.0 else "FAIL"
        lines += [
            "## 对比 (同一 case 集合)",
            "",
            "| Metric | SpecProof | Baseline | Delta |",
            "|---|---|---|---|",
            f"| Recall | {specproof.get('recall')}% | "
            f"{baseline_summary['recall']}% | {delta_recall:+.1f}pp |",
            f"| Precision | {specproof.get('precision')}% | "
            f"{baseline_summary['precision']}% | {delta_precision:+.1f}pp |",
            "",
            f"Go/No-Go #14 (+25pp recall): **{gate}** ({delta_recall:+.1f}pp)",
        ]
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
    "--llm/--no-llm", "use_llm", default=False,
    help="LLM reads the diff (default: deterministic diff-reader)",
)
def baseline_cmd(
    cases_dir: str,
    repo_path: str,
    specproof_results: str,
    output: str,
    use_llm: bool,
) -> None:
    """Measure the diff-only reviewer baseline and compare with SpecProof."""
    cases_path = Path(cases_dir)
    if not cases_path.exists():
        click.echo(f"ERROR: Cases directory not found: {cases_path}", err=True)
        raise SystemExit(1)
    repo_resolved = str(Path(repo_path).resolve())

    provider = _get_provider() if use_llm else None
    if use_llm and provider is None:
        click.echo(
            "ERROR: --llm requested but LLM_API_KEY is not configured; "
            "use --no-llm for the deterministic baseline.",
            err=True,
        )
        raise SystemExit(1)

    case_dirs = sorted(
        d for d in cases_path.iterdir()
        if d.is_dir() and d.name.startswith("case-")
    )
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
        if use_llm and provider is not None:
            findings = asyncio.run(
                llm_baseline(diff_text, spec_text, provider)
            )
        else:
            findings = deterministic_baseline(diff_text)
        row = judge_case(case_dir.name, gt, findings)
        rows.append(row)
        click.echo(
            f"  [{row['verdict']}] {case_dir.name}: "
            f"{len(findings)} finding(s), "
            f"contracts {row['contracts_found']}"
        )

    summary = summarize(rows)
    specproof = _load_specproof_results(specproof_results)
    report = render_report(rows, summary, specproof,
                           "LLM (diff + requirement)" if use_llm
                           else "deterministic diff-reader")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=2),
        encoding="utf-8",
    )

    click.echo(
        f"\nBaseline summary: recall={summary['recall']}% "
        f"precision={summary['precision']}% "
        f"fp={summary['false_positives']}"
    )
    if specproof is not None:
        delta = round(
            float(specproof.get("recall", 0)) - float(summary["recall"]), 1
        )
        click.echo(f"SpecProof recall={specproof.get('recall')}% -> "
                   f"delta={delta:+.1f}pp "
                   f"(Go/No-Go #14: {'PASS' if delta >= 25.0 else 'FAIL'})")
    else:
        click.echo(f"SpecProof results missing at {specproof_results}; "
                   "run specproof eval first.")
    click.echo(f"Report written to {out}")
