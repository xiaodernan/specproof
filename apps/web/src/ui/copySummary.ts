/**
 * The reviewer's copy: a Markdown digest of one verification, ready to paste
 * into a PR thread, an issue, or a Slack message.
 *
 * <p>Every value comes from what the server already returned for this job;
 * nothing is computed, guessed, or filled in when missing. A field the
 * server did not give us renders as `（未提供）` instead of an invented "none".
 * The digest is plainly marked as a machine-generated artefact so a reader
 * never mistakes it for a human verdict.</p>
 */

export interface CopySummaryJob {
  id: string;
  base_ref?: string | null | undefined;
  head_ref?: string | null | undefined;
  repo_path?: string | null | undefined;
  spec_path?: string | null | undefined;
  status?: string | null | undefined;
  created_at?: number | string | null | undefined;
}

export interface CopySummarySummary {
  verdict: string | null;
  contracts_total: number | null;
  matrix_passed: number | null;
  matrix_failed: number | null;
  matrix_unverified: number | null;
  errors: string[] | null;
}

export interface CopySummaryFinding {
  severity?: string;
  contract_id?: string;
  evidence_type?: string;
}

export interface CopySummaryInput {
  job: CopySummaryJob;
  summary: CopySummarySummary | null;
  findings: CopySummaryFinding[];
}

const NA = "（未提供）";
const now = (): string => new Date().toISOString().slice(0, 10);

function capsuleName(jobId: string): string | null {
  return jobId ? `${jobId}.zip` : null;
}

export function buildMarkdownSummary(input: CopySummaryInput): string {
  const { job, summary, findings } = input;
  const failed = summary?.matrix_failed ?? 0;
  const passed = summary?.matrix_passed ?? 0;
  const total = summary?.contracts_total ?? 0;
  const unverified = summary?.matrix_unverified ?? 0;
  const lines: string[] = [
    `## SpecProof 验收：${job.id}`,
    "",
    `- 裁决：**${summary?.verdict ?? NA}**`,
    `- 仓库：\`${job.repo_path ?? NA}\``,
    `- 变更：\`${job.base_ref ?? NA}\` → \`${job.head_ref ?? NA}\``,
    `- 需求文件：\`${job.spec_path ?? NA}\``,
    `- 验收条件：${total} 项（${passed} 通过 / ${failed} 未通过 / ${unverified} 未验证）`,
    "",
    "### 风险发现",
  ];
  if (findings.length === 0) {
    lines.push(`- ${NA}（无发现），等价于 verify 目前没有产出任何 finding；它不等于"没有缺陷"。`);
  } else {
    const counts = new Map<string, number>();
    for (const f of findings) {
      const key = (f.severity || "UNKNOWN").toUpperCase();
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    lines.push(
      ...Array.from(counts.entries())
        .sort(([a], [b]) => b.localeCompare(a))
        .map(([s, n]) => `- **${s}**：${n} 项`)
    );
    for (const f of findings.slice(0, 5)) {
      lines.push(`  - ${f.contract_id ?? NA} · ${f.evidence_type ?? NA} (${f.severity ?? NA})`);
    }
  }
  lines.push(
    "",
    `- 复现包：\`${capsuleName(job.id) ?? NA}\``,
    `- 链接（同一租户、按权限可见）：\`#/jobs/${job.id}\``,
    `- 生成于：${now()}（SpecProof 证据摘要，机器生成，非人工审阅结论）`,
  );
  return lines.join("\n");
}
