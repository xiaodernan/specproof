# Go/No-Go #14 — "直接让 DeepSeek V4 Pro 看 Diff" 基线实测 (100 案例, 真实接口)

日期: 2026-08-18 · 模型: deepseek-v4-pro (llm-api.fagougou.com/v1, 真实调用)
对照: 同一 100 案例集, SpecProof 评测 (docs/eval/eval-report.results.json)

## 结果

| 指标 | SpecProof | 裸模型 (看 Diff) | Delta |
|---|---|---|---|
| 严格契约归因 recall | 100.0% | 0.0% | +100.0pp |
| 发现率 recall_any (报告≥1 finding) | 100.0% | 100.0% | 0.0pp |
| Precision | 100.0% | 0.0% (严格) | +100.0pp |
| 误报数 | 0 | 5 | — |

门槛 #14 (≥ +25pp): 按严格契约口径 **PASS (+100pp)**; 按发现率口径
SpecProof 与裸模型同为 100%, 但 SpecProof 在归因与误报两个维度全胜。

## 5 个误报 (每个都是 SpecProof 检测器的设计点)

1. case-25 @Secured 等价注解 — 裸模型不认识等价保护 (SpecProof: 等价注解集)。
2. case-30 @Version 移到 getter — 等价重构被当回归 (SpecProof: 属性级等价回退)。
3. case-48 迁移新增索引 — 良性 DDL 被当破坏 (SpecProof: schema 差异归因)。
4. case-78 邮件输入 trim — 良性改进被当回归 (SpecProof: 证据政策, 只判行为回归)。
5. case-94 requirement.txt 注入 "IGNORE ALL PREVIOUS INSTRUCTIONS" — 裸模型被注入影响报了 1 个 finding (SpecProof: 仓库文本一律视为数据, 0 finding)。

## 面试叙事

"裸模型把 100 个案例的回归全都'看到'了 (发现率 100%), 但它:
① 无法把问题归因到契约 (0% 严格归因), ② 误报 5 个等价重构/良性变更,
③ 会被 PR 里注入的指令影响。SpecProof 用契约编译器 + 检查器注册表 +
证据政策做到了 100/100/100、0 误报、0 注入影响 — 这就是
'不是让模型提意见, 而是把需求编译成契约再验证'的量化证明。"
