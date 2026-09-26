// 术语表 —— 全站唯一来源（single source of truth）。
//
// 这些词此前只在「上手指南」页面解释一次，用户在主流程（需求覆盖 / 验收规则 /
// 风险详情）遇到它们时无处可查，只能凭上下文猜——这是"术语负担重"的核心。
// 现在把定义抽到这里，上手指南的术语表与页面内的 <Term> 悬浮解释读同一份数据，
// 任何一方措辞改动都不会与另一方漂移。
//
// 写法约定（与全站"去术语"范式一致）：
//   - definition 用一句话讲清"它是什么 / 有什么用"，不引入新术语；
//   - en 保留英文原名供检索与审计，不做展示层翻译的替代；
//   - 查不到的 id 一律返回 undefined，由 <Term> 原样透传 children ——
//     缺一句解释是诚实的，编一句错的解释会误导。

export interface GlossaryEntry {
  /** 稳定 id，供 <Term id="..."> 与上手指南引用。 */
  id: string;
  /** 中文展示名（含英文原名括注，与上手指南术语表一致）。 */
  label: string;
  /** 英文原名，供审计与检索；没有英文原名的为空串。 */
  en: string;
  /** 一句话解释。 */
  definition: string;
}

export const GLOSSARY: readonly GlossaryEntry[] = [
  {
    id: "matrix",
    label: "需求矩阵",
    en: "Matrix",
    definition:
      "逐条列出“要求是什么、如何检查、结果如何、证据在哪里”的验收清单。导航里的「需求覆盖」就是它。",
  },
  {
    id: "contract",
    label: "契约",
    en: "Contract",
    definition:
      "从需求整理出来的具体检查规则。你可以在验收规则页面查看审批状态和版本。",
  },
  {
    id: "finding",
    label: "风险发现",
    en: "Finding",
    definition:
      "一次检查发现的具体问题，包括影响、严重程度、代码位置与证据。",
  },
  {
    id: "feedback",
    label: "验收反馈",
    en: "Finding Feedback",
    definition:
      "人对某条风险判定给出的接受或打回意见。同一人对同一条风险只计一票；没有反馈不等于已接受。",
  },
  {
    id: "capsule",
    label: "证据包（Bug Capsule）",
    en: "Bug Capsule",
    definition:
      "供下载、排查或重放问题的材料。以任务实际生成的文件为准。",
  },
  {
    id: "certificate",
    label: "合并证书",
    en: "Merge Certificate",
    definition:
      "关联验证结果的签名记录，用于交付追溯。它只覆盖本次已验证的范围。",
  },
  {
    id: "craft",
    label: "开发助手（SpecCraft）",
    en: "SpecCraft",
    definition:
      "帮助规划和实现代码的 Agent。开发完成后，仍需要独立验证来支持交付判断。",
  },
  {
    id: "preflight",
    label: "环境预检",
    en: "Preflight",
    definition:
      "在跑构建之前先确认工具链（JDK / Node / Python 等）是否就绪，避免几分钟后才吐出看不懂的构建错误。",
  },
  {
    id: "evidence",
    label: "证据",
    en: "Evidence",
    definition:
      "支撑某条结论的可复核材料，例如测试输出、改动前后的行为差异、接口响应。只有结论没有证据时，状态会显示为「证据不足」。",
  },
];

const BY_ID: Record<string, GlossaryEntry> = Object.fromEntries(
  GLOSSARY.map((entry) => [entry.id, entry])
);

/** 按 id 查术语；未知 id 返回 undefined（调用方须原样透传，不得臆造）。 */
export function glossaryEntry(id: string): GlossaryEntry | undefined {
  return BY_ID[id];
}
