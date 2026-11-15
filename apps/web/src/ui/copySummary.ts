/**
 * The reviewer's copy: a Markdown digest of one verification, ready to paste
 * into a PR thread, an issue, or a Slack message.
 *
 * <p>Every value comes from what the server already returned for this job;
 * nothing is computed, guessed, or filled in when missing. A field the
 * server did not give us renders as `（未提供）` / `(not provided)` instead of
 * an invented "none". The digest is plainly marked as a machine-generated
 * artefact so a reader never mistakes it for a human verdict. Both locales
 * produce a complete digest; the language is resolved from the stored UI
 * locale at call time (or from the explicit `locale` argument).</p>
 */

import { storedLocale } from "../i18n/strings";

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

type Locale = "zh" | "en";

const TXT = {
  zh: {
    na: "（未提供）",
    sep: "：",
    title: (id: string): string => `## SpecProof 验收：${id}`,
    verdict: "裁决",
    repo: "仓库",
    changeArrow: "变更",
    spec: "需求文件",
    contracts: (total: number, passed: number, failed: number, unverified: number): string =>
      `验收条件：${total} 项（${passed} 通过 / ${failed} 未通过 / ${unverified} 未验证）`,
    risks: "### 风险发现",
    noFindings: "（未提供）（无发现），等价于 verify 目前没有产出任何 finding；它不等于\"没有缺陷\"。",
    itemsSuffix: " 项",
    capsule: "复现包",
    link: "链接（同一租户、按权限可见）",
    generated: (d: string): string =>
      `生成于：${d}（SpecProof 证据摘要，机器生成，非人工审阅结论）`,
  },
  en: {
    na: "(not provided)",
    sep: ": ",
    title: (id: string): string => `## SpecProof verification: ${id}`,
    verdict: "Verdict",
    repo: "Repository",
    changeArrow: "Change",
    spec: "Spec file",
    contracts: (total: number, passed: number, failed: number, unverified: number): string =>
      `Acceptance contracts: ${total} (${passed} passed / ${failed} failed / ${unverified} unverified)`,
    risks: "### Risk findings",
    noFindings:
      "(not provided) — no findings; this means verify produced nothing, NOT that the code is defect-free.",
    itemsSuffix: "",
    capsule: "Reproduction capsule",
    link: "Link (same tenant, permission-gated)",
    generated: (d: string): string =>
      `Generated ${d} (SpecProof evidence summary, machine-generated, not a human verdict)`,
  },
} as const;

const now = (): string => new Date().toISOString().slice(0, 10);

function capsuleName(jobId: string): string | null {
  return jobId ? `${jobId}.zip` : null;
}

export function buildMarkdownSummary(
  input: CopySummaryInput,
  locale: Locale = storedLocale(),
): string {
  const tx = TXT[locale] ?? TXT.zh;
  const NA = tx.na;
  const { job, summary, findings } = input;
  const failed = summary?.matrix_failed ?? 0;
  const passed = summary?.matrix_passed ?? 0;
  const total = summary?.contracts_total ?? 0;
  const unverified = summary?.matrix_unverified ?? 0;
  const lines: string[] = [
    tx.title(job.id),
    "",
    `- ${tx.verdict}${tx.sep}**${summary?.verdict ?? NA}**`,
    `- ${tx.repo}：\`${job.repo_path ?? NA}\``,
    `- ${tx.changeArrow}：\`${job.base_ref ?? NA}\` → \`${job.head_ref ?? NA}\``,
    `- ${tx.spec}：\`${job.spec_path ?? NA}\``,
    `- ${tx.contracts(total, passed, failed, unverified)}`,
    "",
    tx.risks,
  ];
  if (findings.length === 0) {
    lines.push(`- ${tx.noFindings}`);
  } else {
    const counts = new Map<string, number>();
    for (const f of findings) {
      const key = (f.severity || "UNKNOWN").toUpperCase();
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    lines.push(
      ...Array.from(counts.entries())
        .sort(([a], [b]) => b.localeCompare(a))
        .map(([s, n]) => `- **${s}**：${n}${tx.itemsSuffix}`),
    );
    for (const f of findings.slice(0, 5)) {
      lines.push(
        `  - ${f.contract_id ?? NA} · ${f.evidence_type ?? NA} (${f.severity ?? NA})`,
      );
    }
  }
  lines.push(
    "",
    `- ${tx.capsule}：\`${capsuleName(job.id) ?? NA}\``,
    `- ${tx.link}：\`#/jobs/${job.id}\``,
    `- ${tx.generated(now())}`,
  );
  return lines.join("\n");
}
