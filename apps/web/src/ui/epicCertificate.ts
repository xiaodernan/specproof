/**
 * 史诗验收纪要 —— the grand-bureau copy of one verification, meant to be
 * read out loud at a release ritual.
 *
 * <p>Every line is compiled from what the server actually returned for this
 * job; nothing is embellished beyond sentence dress. Missing values render
 * as `（未提供）` — never an invented figure. The document is marked as a
 * machine-assembled artefact so no reader mistakes it for a human approval.</p>
 */

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

const NA = "（未提供）";
const now = (): string => new Date().toISOString().slice(0, 10);

const verdictEpic = (verdict: string | null): string => {
  if (!verdict) return NA;
  if (verdict === "VERIFIED") return "验讫";
  if (verdict === "BLOCKED") return "受阻";
  if (verdict === "FAILED") return "执行未成";
  if (verdict === "NEEDS_REVIEW") return "待议";
  if (verdict === "CANCELLED") return "中辍";
  return verdict;
};

export function buildEpicCertificate(input: EpicCertificateInput): string {
  const { job, summary, findings } = input;
  const total = summary?.contracts_total ?? null;
  const passed = summary?.matrix_passed ?? null;
  const failed = summary?.matrix_failed ?? null;
  const unverified = summary?.matrix_unverified ?? null;
  const passedStr = passed === null ? NA : String(passed);
  const failedStr = failed === null ? NA : String(failed);
  const unverifiedStr = unverified === null ? NA : String(unverified);
  const totalStr = total === null ? NA : String(total);

  const lines: string[] = [
    `# 史诗验收纪要 · ${job.id}`,
    "",
    `> 铁证如山 · 验收官执印 · 机器拼奏 · 人工定夺`,
    "",
    "## 一、卷宗",
    "",
    "| 项 | 实录 |",
    "|---|------|",
    `| 裁决 | **${verdictEpic(summary?.verdict ?? null)}**（${summary?.verdict ?? NA}） |`,
    `| 仓库 | \`${job.repo_path ?? NA}\` |`,
    `| 变更 | \`${job.base_ref ?? NA}\` → \`${job.head_ref ?? NA}\` |`,
    `| 需求 | \`${job.spec_path ?? NA}\` |`,
    `| 验收条件 | ${totalStr} 项（${passedStr} 通过 / ${failedStr} 未通过 / ${unverifiedStr} 未验证） |`,
    "",
    "## 二、铁证",
  ];

  if (findings.length === 0) {
    lines.push(
      "",
      "此卷无发现。**这不等于「没有缺陷」，只等于「本次验收未逮到」——缺什么铁证，就该补什么证据，而不是宣布胜利。**",
    );
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
        .map(([s, n]) => `- **${s}** · ${n} 项`),
      "",
      ...findings.slice(0, 6).map((f) =>
        `- ${f.contract_id ?? NA} · ${f.evidence_type ?? NA}（${f.severity ?? NA}）`,
      ),
    );
  }

  lines.push(
    "",
    "## 三、印记",
    "",
    `- 复现包：\`${job.id ? job.id + ".zip" : NA}\``,
    `- 链接（同租户、按权限可见）：\`#/jobs/${job.id}\``,
    `- 生成于：${now()}（SpecProof 史诗纪要 · 机器拼奏 · **不是人工裁决** · 判决以上方矩阵为准）`,
  );
  return lines.join("\n");
}
