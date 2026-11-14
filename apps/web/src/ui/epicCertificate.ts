/**
 * 史诗验收纪要 —— the grand-bureau copy of one verification, meant to be
 * read out loud at a release ritual.
 *
 * <p>Every line is compiled from what the server actually returned for this
 * job; nothing is embellished beyond sentence dress. Missing values render
 * as `（未提供）` / `Not provided` — never an invented figure. The document
 * is marked as a machine-assembled artefact so no reader mistakes it for a
 * human approval. The markdown it emits follows the stored UI locale:
 * zh mode yields a Chinese bureau document; en mode yields its English twin.</p>
 */

import { storedLocale } from "../i18n/strings";

const isZh = (): boolean => storedLocale() === "zh";

export interface EpicCertificateJob {
  id: string;
  base_ref?: string | null | undefined;
  head_ref?: string | null | undefined;
  repo_path?: string | null | undefined;
  spec_path?: string | null | undefined;
  status?: string | null | undefined;
  created_at?: number | string | null | undefined;
}

export interface EpicCertificateSummary {
  verdict: string | null;
  contracts_total: number | null;
  matrix_passed: number | null;
  matrix_failed: number | null;
  matrix_unverified: number | null;
  errors: string[] | null;
}

export interface EpicCertificateFinding {
  severity?: string;
  contract_id?: string;
  evidence_type?: string;
  description?: string;
}

export interface EpicCertificateInput {
  job: EpicCertificateJob;
  summary: EpicCertificateSummary | null;
  findings: EpicCertificateFinding[];
}

interface Copy {
  notProvided: string;
  title: (id: string) => string;
  motto: string;
  secVerdict: string;
  fieldHeader: string;
  recordHeader: string;
  verdict: string;
  repo: string;
  change: string;
  spec: string;
  acceptance: string;
  passed: string;
  failed: string;
  unverified: string;
  contractsUnit: string;
  items: (total: string, passed: string, failed: string, unverified: string) => string;
  secFindings: string;
  noFindings: string;
  countsItem: (n: number) => string;
  findingItem: (contract: string, evidence: string, severity: string) => string;
  secSeal: string;
  reproBundle: string;
  linkLabel: string;
  generatedAt: (date: string) => string;
  verdictWord: Record<string, string>;
}

const COPY: Record<"zh" | "en", Copy> = {
  zh: {
    notProvided: "（未提供）",
    title: (id) => `# 史诗验收纪要 · ${id}`,
    motto: "> 铁证如山 · 验收官执笔 · 机器拼奏 · 人工定夺",
    secVerdict: "## 一、卷首",
    fieldHeader: "字段",
    recordHeader: "实录",
    verdict: "裁决",
    repo: "仓库",
    change: "变更",
    spec: "需求",
    acceptance: "验收条件",
    contractsUnit: "项",
    passed: "通过",
    failed: "未通过",
    unverified: "未验证",
    items: (t, p, f, u) => `${t} 项（${p} 通过 / ${f} 未通过 / ${u} 未验证）`,
    secFindings: "## 二、铁证",
    noFindings: "此卷无发现。**这不等于「没有缺陷」，只等于「本次验收未逮到」——缺什么铁证，就该补什么证据，而不是宣布胜利。**",
    countsItem: (n) => `${n} 项`,
    findingItem: (c, e, s) => `- ${c} · ${e}（${s}）`,
    secSeal: "## 三、印章",
    reproBundle: "复现包",
    linkLabel: "链接（同租户、按权限可见）",
    generatedAt: (d) => `- 生成于：${d}（SpecProof 史诗纪要 · 机器拼奏 · **不是人工裁决** · 判决以上方矩阵为准）`,
    verdictWord: {
      VERIFIED: "验讫",
      BLOCKED: "受阻",
      FAILED: "执行未成",
      NEEDS_REVIEW: "待议",
      CANCELLED: "中辍",
    },
  },
  en: {
    notProvided: "Not provided",
    title: (id) => `# Certificate of Verification · ${id}`,
    motto: "> Iron, verified · written by the assessor · assembled by machine · decided by humans",
    secVerdict: "## I · The Verdict",
    fieldHeader: "Field",
    recordHeader: "Record",
    verdict: "Verdict",
    repo: "Repository",
    change: "Change",
    spec: "Spec",
    acceptance: "Acceptance",
    contractsUnit: "",
    passed: "passed",
    failed: "failed",
    unverified: "unverified",
    items: (t, p, f, u) => `${t} contract(s) (${p} passed / ${f} failed / ${u} unverified)`,
    secFindings: "## II · The Evidence",
    noFindings: "No findings in this certificate. **This is not “no defects” — it is “nothing caught this time”. Name the missing evidence; do not declare victory.**",
    countsItem: (n) => `${n} finding(s)`,
    findingItem: (c, e, s) => `- ${c} · ${e} (${s})`,
    secSeal: "## III · The Seal",
    reproBundle: "Reproduction bundle",
    linkLabel: "Link (same tenant, role-gated)",
    generatedAt: (d) => `- Generated: ${d} (SpecProof certificate · machine-assembled · **not a human approval** · the verdict stands with the matrix above)`,
    verdictWord: {
      VERIFIED: "Verified",
      BLOCKED: "Blocked",
      FAILED: "Execution failed",
      NEEDS_REVIEW: "Needs review",
      CANCELLED: "Cancelled",
    },
  },
};

const now = (): string => new Date().toISOString().slice(0, 10);

export function buildEpicCertificate(input: EpicCertificateInput): string {
  const { job, summary, findings } = input;
  const c: Copy = COPY[isZh() ? "zh" : "en"];
  const na = c.notProvided;
  const verdictEpic = (verdict: string | null): string => {
    if (!verdict) return na;
    return c.verdictWord[verdict] ?? verdict;
  };

  const total = summary?.contracts_total ?? null;
  const passed = summary?.matrix_passed ?? null;
  const failed = summary?.matrix_failed ?? null;
  const unverified = summary?.matrix_unverified ?? null;
  const passedStr = passed === null ? na : String(passed);
  const failedStr = failed === null ? na : String(failed);
  const unverifiedStr = unverified === null ? na : String(unverified);
  const totalStr = total === null ? na : String(total);

  const lines: string[] = [
    c.title(job.id),
    "",
    c.motto,
    "",
    c.secVerdict,
    "",
    `| ${c.fieldHeader} | ${c.recordHeader} |`,
    "|---|------|",
    `| ${c.verdict} | **${verdictEpic(summary?.verdict ?? null)}** (${summary?.verdict ?? na}) |`,
    `| ${c.repo} | \`${job.repo_path ?? na}\` |`,
    `| ${c.change} | \`${job.base_ref ?? na}\` → \`${job.head_ref ?? na}\` |`,
    `| ${c.spec} | \`${job.spec_path ?? na}\` |`,
    `| ${c.acceptance} | ${c.items(totalStr, passedStr, failedStr, unverifiedStr)} |`,
    "",
    c.secFindings,
  ];

  if (findings.length === 0) {
    lines.push("", c.noFindings);
  } else {
    const counts = new Map<string, number>();
    for (const f of findings) {
      const key = (f.severity || "UNKNOWN").toUpperCase();
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    lines.push(
      "",
      ...Array.from(counts.entries())
        .sort(([a], [b]) => (a < b ? 1 : -1))
        .map(([s, n]) => `- **${s}** · ${c.countsItem(n)}`),
      "",
      ...findings.slice(0, 6).map((f) =>
        c.findingItem(f.contract_id ?? na, f.evidence_type ?? na, f.severity ?? na),
      ),
    );
  }

  lines.push(
    "",
    c.secSeal,
    "",
    `- ${c.reproBundle}：\`${job.id ? job.id + ".zip" : na}\``,
    `- ${c.linkLabel}：\`#/jobs/${job.id}\``,
    c.generatedAt(now()),
  );
  return lines.join("\n");
}
