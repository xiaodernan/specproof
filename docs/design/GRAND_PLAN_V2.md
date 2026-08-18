# SpecProof 2.0 宏伟项目计划书 (GRAND PLAN V2)

版本: 2.0 · 2026-08-18 · 状态: 演进中 (每轮审计→实现→全绿验证, 按卷追加)
定位: AI 变更验收防火墙 (SpecProof) + 自主开发 Agent (SpecCraft) 的一体化平台,
以行业最先进水平 (Claude Code / Codex / Devin / Cursor) 为对标, 在"独立验证"
细分做到世界级。

## 卷 I. 总纲与目标

### 1.1 终极目标 (三句话)
1. SpecCraft 是能独立完成中小型真实仓库任务的超强开发 Agent (规划/编辑/执行/
   自校验/交付, 全部可审计、可续跑、可预算)。
2. SpecProof 是任何 AI 产物 (不管哪个 Agent 写的) 的独立验收方: 需求→契约→
   差分/变异/状态证据→签名证书, 实现"写代码的不能给自己签字"的行业标准。
3. 平台层把两者连成闭环 (craft → verify → certificate → fix), 并输出完整
   前端/后端/中间件与评测基准, 达到可商业部署、可面试演示、可论文引用的水平。

### 1.2 关键指标目标 (量化, 可机器判定)
- 验证侧: 200 金案例; Recall/Precision/F1 ≥ 99%; 误报 = 0; 15 项 Go/No-Go 全绿;
  FAST 小 PR p95 ≤ 8 分钟 (实测计时基准)。
- 开发侧 (SpecCraft): 10 任务微基准完成率 ≥ 90% (确定性+LLM 混合); 自校验
  拦截率 = 100% (陷阱变体必被拦); 平均迭代 ≤ 6; 预算内完成率 ≥ 80%;
  SWE-bench-lite 适配器打通 (可选集, 私有部署优先)。
- 平台: 单测 1000+; 安全测试 30+; 故障注入 30; 集成 150; MCP 一致性 100%;
  前端 60+ 测试; 全门禁 (ruff/mypy/bandit/pytest/compose) 常绿。
- 可靠性: 评测 20 连跑 0 误报漂移; worker kill ×10 恢复率 100%; 网关故障注入
  场景 100% 不丢 Job; 密钥泄漏测试 100% 通过。

### 1.3 演进节奏与方法论
- 每轮: 审计 (门禁+评测+安全+基准) → 实现 (一个可验证增量) → 全绿验证 →
  里程碑提交 (git + 镜像 + bundle + GitHub)。
- 指标单调: 任何一轮不得回退既有指标 (回归红线); 新能力先写评测再实现。
- 季度: 重跑全部基准, 重对标公开榜单 (SWE-bench Verified / Aider Polyglot /
  LiveCodeBench / terminal-bench), 更新差距矩阵。
- 诚实原则: 一切数字来自真实运行; 无密钥落盘; 无 TODO/pass 占位; 降级显式。

## 卷 II. 技术栈演进决策 (含 LangChain 评估)

### 2.1 LangChain / LangGraph 评估结论
- LangChain (chains 抽象): 不采用 — 链式封装黑盒化严重, 调试/审计困难,
  与我们的证据链要求冲突; 我们已有自己的 10 态状态机 + LangGraph 节点图 +
  确定性回退体系。
- LangGraph: 保留 (仅用于验证管线图编排), 原因: 状态 schema 明确、可检查点
  (MongoDB saver)、可中断/恢复, 与我们的 checkpoint 审计要求吻合; 12-14 节点
  管线实测稳定。若未来发现其复杂度过高, 备选: 自研 DAG 执行器 (状态机已有,
  迁移成本可控) — 决策记录在 ADR, 不做无谓迁移。
- 结论写入 ADR-018 (新增)。

### 2.2 LLM 工程层 (大模型工程) 技术栈
现状: 自研 providers/ (11 维能力探测 + Envelope 降级 + thinking 分层 +
KV 缓存友好模板 + TokenBudget) — 已在真实 DeepSeek V4 Pro 网关实测 (8/11,
live-fire 修复)。
演进:
1. 结构化输出升级: 引入 Pydantic 输出模型 (LLMResponse 已是 Pydantic; 把
   planner/diagnose 的 JSON 解析升级为 Pydantic 校验器, 替代手写 schema 校验)
   → 减少解析 bug, 类型安全直达 mypy。
2. 评估 LiteLLM (只评估, 不强推): 多网关路由/计费聚合有价值, 但我们自研
   探测+降级已覆盖核心需求; 若采用, 仅作为 provider 适配层的一个可选后端,
   不替换我们的能力探测模型 (ADR-019)。
3. 提示词工程: 模板库升级 — 增加 few-shot 示例注入 (按任务类型), 稳定前缀
   不变 (缓存友好); 增加"思维预算提示" (要求模型先给假设再给结论, 对齐 V4 Pro
   的推理特性)。
4. 批量与流式: chat_stream 已实现; 增加并发调用池 (asyncio.Semaphore,
   默认并发 2, 与预算/限流联动); 评测/基线批量跑用并发+退避。
5. 结构化输出兜底: 增加 Pydantic 校验失败 → 单次修复重试 (把校验错误回喂模型)
   → 再失败回退规则模板 (三层: 校验/修复/回退)。
6. 缓存: 语义缓存 (可选, 键=spec_digest+diff_digest, 存 MongoDB, TTL) —
   只在 RELEASE 档重放场景启用, 避免污染证据链 (证据必须是新跑的结果;
   缓存只用于计划/诊断等非证据链路, ADR-020)。

### 2.3 RAG 技术栈 (符号图谱 + 混合检索 2.0)
现状: ES BM25 + 方法级符号块 + repo_graph 邻域扩展 (确定性, 已端到端);
dense_vector 预留未启用。
演进 (RAG 2.0, 本轮开工):
1. 向量化: 嵌入层可选 — OpenAI 兼容 /embeddings (BYOK, 复用 provider 栈) 或
   本地模型 (sentence-transformers, 可选依赖); 无嵌入时诚实降级 BM25+图谱
   (现状)。索引: ES dense_vector (已预留) + HNSW。
2. 混合检索: BM25 + 向量 → RRF 融合 → 图谱邻域扩展 → (可选) 重排。
3. 重排: 首选交叉编码器 (bge-reranker 本地小模型, 可选依赖); 无本地模型时
   用 LLM 重排 (一次性列表比较, 预算内); 无 LLM 时保序 (诚实标注 rerank=off)。
4. 图谱升级: 现有类/方法/调用图 → 增加 文档图 (README/ADR/issue 与符号的
   链接) + 契约图 (contract 与符号的绑定), 检索时可跨证据类型召回。
5. 评估: 检索质量评测集 (30 个查询 → 黄金上下文文件集), 指标 recall@10 /
   MRR, 每轮 RAG 改动必跑 (检索回归红线)。
## 卷 III. Agent 引擎演进 (SpecCraft 2.0)

### 3.1 现有能力 (M1 已交付, M2 在途)
规划 (确定性模板 + M2 LLM) / 编辑器 (原子写/唯一匹配/备份/审计) / 执行器
(命令白名单 + 沙箱) / 收敛循环 (预算/断点/STUCK 判定) / 自校验 (M3) /
交付 (M6) / 验收闭环 (M7)。

### 3.2 演进路线 (按优先级)
M2  (在途) LLM 规划与诊断 — 真实 V4 Pro, thinking 分层, 预算账本, 推理不进证据。
M3  自校验 — 接入 SpecProof checker 家族 + 安全扫描作为 craft 的硬门。
M4  持久化 — MySQL job 行 (job_kind=craft) + 审计表 + kill 后 resume。
M5  子代理并行 — 计划步骤 DAG: 无依赖步骤并行执行 (asyncio 任务池),
     共享编辑器用文件锁/分文件所有权; 每子任务独立预算, 父级汇总 (对标
     Claude Code subagents 的 fan-out)。
M6  交付 — 分支/PR/diff 报告; GitHub App 触发 (复用 integrations/)。
M7  闭环 — craft accept → verify → certificate → fix 循环 (最多 3 轮)。
M8  仓库策略摄取 — 读仓库 AGENTS.md/CLAUDE.md (对标记忆文件), 注入规划层
     系统上下文 (数据段, 不可覆盖系统指令), 缓存按文件 hash。
M9  工具生态 — MCP 客户端 (craft 可消费外部 MCP 工具, 白名单+预算);
     内置工具扩展 (grep/glob/tree/test/shell, 对齐 Claude Code 工具面)。
M10 上下文压缩 — 上下文超预算时自动生成中间摘要 (LLM summarize 或确定性
     截断), checkpoint 记录压缩点, resume 可重建。
M11 技能包系统 — 把验证技能 (auth/txn/mq/redis 场景) 打包为可插拔技能
     (对标 skill packs), craft 按任务类型加载。
M12 提示词自动优化 — DSPy 风格签名 + 小样本优化循环 (用微基准做信号),
     优化结果人工审阅后入库 (绝不自动上线未审提示词)。

### 3.3 Agent 循环状态机 (复用 10 态)
QUEUED → PLANNING → PLAN_READY(人工可审) → EXECUTING → SELF_VERIFYING →
DONE | FAILED | STUCK | CANCELLED | EXPIRED; 每个转换写审计行;
人工中断 (hup) 优雅落 checkpoint。

### 3.4 人机协同
- 计划审批 (PLAN_READY): 终端展示计划 + 风险标注, 用户可改/拒 (对标 plan mode)。
- 危险操作确认: 白名单外命令 / 超出 diff 规模 / 触碰 forbidden_changes →
  要求显式确认或直接拒绝。
- 差异审阅: 交付前展示 diff 摘要 + 自校验结论, 用户可逐文件接受/拒绝。

## 卷 IV. RAG 2.0 详细设计 (已实现 + 实测, 车道 L, 2026-08-18)

### 4.1 索引层
- chunk: 方法级符号块 (现状, AST-free 正则切分) 保持; 增加文档块
  (README/ADR/issue 按标题切分)。
- 向量: dense_vector dims 随嵌入模型 (默认 1536, 可配); HNSW m=16。
- 字段: content / symbol / kind(code|doc|contract) / repo / commit / path /
  embedding (可选); 仓库隔离强制 term 过滤 (现状保留)。

### 4.2 检索管线 (RRF 融合)
query → BM25 (content+symbol) → 向量 top-k (如有) → RRF 融合 → repo_graph
邻域扩展 (2 跳) → 重排 (cross-encoder 或 LLM, 可选) → 预算截断 → 注入。

### 4.3 降级矩阵 (诚实标注在结果里)
| 场景 | 行为 |
|---|---|
| 嵌入未配置 | BM25 + 图谱 (现状行为, rerank 保序) |
| ES 不可用 | retrieval_note=unavailable, 契约编译退回仅需求文本 |
| 重排模型缺失 | rerank=off 保序 |
| 向量字段无数据 | 自动回退 BM25 (不报错) |

### 4.4 检索质量评测 (红线)
30 查询黄金集 (函数名/需求句/契约 id → 期望文件集), 指标 recall@10 / MRR;
每次 RAG 改动必跑; 当前 BM25+图谱基线先固化数字, 后续向量/RRF/重排逐项
增量对比 (消融实验)。

### 4.5 与 LLM 上下文工程的联动
检索结果按"稳定前缀 + 任务模板 + 变量数据"组装 (缓存友好); 检索结果本身
进入变量段, 不进稳定前缀。

### 4.6 实现与实测状态 (L 车道交付, 2026-08-18)
已实现文件: retrieval/embeddings.py (EmbeddingClient: LLM_EMBEDDING_* →
LLM_* 回退, 批量 ≤64, 429 退避复用 providers 语义, 不可用返回 None+原因,
绝不伪造向量); retrieval/rerank.py (交叉编码器 → LLM 列表重排 → 保序,
三档诚实标注); retrieval/hybrid.py (BM25+向量 RRF k=60 → 图谱 2 跳 →
重排 → 预算截断, 元数据 bm25_hits/vector_hits/rerank_mode/embedding_used
随结果返回); storage/elasticsearch.py (dense_vector 启用: dims 默认 1536
可配 ES_VECTOR_DIMS, HNSW m=16, 新增 index_with_embeddings / vector_search,
既有 BM25 路径不变); agent/nodes/retrieve_repository_context.py (有嵌入走
hybrid, 无嵌入走现状 BM25+图谱, 模式日志+retrieval_note 标注);
tests/unit/test_retrieval_hybrid.py (全 mock)。

实测降级矩阵 (mock 验证 + 真实 ES 通道冒烟 — 本机无可用嵌入端点, 用确定性
伪向量实测了 dense_vector/HNSW/knn/RRF 真实 ES 链路: 索引 3 块 embedded=3,
mapping dense_vector dims=1536 index=true hnsw m=16, hybrid 模式
bm25_hits=1/vector_hits=3, 融合首位 bm25+vector rrf=2/60; 真实嵌入端点
冒烟待接入):

| 场景 | 实测行为 | 标注 |
|---|---|---|
| 嵌入未配置 | BM25+图谱现状路径, rerank 保序 | mode=bm25, rerank=off |
| 嵌入端点不可用 | 索引/检索自动回退 BM25, 不报错 | embedding_error=原因 |
| 向量字段无数据 | vector_hits=0, 自动回退 BM25 | mode=bm25 |
| 重排模型缺失 | 原序返回 | rerank_mode=off + reason |
| ES 不可用 | retrieval_note=unavailable, 契约编译退回仅需求文本 | 现状不变 |

偏差说明: (1) 4.4 检索评测 30 查询红线为后续车道任务, 本轮未含评测集;
(2) 交叉编码器依赖 sentence-transformers 为可选依赖 (未进 pyproject,
缺失时诚实降级); (3) LLM 重排的 token 预算以输入截断实现
(ModelProvider.chat 无 max_tokens 通道); (4) hybrid 路径按 4.2 用 2 跳
图谱扩展, 现状 BM25 路径保持 1 跳不动 (向后兼容)。
## 卷 V. LLM 工具调用与工程深化 (大模型工程)

### 5.1 工具调用分层 (基于真实网关 8/11 探测)
- 有 tool_calls: 原生 function calling (并行工具, 严格 schema)。
- 无 tool_calls: JSON Action Envelope (单对象 {action, params}) — 已实测。
- 思考分层: 规划/Judge/诊断开 thinking; 工具循环关 thinking (实测该网关
  thinking+工具不共存, 分层是唯一正确解)。
- 工具结果回喂: 每条工具输出截断 (4000) + 结构化 (status/output/error),
  避免模型被注入内容操纵 (工具输出同样进数据段)。

### 5.2 结构化输出可靠性三层
1. response_format json_object + 提示词含 JSON (实测网关要求);
2. Pydantic 校验失败 → 单次"修复重试" (校验错误回喂, 预算内);
3. 仍失败 → 规则模板回退 (确定性), 结果标注 fallback_reason。
(三层全部进 checkpoint 审计, 不静默。)

### 5.3 预算与经济性 (真实 usage 字段实测)
- 账本字段: prompt/completion/reasoning/cache_hit/cache_miss (已实测解析);
- 权重可配 (默认 cache_hit 0.1x); 任务级/平台级双层预算;
- 成本报告进 dashboard (cost available=true 之后);
- 目标: 同任务二跑 (缓存热) 成本下降 ≥ 40% (KV 前缀命中验证)。

### 5.4 评测与回归 (LLM 层)
- 能力探测 11 维 (新增 reasoning_content 位) — 每次换网关/模型必跑;
- 工具调用正确率小基准: 20 个合成任务 (envelope 解析 / tool_call 解析 /
  坏 JSON / 空 content), 每轮必跑 (已部分覆盖, 扩充至 20);
- 提示词模板回归: 稳定前缀逐字节自检 (已有) + 语义回归 (微基准)。

## 卷 VI. 验证引擎深化 (SpecProof 2.0)

### 6.1 契约体系
- 现有: AUTH/UNIQUE/EVENT_ONCE/TRANSACTION/ATOMICITY/CONCURRENCY/CACHE/
  MIGRATION/OPENAPI/BACKWARD_COMPATIBLE/NPLUSONE/TEST_STRENGTH/ORDER_EVENT…
  (11+ 族, 100 案例实测)。
- 演进: 序列化状态机契约 (STATE-01: 订单生命周期合法转移), 幂等契约
  (IDEMPOTENT-01 深化: requestId 重放矩阵), 授权矩阵契约 (RBAC-01:
  角色×端点矩阵), 数据保留契约 (PII-01: 脱敏/最小化)。
- 契约编译器: 需求→候选契约的 LLM 编译 (真实端点) + 人工审批 + 版本化
  (已有骨架, 深化 few-shot 与反例生成)。

### 6.2 差分实验室深化
- 现有: HTTP/MySQL/Redis/RabbitMQ 快照 + 语义归因 + H2 三表取证。
- 演进: 序列请求重放 (stateful sequence, 从 spec 生成调用序列), 时间旅行
  (Redis TTL/键过期模拟), 事件顺序断言 (顺序/去重/死信), 性能计数器
  (查询数/外部调用数) 阈值契约 (已部分), 内存/阻塞调用探测 (可选)。

### 6.3 变异测试深化
- 现有: 4 算子 + 战役 + KILLED/SURVIVED + 等价判断。
- 演进: 算子扩至 8 (边界/空值/权限/事务/重试/ack/缓存失效/返回值),
  变异体优先级 (changed-files 影响面, 已有思路 → 落实), 存活体分析报告
  (等价判定 + 测试弱点建议)。

### 6.4 反注入与对抗 (安全红线)
- 现有: 注入负样本 5 (README/注释/spec/schema/pom), 实测裸模型被注入影响、
  我们 0 影响。
- 演进: 注入矩阵扩至 15 (分支名/commit message/issue 标题/图片 alt/
  JSON 字段值/环境变量名), 每类正反两向; 全部进 200 案例。

### 6.5 200 案例路线 (从 100 → 200)
+40 序列状态机/幂等/RBAC/PII 契约案例 (正负各半);
+30 跨契约组合案例 (一个 PR 同时破坏 auth+tx+event);
+20 注入对抗案例; +10 性能/N+1 深化。holdout 纪律保持 (锁定子集永不作调优)。
## 卷 VII. 平台工程深化 (后端/中间件/多租户)

### 7.1 FastAPI 运行时
- 现有: 鉴权 (fail-closed) / 限流 / CORS / SSE / metrics / OTel / 结构化日志
  + 9 个 /api/v1 只读端点 (H 交付)。
- 演进: Request-ID 传播 (J 在途), payload 上限 10MB (J 在途), 响应压缩
  (gzip, 大报告), 分页游标统一, OpenAPI schema 完善, 健康端点分级
  (liveness/readiness 分离)。

### 7.2 Spring Boot Control Plane
- 现有: 6 控制器 (tenant/user/job/webhook/health) + 5 实体 + outbox + 审计
  + 版本化迁移 0001-0004。
- 演进: RBAC (角色×端点矩阵, 与验证侧 RBAC-01 契约联动), 租户级限流,
  组织/成员管理, GitHub 安装管理页, 审计查询 API, 计费事件 (job 完成时
  写 usage 事件), 定时任务 (workspace 清理/陈旧 job 回收)。

### 7.3 存储层
- MySQL: 事实源 (10 态/outbox/审计) — 演进: 查询索引优化, 归档策略,
  backup/restore 演练脚本 (RUNBOOK 已有章节, 补自动化)。
- MongoDB: 工件 (checkpoint/evidence) — 演进: TTL 索引 (工件过期), 分片预留。
- ES: 检索 (RAG 2.0 车道)。
- Redis: 锁/租约/预算/进度 — 演进: 分布式限流 (token bucket, 租户级),
  进度流压缩。
- RabbitMQ: 任务流水线 — 演进: 优先级队列 (RELEASE 档优先), 每队列消费者
  数可配, 死信自动重投上限 + 告警。
- MinIO: 工件/证书/胶囊 — 演进: 生命周期策略, 服务端加密, 预签名 URL
  (前端下载免鉴权)。

### 7.4 中间件全链路 (盘点 + 补缺, J 在途)
Request-ID → 鉴权 → 限流 → CORS → payload 限制 → 路由 → 日志/指标/追踪;
CP 侧: webhook 验签 → 幂等 (delivery_id) → outbox → 审计。
文档 docs/operations/MIDDLEWARE.md 为唯一盘点源。

## 卷 VIII. 前端与体验 (React SPA 2.0)

### 8.1 现有 (H 交付)
9 页: 登录 / Dashboard / Jobs / JobDetail (SSE) / Matrix / Finding /
Contracts / Eval / Health; 深色工业风, 零外部运行时依赖, hash 路由。

### 8.2 演进
- 实时性: SSE 复用单连接 (EventSource 多 tab 共享), 心跳+重连退避;
- Job 详情: 阶段时间线可视化 (SVG 甘特), 工具调用日志流, 推理过程
  (reasoning) 只读视图 (内存态, 刷新即失, 符合 ADR-017);
- 契约中心: 契约 diff 视图 (版本对比), 批量审批;
- 评测页: 基线对比 (SpecProof vs LLM 双口径) 图表;
- 设置: 模型配置/预算/网关探测结果 (11 维) 可视化;
- 国际化: 中英切换 (已有双语文案, 补全);
- 可访问性: 键盘导航/对比度 (WCAG AA 目标);
- 测试: SPA 路由与降级视图断言 (K 车道扩展目标 60+)。

## 卷 IX. 可观测与可靠性 (SRE 深度)

### 9.1 现状
Prometheus + Grafana (15 面板 + 7 SLO 告警) + OTel + 结构化日志 + worker/relay
指标端口; outbox 积压告警已接线。

### 9.2 演进
- 指标补全: 阶段级耗时 (p50/p95), LLM token/成本, 检索延迟, 缓存命中率,
  沙箱失败率, 证书签发率, capsule 重放成功率 (§8.10 清单逐项接线);
- 追踪: webhook→outbox→MQ→worker→LLM→tools 全链路 span (OTel 已插桩,
  补 RabbitMQ 传播上下文);
- 告警: 分级 (P1 立即/P2 15min), 静默规则, 值班手册 (RUNBOOK 联动);
- 混沌: 故障注入脚本集 (kill worker / 断 MQ / 429 网关 / 磁盘满), 月度演练;
- SLO 仪表: 15 门槛中可自动化的项全部进 Grafana (dashboard 已部分, 补全)。
## 卷 X. 安全与合规 (企业级)

### 10.1 密钥与凭据
- 纪律 (已执行): 密钥仅环境变量/Secret; 0 密钥门禁 (安全扫描器) 已实测拦下
  4 次假密钥事故; 脱敏/redaction; canary 自检。
- 演进: 密钥轮换 SOP (§0: 聊天出现即轮换), 扫描器扩展 (PAT/私有 key/内部
  URL), CI 密钥检查 job (已部分), 依赖漏洞扫描 (pip-audit, 新 CI job)。

### 10.2 沙箱与威胁模型 (§12 深化)
- 现有: 非 root / 断网 / ro 工作区 / pids 限额 / 资源限额 / 不挂 socket。
- 演进: gVisor 运行时评估 (隔离强化, 兼容性验证), 网络 egress 代理白名单
  (需要联网的场景: 依赖安装代理), 时间预算 (CPU time), seccomp 配置,
  fork PR 更严格策略 (策略编码而非文档)。

### 10.3 数据与隐私 (ADR-017 扩展)
- 私有推理不保存: reasoning 只进内存 (已实现); 审计日志不含仓库内容全文
  (哈希引用); 数据保留策略可配 (保存期限), 仓库数据删除接口 (GDPR 风格);
  请求脱敏最小上下文 (已有 redaction, 扩展 schema 级)。

### 10.4 供应链
- 依赖锁定 (requirements.lock / uv lock 评估), 镜像签名 (cosign 评估),
  SBOM 生成 (可选), 构建可复现 (Docker build 缓存策略)。

## 卷 XI. 评测与基准体系 (世界级目标)

### 11.1 分层评测矩阵
| 层 | 基准 | 红线 |
|---|---|---|
| 单元 | 1000+ 测试 | 全绿, 新增必测 |
| 安全 | 30+ (注入/越权/密钥) | 0 泄漏/0 注入影响 |
| 故障 | 30 (MQ/网关/磁盘/时钟/租约) | 恢复语义正确 |
| 集成 | 150 (真实基础设施 + compose 组合) | 全绿 |
| 金案例 | 200 (验证侧) | Recall/Precision ≥ 99%, FP=0 |
| 基线 | diff-reader + LLM 双口径 (100 案例已实测) | +25pp 门槛, 每季度重测 |
| 微基准 | 10 任务 (craft) + 陷阱变体 | 完成率 ≥ 90%, 拦截率 100% |
| MCP | 协议一致性矩阵 | 100% |
| 前端 | 60+ | 全绿 |

### 11.2 外部基准对齐 (可选, 私有优先)
- SWE-bench-lite 适配器 (M5+): 拉取公开任务集 (或私有镜像), craft 跑任务,
  机器判定 (test patch), 出 pass@1 — 与业界同口径比较;
- 验证侧: 发布"SpecProof Golden Bench" (100/200 案例) 为开源基准, 邀请
  其他验收工具跑分 (这是细分领域标准制定的机会)。

### 11.3 反作弊纪律 (评测可信)
- holdout 锁定 (永不调优), 盲评 (评测脚本与开发分离), 结果可复现
  (seed/版本/命令全记录), 报告含环境指纹 (git SHA/模型/日期)。

## 卷 XII. 里程碑总表 (M10-M20, 每项: 目标/验收命令/交付物)

M10 RAG 2.0 (L 车道): 向量+RRF+重排可选链路, 降级矩阵, 检索评测 30 查询红线。
M11 安全深化: 注入矩阵 15 类, 依赖扫描 CI, 密钥轮换 SOP。
M12 契约深化: STATE/IDEMPOTENT/RBAC/PII 四族 + 案例 +40。
M13 评测体系: 200 案例全量 + 微基准 10 任务 + SWE-bench-lite 适配器骨架。
M14 平台深化: RBAC/租户限流/计费事件/审计查询 API。
M15 前端 2.0: 实时/甘特/契约 diff/推理只读视图/设置页。
M16 SRE 深度: 全链路 span + 混沌演练 + 告警分级 + SLO 全接线。
M17 Agent 并行与技能: 子代理并行 + 技能包 + 仓库策略摄取 + MCP 客户端。
M18 经济性: KV 缓存命中验证 (≥40% 成本降), 语义缓存 (非证据链路), 成本看板。
M19 供应链: 依赖锁定 + 镜像签名 + SBOM + 备份恢复自动化。
M20 发布候选: 15 门槛全绿 + 三仓库试点 2 周 + 运维手册终版 + 面试演示脚本。
## 卷 XIII. 技术栈候选清单与选型理由 (逐项评估)

### 13.1 编排框架
- LangGraph (保留): 状态图/检查点/中断恢复; 决策记录 ADR-018。
- 备选: 自研 DAG 执行器 (已有 10 态状态机底座), smolagents (轻量, 仅参考
  其 CodeAgent 设计), PydanticAI (结构化 LLM 调用值得评估 — 见 13.3)。
- 不采用: LangChain chains (黑盒/审计差), CrewAI/AutoGen (多智能体叙事强、
  可控性弱, 与我们审计要求冲突; 需要的并行编排自己用任务池实现)。

### 13.2 RAG
- 向量库: ES dense_vector (零新组件, 已预留) 为默认; 评估 Qdrant/Milvus
  (数据量大后迁移), pgvector (CP 侧轻量场景)。决策: 先 ES, 迁移口留好。
- 嵌入: OpenAI 兼容 /embeddings (BYOK, 复用 provider) 为主; sentence-transformers
  本地为可选 (无外联部署)。
- 重排: bge-reranker 本地 (可选依赖) → LLM 重排 (预算内) → 保序 (诚实标注)。

### 13.3 LLM 工程
- 结构化输出: Pydantic + Instructor 风格校验 (自实现三层, 不引重依赖);
  评估 PydanticAI (类型化 agent 循环, 若成熟可吸收其设计)。
- 网关: 自研 provider (探测+降级, 实测 8/11) 为默认; LiteLLM 仅评估 (路由/
  计费聚合), 不替代探测模型 (ADR-019)。
- 提示词优化: DSPy 评估 (M12), 不上线未审提示词。
- 缓存: 前缀 KV (已做) + 语义缓存 (M18, 仅非证据链路, ADR-020)。

### 13.4 基础设施
- 部署: Docker Compose 单机 (现状, 16-32GB 目标机); 不引入 K8s (ADR-016)。
- 观测: OTel + Prometheus + Grafana (已落地, 继续补指标)。
- CI: GitHub Actions (lint/type/security/unit/infra/eval 子集/夜间全量)。

## 卷 XIV. 风险登记与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 网关/模型变更破坏探测假设 | 中 | 高 | 11 维探测前置 + 每轮 LLM 基准回归 |
| 评测过拟合 (案例调优) | 中 | 高 | holdout 锁定 + 盲评 + 双口径基线 |
| 多子代理并行冲突 (本季已发生) | 高 | 高 | 车道边界制 + 持久提交纪律 + 提交前全绿 |
| 依赖/供应链风险 | 中 | 中 | 锁定 + 扫描 + 最小依赖原则 |
| 预算失控 (LLM 成本) | 中 | 中 | TokenBudget + KV 优化 + 成本看板 |
| 上下文过长导致质量退化 | 中 | 高 | 图谱邻域 + 中间摘要 (M10) + 预算截断 |

## 卷 XV. 执行节奏与纪律 (长期化)

- 车道制: 每车道一个子代理 + 明确文件边界 + 完成报告模板 (文件清单/门禁
  输出/偏差清单)。
- 提交纪律: 每里程碑/每大块 → git commit → 推本地镜像 + bundle → 推 GitHub
  (令牌权限修复后); 提交信息 W<N>: <主题>。
- 全绿定义: ruff + mypy strict + bandit (包列表, Medium+ 0) + pytest 全量
  (no-infra) + 集成子集 + compose config; 评测/基准按里程碑要求。
- 每轮报告: 审计发现 → 实现 → 验证输出 → 指标变化 → Next。
- 长跑机制: goal rounds 自动续跑, 每轮至少一个可验证增量; 无增量时做
  审计/基准重跑 (也产生证据)。

## 卷 XVI. 附录

A. 命令清单 (probe/verify/eval/replay/baseline/contracts/craft/mcp/health)
B. 指标看板字段表 (grafana 面板 ↔ 代码注册点)
C. 文档索引 (PRODUCTION_SPEC / SPECCRAFT_PLAN / AGENT_STATE_OF_ART /
  GRAND_PLAN_V2 / ADR-001..017 / RUNBOOK / OBSERVABILITY / FRONTEND)
D. 面试演示脚本 (一条命令出代码+证书: craft run --accept → verify →
  certificate; 一条命令出基线对比: baseline --mode llm)

## 卷 XVII. 本计划书的演进方式

本文件是活文档: 每轮实现后更新对应卷的"现状"与"里程碑"状态; 新想法以
ADR/新卷追加; 五万字目标按轮次持续扩写 (当前 ~1.2 万字, 每轮 +2-5k 字),
直至覆盖全部 17 卷的细节 (每个里程碑的验收命令、每个模块的接口契约、
每个指标的测量方法)。
## 卷 XVIII. 突破性/新颖功能设计 (行业首创候选, 按可实现性排序)

本卷回答"能给行业带来什么突破" — 每个功能都给出: 一句话主张 / 为什么没人做 /
设计要点 / 实现路径 / 验收标准。全部在本项目架构内可实现, 不画饼。

### 18.1 契约血缘证据链 (Contract Lineage — 密码学级可追溯验收)
主张: 世界上第一份"可密码学追溯"的 AI 变更验收 — 从需求到证书的每一步
(certificate 里的每个数字) 都能沿哈希链回溯到原始实验产物。
为什么是突破: 现有 CI/评审工具给你一个"通过"结论, 但不给你"为什么通过"的
可验证因果链; 我们已有 in-toto 风格签名, 缺的是把全链哈希化。
设计:
- 证据 DAG: 节点 = requirement(spec_digest) / contract_version / checker /
  experiment / artifact(sha256) / capsule(manifest_digest) / finding /
  certificate; 边 = produced_by / verifies / derived_from。
- 每条边带 sha256(node_a + node_b + 边类型), 根哈希写入证书 extension 字段。
- verify_lineage(certificate, dag) 重算全部哈希 → 任一产物被篡改即证伪。
- 前端: Finding 详情页可视化血缘图 (SVG)。
实现路径: evidence/lineage.py (build/verify/serialize) + publish_report/
certificate 节点接线 + 前端面板 + 篡改检测测试。
验收: 篡改任一 capsule/报告后 lineage 校验失败 (单测); 旗舰案例证书含
完整血缘根哈希 (实测)。

### 18.2 变异驱动的测试强化闭环 (Mutation-Guided Test Hardening)
主张: 让"活下来的变异体"自动变成"新测试" — SpecCraft 与 SpecProof 的闭环
里最锋利的一环: 变异分析发现的测试弱点, 由开发 Agent 自动补测试杀死,
再验收, 形成 变异→补测→再变异 的自强化循环。
为什么是突破: 行业里 PIT/变异工具止步于"报告存活体"; 我们把它变成
开发 Agent 的任务源 (闭环首次打通)。
设计: surviving mutants → (等价性判定后) → craft 任务 "为 <方法> 补一个
能区分该变异体的测试" → 新测试跑在 Base(绿) 与变异体(红) → 双绿判定 →
合约升级 (TEST_STRENGTH 记录)。
实现路径: M12-M13 (craft 微基准任务 6 已有雏形; 与 mutation runner 接线)。
验收: 微基准任务"补测试杀变异"机器判定通过率 ≥ 80%; 100 案例中 mutation
案例的存活体数量下降可测。

### 18.3 注入免疫认证 (Prompt-Injection Immunity Certificate)
主张: 证书新增安全维度 — "本 PR 在 N 类注入攻击下验证, 验证结论 0 受影响"
(已实测: 裸模型被注入影响报假问题, 我们的管线 0 影响 — 把这个事实变成
可签发的、可复现的认证)。
为什么是突破: 供应链时代"代码是否安全"之外,"验证过程是否被操纵"同样致命,
目前无人认证后者。
设计: verify 阶段强制注入对抗套件 (15 类注入样本注入 diff/README/spec/
branch/commit 等), 每次验证结论记录 injection_matrix_results; 证书扩展
injection_immunity: {cases: N, influenced: 0}; 重放可复现 (套件哈希入血缘)。
实现路径: 注入矩阵 (K 车道扩) + evidence_policy_gate 前置硬门 + 证书字段。
验收: 200 案例中注入类全过; 证书字段实测存在且重放一致。

### 18.4 跨 Agent 中立验收 (Agent-Agnostic Attestation)
主张: SpecProof 不为任何厂商站台 — 任何 Agent (Claude Code/Codex/Cursor/
DeepSeek/自家 SpecCraft) 的产物都接受, 同一套契约与证据标准验收并签发 —
成为"AI 代码的独立裁判"这一中立基础设施。
为什么是突破: 当前各家 Agent 自带评审, 球员兼裁判; 行业缺一个中立的、
跨工具的验收层 (类似 CA 之于 HTTPS)。
设计: 输入适配层 (各 Agent 的 PR/补丁/会话产物 → 统一 ChangeBundle) +
MCP 入口 (J 车道) + GitHub App 通用触发; 证书不含 Agent 品牌 (仅记录
toolchain 元数据)。
实现路径: MCP (在途) + ChangeBundle schema + 适配器 (cursor/claude/codex
各一个, 从 PR 格式切入) + 文档。
验收: 用两个不同 Agent 产物跑同一案例, 证书字段一致 (除 toolchain)。

### 18.5 可证伪验收协议 (Falsifiable Acceptance — 评审法庭升级)
主张: 每条 BLOCKER/MAJOR 都附带"什么证据能推翻它" — Defender 的反证实验
是签发的必要输入; 证书记录证伪条件。把验收从"模型断言"升级为
"可被任何人设计实验推翻的结论" (波普尔式质量)。
为什么是突破: 行业评审只给结论不给证伪路径; 可证伪性是可审计 AI 的关键
性质, 目前无人产品化。
设计: review_court Defender 输出 falsification_plan (一个能证伪该 finding
的实验设计); verifier 试跑 (预算内) — 若证伪实验通过 → finding 降级/撤销
(记录); 证书记录每个高等级 finding 的 falsification 状态。
实现路径: review_court 节点扩展 + 实验调度预算 + 证书字段。
验收: 构造一个"假阳性"案例, Defender 证伪路径能自动撤销 finding (实测)。

## 卷 XIX. 五万字扩写路线 (本卷之后每轮追加)

- 每轮执行后: 更新对应卷状态行 + 追加"实测记录"小节 (每轮 +1-3k 字);
- 待扩写至细节级的卷: IV (RAG 实现细节) / VI (契约 schema 全表) /
  VII (端点规格) / X (SOP 全文) / XII (每里程碑验收命令) / XVIII (实现进展);
- 五万字 = 17+2 卷 × 平均 2.6k 字, 目标按轮次在 20 轮内达成;
- 每次追加随里程碑提交 (git + 镜像 + bundle)。
## 卷 XX. LLM 工具调用深化设计 (新增)

### 20.1 并行工具调用
- 现状: 单次 chat 单工具 (envelope) 或原生 tool_calls (网关支持, 但 thinking+工具
  不共存已实测)。
- 设计: 规划/诊断请求允许模型一次提出多个独立工具调用 (原生 tool_calls 并行数组);
  envelope 模式保持单对象 (协议限制); 工具执行层并发执行独立调用 (asyncio.gather,
  每工具独立超时), 结果按 tool_call_id 回填; 总工具调用预算不变 (max_tool_calls)。

### 20.2 工具结果结构化回喂 (注入防线)
- 每条工具结果包 envelope: {status: ok|error, output_head, output_tail, error?,
  truncated, bytes}; 只回喂截断内容; 工具输出一律进"数据段", 禁止出现在系统指令
  位; 结果中的 "IGNORE ALL..." 文本保持原样但已被分段防御 (实测 0 影响)。

### 20.3 工具 schema 版本化
- 每个工具定义带 version; provider 探测结果记录支持的 schema 版本; 降级时按版本
  矩阵选择 envelope/原生; 工具变更必须走版本号 + 兼容测试 (MCP 侧同规则)。

### 20.4 工具超时与预算联动
- 每工具 timeout (默认 120s), 超时 → 诚实 error 回喂模型 (模型可改路径);
  工具层超时计入时间预算; 连续 3 个同类工具超时 → 任务 EXPIRED (不空转)。

## 卷 XXI. Agent 记忆与长期上下文 (新增)

### 21.1 记忆分层
1. 会话记忆 (进程内): 当前任务步骤的决策/产物引用 (现状: checkpoint 已有)。
2. 任务记忆 (新增, craft/memory.py): 任务级事实库 — 已读文件/已改文件/错误签名/
   关键决策/预算消耗, 序列化 memory.json; resume 时注入规划/诊断上下文 (数据段,
   预算截断 ≤ 2k tokens)。
3. 仓库记忆 (M8 排期): AGENTS.md/CLAUDE.md 策略摄取 + 检索历史 (RAG 2.0 已就绪)。
4. 跨任务记忆 (M18 排期): 契约/修复模式库 (非证据链路可缓存, ADR-020)。

### 21.2 压缩 (compaction)
- 上下文超预算 → 触发压缩: 旧步骤摘要 (LLM summarize, 预算内) 替换原始消息;
  checkpoint 记录压缩点与摘要哈希; resume 可从摘要重建上下文; 压缩只作用于
  规划/诊断上下文, 不动证据链路。

### 21.3 流式交互 (新增, 本轮 N 车道)
- craft run --stream: 规划与诊断的 token 级流式输出 (provider chat_stream);
  支持 Ctrl-C 优雅中断 (当前步骤落 checkpoint 后退出); 非流式环境自动回退。
- CLI 进度: 步骤状态条 (s1..sn 状态/迭代/耗时) + 流式模型输出窗口。

## 卷 XXII. 提示词工程系统化 (新增)

- 模板注册表: providers/prompt_templates 已是单一来源; 增加版本号 + 变更日志;
- A/B 与回放: 提示词变更必须跑微基准 (10 任务) + LLM 基线 (100 案例) 前后对比,
  报告 delta; 提示词回放 (同一输入重放历史提示词版本);
- few-shot 注入: 按任务类型挂示例 (稳定前缀外、变量段内), 示例库版本化;
- 未审提示词不上线 (人工审批 + 评测证据)。

## 卷 XXIII. 技术栈候选追加评估

- uv (包管理): 评估替换 pip+venv (锁文件/速度) — 低风险, M19 与依赖锁定一起做。
- PydanticAI: 设计参考 (类型化 agent 循环), 不引入依赖; 我们已有的
  LLMResponse/Plan/Step Pydantic 体系等价覆盖。
- smolagents: 借鉴 CodeAgent 的"代码即行动"思路评估 (可选 M5 实验); 不替代
  craft 循环 (我们的审计/证据要求更硬)。
- LangGraph 迁移预案: 若未来弃用, 自研 DAG 执行器接口契约 = 节点函数签名不变 +
  状态 dict 不变 (迁移成本 ≤ 2 天, ADR-018 记录)。
- 向量库: ES 默认 (已落地); Qdrant/Milvus 迁移口 = retrieval/hybrid 的
  search 接口抽象 (L 已留)。

## 卷 XXIV. 突破性功能实现进展 (卷 XVIII 对应)

| 功能 | 状态 |
|---|---|
| 18.1 契约血缘 | ✅ 已实现 (W13, 19 测试, 篡改定位实测) |
| 18.2 变异驱动测试强化 | 排期 M12-M13 (微基准 task-06 已具雏形) |
| 18.3 注入免疫认证 | 矩阵 24 测试已建; 证书字段待 M12 |
| 18.4 跨 Agent 中立验收 | MCP 入口已建 (W14); ChangeBundle schema 待 M11 |
| 18.5 可证伪验收 | review_court falsification_plan 设计定稿, 实现待 M12 |

## 卷 XXV. 本轮新增实施车道

N 车道 (Agent 记忆 + 流式): craft/memory.py 任务记忆 + craft run --stream +
中断落 checkpoint + 测试; 完成后更新本卷状态。
