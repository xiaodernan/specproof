import type { Locale } from "../i18n/strings";

/**
 * SpecProof IDE copy — every string the forge panel renders.
 * Two locales, one product — the forge is bilingual or it doesn't ship.
 */

export interface AnchorDoc {
  label: string;
  href: string;
  detail: Record<Locale, string>;
}

export interface CmdItem {
  id: string;
  title: Record<Locale, string>;
  body: string;
  note: Record<Locale, string>;
}

export const ANCHOR_DOCS: readonly AnchorDoc[] = [
  { label: "README", href: "https://github.com/xiaodernan/specproof#readme", detail: { zh: "从哪一炉火开始", en: "where the fire starts" } },
  { label: "POCKET_CARD.md", href: "https://github.com/xiaodernan/specproof/blob/master/docs/operations/POCKET_CARD.md", detail: { zh: "出门随身带的 30 秒口袋卡（中英双版）", en: "the 30-second pocket card (zh + en)" } },
  { label: "USER_GUIDE.md", href: "https://github.com/xiaodernan/specproof/blob/master/docs/operations/USER_GUIDE.md", detail: { zh: "五分钟到五小时的全流程指引", en: "five minutes to five hours, the full path" } },
  { label: "SPECROOF_WORLD.md", href: "https://github.com/xiaodernan/specproof/blob/master/docs/world/SPECROOF_WORLD.md", detail: { zh: "十八卷世界书，从第一卷铁证到卷十八", en: "the vol-zero-to-seventeen world book" } },
  { label: "MCP_GUIDE.zh.md", href: "https://github.com/xiaodernan/specproof/blob/master/docs/operations/MCP_GUIDE.zh.md", detail: { zh: "把 SpecProof 当 MCP 工具喂给 Claude/Codex", en: "SpecProof as an MCP tool for Claude/Codex" } },
  { label: "DEEP_OPTIMIZATION_PLAN.md", href: "https://github.com/xiaodernan/specproof/blob/master/docs/operations/DEEP_OPTIMIZATION_PLAN.md", detail: { zh: "Append-only 账本 #1 → #1756", en: "the append-only ledger #1 → #1756" } },
] as const;

export const RUNBOOK: readonly CmdItem[] = [
  { id: "demo-doctor", title: { zh: "30 秒 Demo doctor 自检", en: "Demo doctor — 30-second self-check" }, body: "python scripts/demo_doctor.py", note: { zh: "演示仓六项静态体检；不是验收，而是签名", en: "six static checks on the demo repo — not a verdict, a signature" } },
  { id: "verify-no-llm", title: { zh: "确定性验收（FAST, 无 LLM）", en: "Deterministic verdict (FAST, no LLM)" }, body: "specproof verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt --depth FAST --no-llm", note: { zh: "六条契约 checker，@PreAuthorize 反证", en: "six checkers; the @PreAuthorize removal is the counter-witness" } },
  { id: "ledger-gate", title: { zh: "账本四件套门禁", en: "Ledger four gates" }, body: "python -m pytest tests/unit/test_ledger_section_ids_are_unique.py tests/unit/test_ledger_section_numbers_are_unique.py tests/unit/test_ledger_evidence_claims_are_true.py tests/unit/test_ledger_queue_pointers_resolve.py -q", note: { zh: "任何人动了账本都得先过这四条", en: "anyone who touches the ledger must clear these four first" } },
  { id: "real-llm-smoke", title: { zh: "真实 LLM 端到端 smoke", en: "Real LLM end-to-end smoke" }, body: "python scripts/provider_smoke.py", note: { zh: "wkapi.pro + gpt-6-sol：7 阶段全绿才算通过（详见账本 #1724）", en: "wkapi.pro + gpt-6-sol; 7 stages must all pass (#1724)" } },
  { id: "cache-probe", title: { zh: "wkapi 缓存命中率探针", en: "wkapi cache-hit probe" }, body: "python scripts/provider_smoke.py --cache-probe", note: { zh: "stream=True + include_usage 车道；请勿手动关流调这项指标", en: "stream + include_usage lane; do not tune this metric by hand" } },
] as const;

