# 计费与用量账本设计 (工业化阶段 6)

状态: 设计定稿 (2026-08-18) · 现状: TokenBudget 为全局内存态, 无租户级账本。
目标: 可计费、可审计、可限额的用量账本; 依赖阶段 1 (租户) 先行。

## 1. 模型

- plans(id, name, price_monthly, quotas JSON: {jobs_verify, jobs_craft, llm_tokens,
  cases, seats}, overage JSON);
- subscriptions(id, tenant_id, plan_id, status, period_start, period_end);
- usage_ledger(id, tenant_id, event_id, metric, units, unit_label, job_id,
  happened_at) — job_id #233 加列 (迁移 0014), "" = 未归属 (#233 前存量/非作业事件)
  — metric ∈ {job_verify, job_craft, llm_tokens_in, llm_tokens_out,
  llm_cache_hit_tokens, llm_reasoning_tokens, gate_findings};
- invoices(id, tenant_id, period, line_items JSON, total, currency, status)。

## 2. 计量点 (全部走事件 → 账本投影)

- 验证作业: pipeline 开始/结束事件 (job_verify 1 次/作业, 含 findings 数);
- SpecCraft: agent_jobs 终态事件 (job_craft 1 次/作业 + 工具调用 budget_cost 合计);
- LLM: TokenBudget 每次 usage (input/output/cache_hit/reasoning 四类分别记账,
  与 DeepSeek 网关 usage 字段实测一致);
- 幂等: 账本主键 (event_id) 去重, 事件重放不重复计费 — 复用 outbox_relay 信封。

## 3. 配额与限额

- 预检: 作业创建时对 subscription quotas 校验, 超限 → QUOTA_EXCEEDED (既有码,
  HTTP 402 语义), 软限额 (80%) 通知;
- 超支策略: hard-stop / soft-overage (计费加成) 按 plan 配置, 默认 hard-stop。

## 4. 报表与导出

- GET /billing/usage?from&to (CSV/JSON), GET /billing/invoices (月账单);
- 每作业成本视图 (#233 后端已落): usage_ledger.job_id 归因
  (TokenBudget entry 固化 job_id 后投影落列) + GET /billing/jobs/{job_id}
  (单作业行+按 metric 汇总, billing:read, 跨租户 404); CSV 导出增 job_id 列;
  (job_id → tokens → 单价) 进 job 详情页的 UI 接线仍待 (W31 工作台扩展);
- 账单周期任务 (#234 已落成): 月初生成 invoice — `storage/invoice_cron.py` (独立进程 `python -m storage.invoice_cron`, 但本仓库尚无部署入口起它), 只给**已关闭的上个月**生成草票 (previous_period_key, 跨年无分支), 按 tenant 循环、ensure_invoice 幂等重入、无订阅跳过并计数、单租户失败隔离; SPECPROOF_BILLING_URL 未设时启动即 no-op; 指标 specproof_invoice_cron_* (INVOICE_CRON_METRICS_PORT, 默认 9103; 端口已被别的进程回答时该进程记 "NOT serving (原因)" 并继续开票, 不因此停); 状态机 draft→issued→paid 已在存储层 (transition_invoice), 操作入口与网页签发仍待。

## 5. 测试

- 幂等: 同 event_id 双写 → 账本仅 1 行;
- 配额: 超限预检拒绝 + 软限额通知;
- 金额: invoice 汇总与 usage_ledger 明细对账一致 (金额 = Σ line_items);
- 全 mock, 无真实计费网关; 数字口径与 TokenBudget 实测一致 (含缓存命中 512
  tokens 案例)。
