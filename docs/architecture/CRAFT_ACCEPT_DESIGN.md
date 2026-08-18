# SpecCraft → SpecProof Accept 闭环设计 (工业化阶段 7 / Agent 计划 M5)

状态: 设计定稿 (2026-08-18) · 前置依赖: W33 Schema+工具注册表 ✅ · W34 门禁组合 (在途)
目标: SpecCraft 产出的 ChangeBundle 必须通过 SpecProof 独立验收才可 accept —
让"开发 Agent"与"验收防火墙"形成强制闭环, 任何一方单独放行无效。

## 1. 闭环流程

1. CraftLoop 完成修复 → craft/schemas.py ChangeBundle {files, digests, test_results, plan};
2. 内部门禁 (W34 craft/gates.py GatePipeline): run_test → run_build → run_typecheck
   → security scan → self_verify; 任一 FAIL 即 STOP (不进入 SpecProof, 直接回滚);
3. SpecProof 独立验收: 以任务 spec_text 为需求, base=base_sha, head=当前 HEAD
   调用现有 verify 管线 (agent graph 全节点, 复用 cli verify 的编译/差分/法庭);
4. 判定: VERIFIED → 写 Merge Certificate (Ed25519 签名) + lineage extension
   (contracts → findings → ChangeBundle digests 血缘); BLOCKED → rollback (git reset --hard base)
   + 失败报告; UNVERIFIED 政策按既有配置 (fail-closed 默认);
5. accept 结果写入 agent_jobs.result_json {accept_verdict, certificate_id, gates_report}
   (W30 持久化投影), 前端工作台可见 (W31 在途)。

## 2. 新模块与接线

- craft/accept.py (新建): craft_accept(bundle, spec, repo, base_sha, signer) -> AcceptResult
  {verdict, certificate_path, findings, gates_report, rolled_back};
- signer: 复用现有 Ed25519 签名设施 (evidence/certificate), 私钥从环境/密钥文件读取,
  缺失 → fail-closed (绝不降级为无签名 accept);
- 接线点: craft/loop.py 完成态增加 accept_policy: always | manual | never
  (默认 manual 用于开发, 生产 always; 策略只可收紧);
- CLI: cli/specproof/commands/craft.py 新增 `craft accept --job <id> --base <sha>` 手动触发,
  便于演示与排障;
- 幂等: 同一 (job_id, head_sha, bundle_digest) 重复 accept 返回既有证书 (幂等键)。

## 3. 失败模式与对策 (全部 fail-closed)

| 场景 | 行为 |
|---|---|
| 内部门禁 FAIL | STOP, 不调用 SpecProof, 回滚, 报告分层原因 |
| SpecProof 判定 BLOCKED | 回滚, BLOCKED 报告 + findings 列表 |
| verify 管线不可用 (异常) | 视为 BLOCKED (不可静默放行), 记 error 分类 |
| 签名私钥缺失 | accept 失败 (不允许无签名证书) |
| 预算耗尽 | 中止, 诚实标注 budget_exceeded, 不留半截状态 |
| 工作区脏 (非 agent 文件) | 拒绝 accept (classify_workspace_changes 结果非空 user_changes) |

## 4. 验收证据要求 (真实运行, 不纸面)

- E2E 案例: craft 修复 demo 的 double 函数 (x/2 → x*2, 既有 FIX_SPEC) →
  craft_accept → 证书落盘 → `craft certificate verify` 验签通过;
- 反例案例: 植入回归 (test 失败) → 门禁 STOP 且工作区回滚, 无证书产出;
- 反例案例: 植入密钥泄露 → security 门禁 STOP;
- 性能: 单次 accept 端到端耗时与 token 用量记录 (预算账本口径)。

## 5. 与其余阶段的依赖

- 需 W30 agent_jobs 投影 (result_json 落库) + W31 工作台展示 accept 状态徽标;
- 阶段 5 (KMS/HSM) 上线后 signer 切换为 KMS 签名, 接口不变;
- 阶段 6 账单: accept 次数与 LLM token 计入 usage_ledger。
