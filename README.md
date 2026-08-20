# SpecProof — AI 变更验收防火墙

> 代码是 AI 写的, 谁签字? — 我们把“验收”变成机器可验证的事实。

**SpecProof 产品三条线:**

1. **SpecProof Verify (独立验收)** — 把需求编译成可执行契约, 在 Base/Head 两个隔离沙箱里
   真实运行 (HTTP/MySQL/Redis/RabbitMQ 全栈差分 + 变异测试 + 状态取证), 拦截回归并产出
   **可重放证据**; 全部通过则签发 **Ed25519 签名 Merge Certificate**。
2. **SpecCraft Build (自主开发)** — 同平台开发 Agent: 确定性/LLM 规划 → 人工计划审批 →
   原子编辑 (唯一匹配/备份/审计) → 沙箱执行循环 → 五道门禁自校验 → 交付 →
   `craft accept` 交给 Verify 独立复验, 形成 开发→验收→签发 闭环。
3. **Evidence Private (证据私有)** — 证据链全链路可证伪: Bug Capsule (含回放脚本) 可重放、
   契约版本追加式不可篡改、MinIO sha256 交叉核验 (`docs/architecture/DATA_DICTIONARY.md` §2.3/§3)、
   对象元数据 digest 定位、租户隔离 + 越权审计、每次状态转换落审计行。

---

## 一句演示 (真实拦截, 本地可跑)

```bash
pip install -e ".[dev]"
python -m cli.specproof.main verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt
# → BLOCKER AUTH-01 (@PreAuthorize 被移除, base_pass_head_fail + H2 状态取证) + 可重放 Bug Capsule
```

旗舰案例实测记录见 `CLAUDE.md` (内核加固节): 1 BLOCKER + 1 MAJOR, 判定 BLOCKED。

## 一键体验 (老板动线, 全部本地)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1
# 打开 http://localhost:5173  (脚本幂等: infra → worker/outbox → API → 演示种子 → Vite)
```

验收动线 (7 步, 与 `docs/operations/ACCEPTANCE_CHECKLIST.md` §一 一致):

1. 【演示】任务就绪: 矩阵 / Findings / 证书 / 胶囊可下载。
2. 新建验证: 真实跑 QUEUED→终态 (W43.1 实测 BLOCKED)。
3. Agent 流: 新建任务 → 计划审阅(批准) → 实时工具流 (SSE) → 五道门禁 → accept 判定 (确定性档, 无 LLM 无 key)。
4. 视觉: Aurora 暗/亮双主题 + ⌘K 命令面板 + /ui-kit 活样式指南。
5. 权限: 登录 → 租户切换 → viewer/admin 差异 (计费页 viewer→TENANT_FORBIDDEN)。
6. 计费: /#/billing 套餐/订阅/用量/发票。
7. IDE: `ide/vscode` 扩展 (任务侧栏/计划树/审批/虚拟 diff)。

60 分钟完整体验: `docs/operations/EXPERIENCE_GUIDE.md` · 本地运维: `docs/operations/LOCAL_EXPERIENCE.md`。

## 能力总表 (全部真实运行; 单一事实源: `docs/operations/ACCEPTANCE_CHECKLIST.md`)

| 能力 | 实测数字 | 出处 |
|---|---|---|
| 100 金案例 (正 63/负 37) | 检出 63/63, 误报 0, **Recall/Precision/F1 = 100.0%** (五块全部修复后重跑: c1/c2/c3/c4/rem3 实录); 历史首跑 95.2% 对照保留在总表 | `docs/eval/eval-100-segments.md` |
| SpecCraft 90 任务评测集 | 代码完成率 **98.0%** (49/50); 陷阱拦截/对抗/断点恢复/危险动作审批 **100%/100%/100%/100%**, 审批违规 0 | `docs/eval/agent-task-suite.md` |
| SpecCraft 微基准 (10 任务) | 完成率 **90.0%**, 平均迭代 **1.1**, 预算内 100%, 陷阱自校验拦截率 **100%** | `docs/eval/craft-microbench.md` |
| 检索 (30 查询黄金集) | BM25+RRF recall@10 **87.2%** / MRR **0.760** (vs BM25 72.2%/0.561, +15.0pp); symbol-index 75.6% @ 2.3ms | `docs/eval/retrieval-bench.md` |
| 变异测试 | 杀死率 **83.3%** (5/6, 存活体为规范外行为 — 数字不凑 100%) | `docs/eval/mutation-results.md` |
| 基线对比 (Go/No-Go #14) | 确定性 diff-reader 基线: Recall **+41.7pp**; LLM 看 Diff 基线: Recall **+100.0pp** (SpecProof 100% vs 基线 0%) | `docs/eval/baseline-report.md` / `docs/eval/llm-baseline-live.md` |
| Go/No-Go 15 门槛 | **PASS 11/15 · PARTIAL 1/15 · PENDING 3/15** (未实测一律 PENDING, 不编造; #4 回放 100% / #5 无证据评论 0 / #6 p95 161s / #9+#11 真实演练 / #14 LLM 基线 +100pp; PARTIAL #3 归因 88.9%) | `docs/eval/go-nogo.md` |
| 质量门禁 | 单元 **2069 passed + 1 skipped** 全绿; ruff / mypy strict / bandit Medium+=0; **密钥泄漏 0** | `docs/operations/ACCEPTANCE_CHECKLIST.md` §二 |
| 前端 | vitest 90+, Playwright e2e 9/9, 设计系统 21 组件 | `docs/operations/ACCEPTANCE_CHECKLIST.md` §二 |

## 架构图 (文本)

```text
CLI · Web SPA · MCP · GitHub App · VS Code 扩展     ← 五种入口, 同一 API 语义
                │
        FastAPI (api/)  — 鉴权/限流/租户作用域 (fail-closed)
                │ POST /jobs (严格字段白名单)  POST /webhooks/github (HMAC+去重)
                ▼
   MySQL verification_jobs + outbox (同一事务, at-least-once)
                │ outbox-relay (SELECT ... FOR UPDATE SKIP LOCKED, publisher confirm)
                ▼
   RabbitMQ q.p1.verify.job (+.retry 逐消息 TTL +.dlq)  ← Redis SETNX 幂等
                │
                ▼
   Worker (agent/worker.py): Redis 租约 → LangGraph 12 节点
   (Mongo agent_checkpoints 断点续跑) → DooD 沙箱 (docker:27-dind,
   非 root/断网/限额) Base/Head 差分执行 + 状态取证 + 变异
                │
       终态 CAS 写回 MySQL (VERIFIED/BLOCKED/FAILED) + audit_logs
       证据: MinIO 三桶 + Mongo evidence_packs (sha256 交叉核验)
       检索: Elasticsearch specproof-code-phase0 (BM25+向量, 可重建投影)
       进度: Redis Stream → SSE → Web 实时; 指标: OTel → Prometheus → Grafana
```

存储全字段字典: `docs/architecture/DATA_DICTIONARY.md` · 状态机: `docs/architecture/STATE_MACHINES.md` ·
依赖锁定: `docs/architecture/DEPENDENCY_LOCK.md` · 总架构: `docs/architecture/ARCHITECTURE.md`。

## 目录地图

| 目录 | 职责 |
|---|---|
| `cli/` | Click CLI 入口 (verify / replay / eval / baseline / craft) |
| `agent/` | 12 节点 LangGraph 管线、worker、检查器/契约族、错误分类 |
| `api/` | FastAPI: jobs / webhooks / web 只读视图 / 多租户身份 / agent console |
| `storage/` | MySQL / Mongo / ES / Redis / MinIO / RabbitMQ / outbox / 计费 / 元数据适配器 |
| `craft/` | SpecCraft: spec/planner/editor/executor/loop/verify/gates/accept |
| `evidence/` | 矩阵构建、HTML 报告、Merge Certificate (Ed25519) |
| `providers/` | DeepSeek/OpenAI 兼容 Provider + 能力探测 + 降级 |
| `retrieval/` | RAG: BM25 + 符号图谱 + RRF + 重排 (三层诚实降级) |
| `sandbox/` | 执行隔离 (DooD, 非 root/断网/资源限额) |
| `integrations/` | GitHub App Check Run / Inline Findings |
| `observability/` | 结构化日志 / metrics / OTel 追踪 |
| `apps/web/` | React 18 + Vite SPA (9 页 + Aurora 主题 + /ui-kit) |
| `ide/vscode/` | Agent Console 扩展 (任务/计划树/审批/diff) |
| `demo/spring-backend/` | Spring Boot 3.4 / JDK 21 演示仓库 (base / head-v1 tags) |
| `infra/` | MySQL 迁移 0001-0008、compose、Prometheus/OTel/告警 |
| `docs/` | 架构/设计/评测/运维文档 (本仓库唯一事实区之一) |
| `tests/` | unit / security / fault / integration / e2e |
| `golden-cases/` | 20 金案例评测集 (holdout 3 例锁定) |
| `bench/` | SpecCraft 90 任务评测集 fixtures |
| `scripts/` | 一键启动 / 评测 / 演练 / 构建脚本 |

## 门禁命令 (提交前必跑)

```bash
# Python: lint + 类型 + 安全 + 测试
python -m ruff check .          # 全绿
python -m mypy .                # strict (pyproject.toml)
python -m bandit -r agent api storage craft cli  # Medium+ = 0
python -m pytest tests/ -v      # 单元 2069+ 全绿; integration 需真实基础设施时显式 skip, 不伪造

# Web
cd apps/web && npm run typecheck && npm run test && npm run build
# e2e: npm run test:e2e (Playwright, 9/9)

# Compose 配置校验
docker compose -f compose.phase0.yml -f compose.production.yml -f compose.observability.yml config
```

100 案例全量评测为 slow_eval 标记 (multi-hour), 见 `docs/eval/p6-100-case-eval.md`。

## 安全声明

- **密钥纪律**: 密钥只经环境变量注入; `tests/security/` canary 自检 + 全库扫描门禁, 实测泄漏 0; `.env.example` 仅占位符。
- **沙箱**: 执行不可信 PR 代码一律进 DooD 沙箱 — 非 root、断网、资源限额、超时截断; worker 不挂载宿主机 docker socket (`compose.production.yml` §12)。
- **注入免疫**: 仓库文本一律视为数据段, 不得覆盖系统级安全规则; 实测注入 0 影响 (`docs/eval/eval-100-segments.md` 负样本含 5 例注入案例)。
- **推理不落盘**: reasoning_content 只进内存 journal, 产物零推理泄漏 (ADR-017, `docs/adr/ADR-017.md`)。
- **证据可证伪**: Ed25519 in-toto 风格证书 + sha256 对象摘要交叉核验 + 契约 (id, version) 追加式不可就地改。
- **API fail-closed**: 所有业务端点要求 X-API-Key + 限流; webhook 走 HMAC (恒定时间比较) + delivery 去重; 越权读取 404 + 审计。

## 诚实边界 (验收当天如实汇报, 不掩饰)

1. **100 案例已冲 100.0%**: 63/63 误报 0 (五块修复后重跑实录, `docs/eval/eval-100-segments.md`; 历史首跑 95.2% 对照保留)。
2. **Go/No-Go 15 门槛 11/15 PASS** (#4 回放 25/25=100% / #5 无证据 BLOCKER 不变式测试 19 例 / #6 FAST p95 161.1s / #9+#11 真实故障演练 / #14 LLM 基线 +100pp); PARTIAL 1 (#3 归因 88.9%, att-08 both-fail 修复在途), PENDING 3 (#12 试点 / #13 用户 / #15 成本, 仓库外依赖); 任一门槛未达 PASS 前不宣称商业优势 9.0。
3. **诚实未达标项**: Aider polyglot 离线样本 1/3=33.3% (harness 全绿, 跨语言编辑器未支持诚实标注); SWE-bench-Lite 真实跑十二轮 (v1-v12) 每轮消掉一类失败 (信封→venv→测试文件误改→编辑锚点→判据退化→依赖漂移→venv 复用→后缀路径→测试收集→重复提案→瞬时超时), resolved 率始终诚实 0% — harness 层障碍已清完, 剩余模型能力层 (v12 实测: 网关 /v1/models 仅 deepseek-v4-flash/v4-pro 两档无更强档, 最强档重测两实例仍 [LLM_PROPOSAL_REPEATED] STUCK; v13 方向 = 官方 Docker 口径/网关外更强模型); Go/No-Go 整体评级见 `docs/eval/go-nogo.md`。
4. **依赖基础设施未实测**: Linux 非 root 沙箱、KMS/HSM、跨语言 Gradle/Node/Go 适配器 — 本地不可验。
5. **依赖锁定缺口**: Python 无 lock/freeze 快照, 完整锁定审计需干净 venv (`docs/architecture/DEPENDENCY_LOCK.md` §0/§1.3)。
6. **状态机差异**: Verify/Craft 当前实现与演进计划 §4.3/§4.4 冻结定义的逐项差异已诚实列明 (`docs/architecture/STATE_MACHINES.md`)。
7. **LLM 档**依赖外部可用端点与 Key; 无 Key 时诚实降级为确定性档并明确标注, 绝不伪造 LLM 结果。
8. ~~计费路由与前端收尾 (W101)~~ 已落地 (billing 路由/wizard/权限页/progress 形状, 19 文件 90 测试+build 全绿)。

## 文档导航

- 验收: `docs/operations/ACCEPTANCE_CHECKLIST.md` (老板总表) · `docs/operations/EXPERIENCE_GUIDE.md` (60 分钟体验)
- 架构: `docs/architecture/ARCHITECTURE.md` · `docs/architecture/STACK_INVENTORY.md` · `docs/architecture/domain-model.md`
- 数据/状态/依赖: `docs/architecture/DATA_DICTIONARY.md` · `docs/architecture/STATE_MACHINES.md` · `docs/architecture/DEPENDENCY_LOCK.md`
- 运维: `docs/operations/RUNBOOK.md` · `docs/operations/DATA_LIFECYCLE.md` · `docs/operations/OBSERVABILITY.md`
- 评测: `docs/eval/` (全部真实运行输出)
- 演进: `docs/持续演进终极目标与链路计划.md` · `docs/design/SPECCRAFT_PLAN.md`
