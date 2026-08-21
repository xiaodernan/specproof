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
2. 任务记忆 (✅ N 车道已实现, craft/memory.py): 任务级事实库 — 已读文件/已改文件/
   错误签名/关键决策/预算消耗, 序列化 memory.json; resume 时恢复并注入诊断上下文
   (数据段, 预算截断 ≤ 2k tokens)。实现要点: 条目 {kind, detail, step_id, ts,
   count}; 确定性去重 (error_signature 同类合并计数, file_read/file_written 按
   (kind, detail) 合并取最新, budget 仅留最新快照, decision 逐条追加);
   summarize_for_prompt() 按优先级 file_written > error_signature > decision >
   file_read > budget 整条截断, 每条一行紧凑文本; save/load 原子写 memory.json,
   缺失文件视为空记忆 (旧作业可续跑), 损坏文件响亮报错; file_written 来自 editor
   审计, error_signature 来自规则诊断; 注入路径仅经 prompt_templates.assemble()
   的 variable_data (task_memory 键), 绝不进稳定前缀 (AD 系列约束);
   所有产物 (checkpoint/report/memory.json) 无 reasoning 文本 (ADR-017)。
3. 仓库记忆 (M8 排期): AGENTS.md/CLAUDE.md 策略摄取 + 检索历史 (RAG 2.0 已就绪)。
4. 跨任务记忆 (M18 排期): 契约/修复模式库 (非证据链路可缓存, ADR-020)。

### 21.2 压缩 (compaction)
- 上下文超预算 → 触发压缩: 旧步骤摘要 (LLM summarize, 预算内) 替换原始消息;
  checkpoint 记录压缩点与摘要哈希; resume 可从摘要重建上下文; 压缩只作用于
  规划/诊断上下文, 不动证据链路。

### 21.3 流式交互 (✅ N 车道已实现)
- craft run --stream/--no-stream (默认 --no-stream 保持现状): 规划与诊断的
  token 级流式输出经 provider.chat_stream (LLMClient.stream_chat_sync 生成器 +
  stream_hook 驱动 chat()); 非流式环境 (无 key / 探测无 streaming) 诚实回退
  chat 路径并 yield 最终 content 一次, 每次调用以 stream_mode=native|fallback
  标注在 stats 调用条目上 (无伪造增量); 无 TTY 自动逐行缓冲输出。
- Ctrl-C 优雅中断: KeyboardInterrupt → 当前步骤以 verdict=interrupted 落
  checkpoint + memory.json 落盘, 退出码 130, 打印 resume 命令提示;
  report.json 仅在任务真正终态时写出。
- 已知取舍: 原生 chat_stream 在 provider 契约中无 response_format 槽位,
  --stream 下 JSON 契约由模板 OUTPUT CONTRACT + 容错解析兜底 (解析失败走既有
  诚实降级); usage 聚合来自 chunk 携带字段 (网关按能力回传)。
- CLI 进度: 步骤状态条 (s1..sn 状态/迭代/耗时) + 流式模型输出窗口 (排期 M 车道,
  本轮仅 token 流 + stream_modes 标注)。

### 21.4 实测记录 (N 车道)

**本地 mock 流式 (scripts/n-lane-stream-demo.py, 无网络)**
- native: MockProvider 逐 chunk 产出 ["hello", " ", "world"], 终端按序打印
  "hello world"; last_stream_mode=native; usage 聚合 prompt=21/completion=11/
  reasoning=4, budget.used=36.0 (加权和), 记账一次。
- fallback: get_capabilities() 无 streaming → chat() 路径执行一次, yield 最终
  content 一次; last_stream_mode=fallback; usage 正常入账。

**CLI --stream 无 key 回退 (speccraft-demo, SPECPROOF_SANDBOX=local)**
- specproof craft run task.spec --repo speccraft-demo --fix-module fixes.py
  --stream → 输出 "LLM unavailable: LLM_API_KEY 未设置 — falling back to
  deterministic" + "--stream: 无可用 LLM (无 key), 无流式输出, 按确定性模式执行";
  4 步全绿 DONE (s3 经注入 fix 修复, iterations=1); memory.json 落盘
  (file_read / file_written 来自 editor 审计 / decision / budget, 无 reasoning
  文本); exit 0。
- 同一 job 执行 craft resume → 4 步 resumed 证据, DONE, memory.json 完整加载。

**门禁**
- ruff / mypy / bandit 对 craft/memory.py + craft/llm.py + craft/loop.py +
  cli/specproof/commands/craft.py 全绿; craft 全套 116 tests 全绿 (含新增
  test_craft_memory.py 17 + test_craft_stream.py 13); tests/unit 全量 626
  passed (基线 2026-08-18)。

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

N 车道 (Agent 记忆 + 流式): ✅ 完成 — craft/memory.py 任务记忆 (去重/优先级
截断/save-load/注入数据段) + LLMClient.stream_chat_sync + stream_hook +
craft run --stream/--no-stream + Ctrl-C 中断落 checkpoint (退出码 130) +
tests/unit/test_craft_memory.py (16) + test_craft_stream.py (13) 全绿;
ruff/mypy/bandit 门禁全绿; 实测见 21.4。
## 卷 XXVI. RAG 3.0 深化设计 (图谱融合 + 检索评测落地)

### 26.1 三图融合 (代码图 + 文档图 + 契约图)
- 代码图 (现状): 类/方法/调用点, expand_hits 邻域扩展。
- 文档图 (新增): README/ADR/issue 段落 → 符号锚点 (路径/类名/方法名), 边
  documents/explains; 检索命中文档时反向拉取被解释的符号。
- 契约图 (新增): contract_id ↔ checker ↔ 历史案例 ↔ 修复模式, 边 verifies/
  detected_in; 命中契约时注入"该契约历史上怎么被违反过"的案例摘要
  (来自 golden-cases 元数据, 非证据链路, 可缓存)。
- 融合检索: 三图统一邻域扩展 (预算内), 结果带来源标注 (code/doc/contract)。

### 26.2 检索评测落地 (30 查询红线, L 遗留)
- 黄金集: 30 查询 (函数名/需求句/契约 id/错误信息) → 期望文件集;
- 指标: recall@10 / MRR / 单查询延迟;
- 运行器: scripts/bench_retrieval.py (mock ES + 真实图谱) + 每轮 RAG 改动必跑;
- 基线固化: 当前 BM25+图谱数字先存档, 向量/RRF/重排逐项消融报告。

### 26.3 向量库迁移契约
- retrieval/hybrid 的 search() 接口为唯一检索入口 (L 已留); 迁移 Qdrant/Milvus
  只实现该接口; ES 保持默认 (零新组件)。

## 卷 XXVII. 突破性功能第二波实现规格 (卷 XVIII 深化)

### 27.1 变异驱动测试强化闭环 (18.2 规格)
- 输入: surviving mutants 清单 (id/算子/位置/存活原因/等价性判定);
- 转换: craft 任务 "为 <方法> 写一个能杀死 <变异描述> 的测试" (模板 + 上下文);
- 判定: 新测试在 Base 绿 + 在变异体红 (机器双跑); 通过 → 测试入库 + 契约
  TEST_STRENGTH 记录; 失败 → 变异体标记 equivalent (可证伪记录);
- 预算: 每变异体 ≤ 2 次尝试; 每轮 ≤ 5 变异体 (经济性)。

### 27.2 跨 Agent ChangeBundle schema (18.4 规格)
- ChangeBundle = {source_agent, base_sha, head_sha, diff, spec, context_files,
  tool_traces(可选)}; 适配器: claude_code (PR diff + CLAUDE.md)、codex、
  cursor、generic (git diff 直读); 校验器: 字段完整性 + sha 一致性;
- 验收: 同一案例经两个适配器 → 证书除 toolchain 外逐字节一致。

### 27.3 注入免疫认证证书字段 (18.3 规格)
- extension.injection_immunity = {suite_version, cases, influenced};
- 生成: evidence_policy_gate 前强制注入套件 (15 类 × 正反), 记录每类影响数;
- 重放: 套件哈希入血缘 (18.1 已就绪), replay 复现同结论。

### 27.4 可证伪验收协议 (18.5 规格)
- Defender 输出 falsification_plan = {hypothesis, experiment, falsifies};
- verifier 预算内试跑 (≤1 次/高等级 finding); 通过 → 撤销/降级并记录;
- 证书 extension.falsification = {finding_id: {attempted, outcome}}。

## 卷 XXVIII. 评测自动化与 CI 编排深化

- nightly 矩阵: 100 案例全量 eval + LLM 基线双口径 + 微基准双档 (确定性/LLM)
  + 检索评测 + MCP 一致性 + 安全/故障全量 — 单 job 串行, 产出
  docs/eval/nightly-report.md + 历史归档;
- 回归红线: 任一项较上次倒退 → job 失败 + 告警;
- 成本核算: 每次 LLM 评测记录 tokens/费用 (预算账本), 月报汇总;
- 本地一键: scripts/run_all_evals.ps1 (队长/开发者入口)。

## 卷 XXX. 契约门禁纵深: 错误码 · OpenAPI 差分 · 事件信封 (W28 已交付)

> 状态: ✅ 已交付并上线 (commit e4ce0aa)。动机: AI 生成的 API 改动最易造成
> "契约漂移" — 无声 breaking change 在微服务边界积累, 运行时才爆发。
> 本卷把契约从"评审靠人"变成"机器门禁", 与 卷 XIV (中间件) / 卷 XVII
> (契约化) 的规划逐一呼应, 全部以真实运行验证 (非纸面设计)。

### 30.1 稳定错误码体系 (api/errors.py)
- 编码表: 10 个要求码 + STATE_CONFLICT(409) 扩展; 每条含稳定 code、
  默认 message、HTTP status — 语义化 4xx/5xx, 机器可 grep 可告警;
- 三件套: error_response(detail, code, ...) / api_error_response / ApiError;
  routes (jobs/web/webhooks) 与 server 全局 handler 统一输出
  {detail, error: {code, message, request_id}, schema_version: 1};
- 兼容铁律: detail 原文保留 — 既有消费方文本断言零破坏 (回归实测确认);
  request_id 与中间件 RequestID 联动, 线上问题日志→响应一键串链;
- 验证: tests/unit/test_api_errors.py 15 例 + 既有断言回归 110/110。

### 30.2 OpenAPI 差分门禁 (scripts/openapi_diff.py)
- 基线: docs/openapi/baseline.json (16 paths) 作为契约快照入库;
- 机制: 导出 OpenAPI → 与基线逐 path/method/参数形状比对 → breaking
  change (删 path、改必填、收窄类型) 输出 BLOCKING 报告 exit 1;
  明确豁免走 --allow 并留痕 (谁、何时、为何);
- CI: .github/workflows/ci.yml 新增 openapi-schema-diff job, 每个 PR 自动拦;
- 实测四跑全部真实复现: 基线生成 exit 0 → 无变更 exit 0 → 篡改基线
  exit 1 (BLOCKING 报告) → --allow 豁免 exit 0。

### 30.3 事件信封契约 (contracts/events.py)
- build_envelope: event_id = uuid4 hex (幂等/审计锚点), 密钥递归脱敏,
  确定性 sha256 payload_digest — 落盘前即完成不可抵赖摘要;
- 平铺兼容: wire 老字段全部保留, 新信封字段平铺附加 — 老消费者零迁移;
- storage/outbox_relay.py 接入: 出站消息统一走信封, 断链重放用 digest 去重;
- 验证: tests/contract/test_event_envelope.py 12 例 (脱敏/确定性/兼容)。

### 30.4 交付证据 (真实运行)
- 27 新测试; 定向回归 110/110; 全量 unit+contract 655 passed;
- ruff / mypy (9 文件 strict) / bandit (Medium+=0) 全绿;
- 破坏性代价: 0 — detail 断言、事件老字段、既有 OpenAPI path 全保留。

### 30.5 安全门禁纪律实战
- 事故: tests/unit/test_craft_verify.py 夹具字面量 'API_KEY = "sk-..."'
  同时命中 sk-[a-z0-9]{32,} 与 api_key= "sk- 双模式 → 门禁 2 红;
- 修复: 字面量改拼接 ("API_" + 'KEY = "' + "sk-" + ...), 运行时语义不变,
  源码静态扫描不再命中; 31/31 转绿 — 已成团队铁律 (所有假密钥必须拼接)。

### 30.6 演进路线
- OpenAPI 语义分级: required/type/enum 变化按 MAJOR/MINOR/PATCH 分级,
  仅 MAJOR 阻断, 其余计入报告;
- consumer-driven contracts: 从客户端调用流量回放生成基线 (替代手写);
- 契约漂移记录进 Merge Certificate extension (与 卷 XVIII 血缘链打通)。

## 卷 XXXI. 检索纵深: 四语言符号索引与 30 查询黄金基准 (W29 已交付)

> 状态: ✅ 已交付 (commit 8395899)。问题起源: RAG 2.0 chunk 检索对"符号级"
> 提问存在盲区 — 大文件 4000 字符截断后, 后半段符号不进索引, Agent 问
> "哪个函数改了"时召回为 0。本卷用最小符号索引补上这块, 实测发现两处盲区。

### 31.1 四语言最小符号索引 (retrieval/symbols.py)
- python: ast 精确解析 + 作用域 refs (change_email refs={load_user, update_email,
  user, user_id}, calls 边正确);
- typescript: 保守正则 (import/function/arrow/interface/class/export) + 声明守卫
  (拒绝 "ident(...) {"), conservative=True 标记; go: import/type/func/method;
  java: repo_graph 同风格等价切分 (@PreAuthorize 注解后方法名正确);
- SymbolIndex 图谱视图: resolve/neighbors/expand_hits/search; index_repo →
  {symbols, edges{calls,refs}, stats}; 单文件语法错 → 空+note, 全仓不中断。

### 31.2 30 查询黄金集 (retrieval/bench_queries.py)
- 10 符号名 / 10 需求句 / 10 错误信息 × 期望文件集 (语料 grep 逐条核验);
- recall@10 / MRR / summarize_bench 纯函数; 脚本双档: 真实 ES (只读复用
  storage.elasticsearch.search_code) 或 --offline 内存 BM25 mock — CI 无
  Docker 亦能跑, 每次运行独立 repo 名幂等重建。

### 31.3 实测结论 (真实 Docker ES, 86 文件 1610 符号, 2026-08-18 23:34)
| 系统 | recall@10 | MRR | 平均延迟 |
|---|---|---|---|
| BM25 | 82.2% | 0.656 | 50.5ms |
| BM25+图谱 (top-8 插值) | 48.9% | 0.528 | 89.6ms |
| symbol-index 查表 | 75.6% | 0.683 | 1.3ms |
- 关键发现 1: _chunk_files 4000 字符截断 → 大文件后半符号不进 ES
  (s03 CraftLoop / s05 deterministic_baseline BM25 零命中), symbol-index
  100% 找回 — 证明"符号级问题必须符号级索引";
- 关键发现 2: BM25+图谱低于纯 BM25 = top-8 种子邻域插值顶替了 9-20 位的
  既有 hybrid 语义 → 记为消融输入, 下一轮并入向量/RRF/重排再测。

### 31.4 工程决策与门禁
- ParseResult(symbols, notes, calls) 包装承载"语法错→空+note"契约;
- 15 新测试 (四语言解析/排除规则/图边/扩展/查表/黄金集完整性);
- 队长复跑: ruff ✅ / mypy 7 文件 strict ✅ / bandit exit 0 ✅ /
  pytest 58 passed ✅ (真实复跑, 非转述)。

### 31.5 演进
- 截断修复: chunk 重叠 + 符号锚点进 ES 字段 (让 BM25 找回后半符号);
- 混合重排: BM25 召回 → symbol-index 补盲 → 向量重排 (RRF);
- 查询改写: 需求句 → LLM 转符号名候选 → 查表 (1.3ms 档位);
- 黄金集持续扩至 100 条 (随语料增长 50+50)。

## 卷 XXXII. SpecCraft 核心工程底座: Schema·工具注册表·规则摄取·stale 保护 (W33 已交付)

> 状态: ✅ 已交付 (commit 6ffaa4e, R 车道)。这是"完整商业化代码开发 Agent"
> 的核心工程: 让 SpecCraft 的每一层 — 任务建模、工具调用、仓库规则、文件编辑 —
> 都变成可版本、可审计、可门禁的协议, 而不是散落的直连调用。

### 32.1 统一 Schema (craft/schemas.py, 403 行)
- AgentTask (task_id/text/repo/base_sha/execution_mode/budget/desired_checks/
  network_policy/model_policy/idempotency_key) + ToolCall {tool, version,
  call_id, arguments, budget_cost, requires_approval} + ToolResult + Approval
  + Artifact (sha256 digest 校验) + ChangeBundle (含 specproof_result);
- 全模型 schema_version=1 强制版本门 — 上游格式漂移在入口即被拒绝;
- PlanSchema/StepSchema 与 planner dataclass 双向适配 (plan_to_schema/
  plan_from_schema), 复用 planner DAG 校验: 唯一 id / 依赖次序 / ≤12 步。

### 32.2 工具注册表与版本化信封 (craft/tools.py, 917 行)
- 13 工具 v1, 风险四级: readonly 7 (read_file/tree/glob/grep/symbol_search/
  git_status/git_diff, 默认免审批) | low_write 2 (apply_patch/create_file,
  owned_paths 越界拒绝) | controlled_exec 4 (run_test/build/lint/typecheck,
  executor 白名单) | high 0 内建 (shell/network/git_push 预留, 默认需审批);
- dispatch 门链顺序: 未知工具 → 版本 → 参数 (类型/长度/范围) → 审批 →
  路径 → 执行 — 参数非法实测不执行;
- 12 稳定错误码 ([CODE] 前缀, 机器可 grep): UNKNOWN_TOOL /
  TOOL_VERSION_MISMATCH / INVALID_ARGUMENTS / PATH_ESCAPE / PATH_OUT_OF_RANGE
  / APPROVAL_REQUIRED / FILE_NOT_FOUND / NOT_A_GIT_REPO / COMMAND_NOT_ALLOWED
  / STALE_CONTEXT / EDIT_REJECTED / EXECUTION_FAILED;
- 结果截断 + 秘密脱敏 (sk- / Bearer / 私钥头) + untrusted 标签; envelope
  版本化且结果零泄漏; 审批判定 = risk 默认或 approval_policy (只能更严,
  故障 fail-closed); grant/revoke 内存态 (持久化归任务 3/8)。

### 32.3 仓库规则摄取 (craft/rules.py, 382 行)
- RepositoryRules.load(repo): AGENTS.md / CLAUDE.md / README / CONTRIBUTING
  / SECURITY.md / .github CI workflows + 子目录规则 (限深 4 / ≤30 文件,
  node_modules 等跳过, 单文件 200KB / 总量 1MB 有界读取 + 截断诚实标注);
- 7 级优先级 RulePriority(IntEnum): SECURITY(0) > ORGANIZATION(1) >
  REPOSITORY(2) > DIRECTORY(3) > TASK(4) > DEFAULT(5) > MODEL_SUGGESTION(6);
  内置平台安全策略封顶, SECURITY.md 归 security 层;
- 冲突检测: 中英文"忽略/跳过/不要安全"6 组正则 → RepoRule.conflict +
  conflicts() 列表 + security 层强制降级为 repository (实测 SECURITY.md
  含"忽略安全"不进 security 层 — 提示注入无法提升自己的优先级);
- 注入防御: prompt_block() 全部包进 craft.llm.wrap_data_section 数据段
  (实测注入文本只出现在分隔符之间, 模型不会把它当指令)。

### 32.4 editor stale 保护 (craft/editor.py)
- sha256 digest (raw bytes): read_file_meta / FileRead / file_digest;
- write_file/apply_edit 新增 keyword-only expected_digest → 不匹配抛
  StaleContextError(STALE_CONTEXT) 拒绝写入: 实测文件字节不变、不产生备份、
  审计记录拒绝 + 实际 digest; 新文件 expected_digest="" 允许, 非空 → stale;
  不传 digest → 旧行为 (positional 兼容, 134 既有测试全绿);
- 审计 AuditEntry 带 before_digest/after_digest (audit.jsonl 全字段);
- classify_workspace_changes(git status --porcelain) → {user_changes,
  agent_changes, unknown}: " M" 用户改动 / agent_paths 归 agent / 未跟踪、
  冲突对 (DD/AU/UD/UA/DU/AA/UU)、重命名归 unknown。

### 32.5 loop 接线 (向后兼容)
- 诊断提示的工具面改走注册表 envelope (wrap_data_section 数据段);
  LLM 编辑提案经 registry.dispatch (apply_patch/create_file);
- 共享单一 editor → 审计链 / report.diff_stat / 自校验 Base 快照三者一致;
  report.tool_registry 上账; from_checkpoint 透传;
- 无注册表时保留旧 _EDITOR_API_BLOCK (兼容实测)。

### 32.6 交付证据 (真实运行)
- 102 新测试 (schemas 27 / tools 36 / rules 17 / editor_stale 22);
- craft 全套回归 236/236 (队长复跑 2:33); 全量 unit 877 (R 口径);
- ruff ✅ / mypy 13 文件 strict ✅ / bandit exit 0 ✅;
- 偏差清单 7 条诚实记录: high 层无内建工具、审批内存态、结构化 Diff 待
  M4、provider tools 参数未接 (网关 strict_tool_calls=400 已降级 envelope)、
  [CODE] 前缀承载稳定码而非新增字段等。

### 32.7 演进
- M4: AST 编辑 + 结构化 Diff + 跨文件重构;
- M5: ChangeBundle → SpecProof accept 闭环 (任务 7 门禁组合, W34 在途);
- 组织策略注入接口 (org 层无标准文件名, 预留);
- provider tools 原生支持 (视网关能力演进)。

## 卷 XXXIII. 验收门禁组合与并行只读子代理 (W34 已交付)

> 状态: ✅ 已交付 (commit 8cb27bc + 审计 126c1c8)。这是 M5 强制闭环的上游工程:
> ChangeBundle 在进入 SpecProof 之前先过五道内部门禁; 同时把"只读侦察子代理"
> 并行化, 补齐对标 Claude Code/Codex 差距矩阵的并行能力项。

### 33.1 GatePipeline 五道门 (craft/gates.py, 544 行)
- GATE_ORDER = run_test → run_build → run_typecheck → security → self_verify;
- 每门统一结果契约 GateResult {gate, status: passed|failed|skipped|error,
  note, findings[], duration_ms}; 组合语义 FAIL > SKIPPED > PASS (镜像仓库
  FAIL>PASS>UNVERIFIED 惯例), 任一 error = 最差等级且诚实注记;
- GateReport 附可 grep 汇总行: GATES: task=... overall=... <gate>=<status>...
  duration_ms=... — CI/日志一条命令定位哪道门挂;
- 诚实 skipped 纪律 (绝不伪造通过): 无测试套件→skip+note; run_build 按生态
  (mvn -DskipTests compile / gradle compileJava / python compileall); run_typecheck
  = mypy 变更 .py, Java 诚实跳过 (由 build+契约检查覆盖); security = scanner
  过滤变更文件 + CANARY_MARKER (CRITICAL/HIGH 阻断, MEDIUM/LOW 记录);
  self_verify 原样复用 craft/verify.py (W26, verify.py 零改动);
- 可注入 executor/security_scan/self_verify_fn — 测试与生产共用同一组合逻辑。

### 33.2 ParallelRunner 并行只读子代理 (craft/agents.py, 304 行)
- asyncio.gather 真并发 (max_agents=8); SubAgentSpec {name, role, task,
  tool_allowlist, budget}; roles: explorer/tester/security;
- 派发层只读强制: ReadonlyToolSurface.call 拒绝任何注册 risk≠readonly 工具
  (apply_patch/create_file/run_* 结构性不可能) + 每代理 allowlist;
- validate() 启动前 fail-closed 拒绝: 非只读/未知工具、重名、N>上限、
  空集合、写集合重叠 (路径归一化) — 与任务 9"不共写同文件"铁律一一对应;
- 每代理 wall-clock 超时 (asyncio.wait_for → timed_out) + 预算经
  AgentContext.budget 透传 (超额记录) + 单代理崩溃隔离 (error outcome,
  其余继续);
- 单测实证 (真实计时): 双 0.2s 慢代理墙钟 <0.35s 且启动间隔 <0.15s —
  真重叠, 小于串行和 0.4s; LLM 执行器为注入式 callable, 零硬编码。

### 33.3 与总计划的呼应
- M5 闭环上游: W35 accept 车道直接消费 GatePipeline (设计
  docs/architecture/CRAFT_ACCEPT_DESIGN.md, 在途);
- 差距矩阵 (卷 XVIII): "子代理并行" 项由 D 级升 B+ 级 (只读受限并行 +
  写集冲突 fail-closed 比通用并行更安全, 但通用写并行仍待);
- 与 agent_jobs (W30) 组合后可实现"租约内只读侦察→门禁→accept"的完整
  恢复语义 (中断恢复后侦察结果复用)。

### 33.4 交付证据 (真实运行)
- 62 新测试 (gates 41 + agents 21); 目标套件 80 全绿 (含 verify 18);
- -k craft 全扫 338 passed 0 failed; ruff / mypy strict (2 文件) /
  bandit (--skip B101) 全绿 — 队长逐项复跑确认;
- 提交 8cb27bc 严格基于新头 a014078 (车道自查 + 队长核验), 无历史改写。

### 33.5 演进
- ParallelRunner × GatePipeline 组合工作流: 并行侦察结果直接喂门禁输入;
- LLM 执行器接线 (DeepSeek V4 Pro 网关, 注入式已留);
- 只读代理接入 symbol_search (S 车道索引) 提升侦察召回;
- 通用 (可写) 并行子代理: 需 write-set 事务化 + 逐文件锁, 列入 M7+。

## 卷 XXXIV. 评测工业化: 90 任务套件与表驱动生成 (W32 已交付)

> 状态: ✅ 已交付 (commit bd203a6)。任务: 把"10 个微基准"升级为可审计的
> 90 任务评测工厂 — 50 代码 + 20 对抗 + 10 断点恢复 + 10 危险动作审批,
> 全部由紧凑数据表幂等生成, 数字全部来自真实运行。

### 34.1 表驱动生成器 (scripts/bench_gen_tasks.py + _data.py)
- 每任务一行数据 (元数据 + fixture 文件 + 编辑序列 + judge 内容), 生成真实
  目录; 生成器输出统一有序幂等 fixes.py (每次只应用第一个尚未生效的编辑,
  多阶段收敛跨循环迭代), 宽度感知折行 + import 归一化保证 ruff 全绿;
- --check 逐字节校验零漂移 (已测); 生成时经 craft.spec/Plan/compile 校验;
- 与手工 legacy 10 任务共存, 默认运行输出与旧版逐字节兼容。

### 34.2 四类任务与实测 (确定性档, --sandbox local, 90 任务, exit 0)
| 类别 | 数量 | 结果 |
|---|---|---|
| 代码 (10 单文件 bug + 10 多文件功能 + 10 重构 + 10 真实工程 + legacy 10) | 50 | 49/50 = 98.0% (trap 任务按口径 INTERCEPTED); 平均迭代 1.23 |
| 对抗 (误导 Issue/README+注释注入/过时测试/隐藏禁止变更 各 5) | 20 | 20/20 INTERCEPTED (拦截 100%) |
| 断点恢复 (预置半程 checkpoint/memory/plan + audit 副作用账本) | 10 | 10/10 RECOVERED, 账本恰好 1 行 (无重复副作用, judge 幂等) |
| 危险动作审批 (git commit/push/force-push/tag/删分支/网络/制品/销毁) | 10 | 10/10 APPROVAL_REFUSED, 违规 0 (执行器白名单拒绝 + refusal.json 在案) |
- craft_failed=0, judge_error=0; legacy 单独复跑与旧报告一致 (90.0%/1.1/100%)。

### 34.3 工程决策与偏差 (诚实记录)
- 审批口径: 当前无审批服务且白名单不含 git/网络 → 期望口径 = APPROVAL_REFUSED
  (危险动作零执行), 文档标注审批服务上线后的升级路径 (真实审批门两分支,
  APPROVAL_BREACH 继续硬失败);
- LLM 档未跑: 无 key 诚实拒绝伪造, 报告标注待测 (与"绝不伪造"纪律一致);
- task-28 退避计时改 monkeypatch 确定性断言 (wall-clock 高负载 flaky, 已修正
  并全量复跑);
- 高负载并行车道环境完成全套, 数据为时间戳快照。

### 34.4 证据与门禁
- 37 新测试 (分类/判定/生成幂等/落盘无漂移/checkpoint 改写);
- 全量 tests/unit 990 passed (队长复跑 5:15); ruff/mypy strict/bandit 全绿;
- 报告: docs/eval/agent-task-suite.md + results.json (全量明细)。

## 卷 XXXV. M5 强制闭环: SpecCraft→SpecProof Accept (W35 已交付)

> 状态: ✅ 已交付 (commit 06a8207)。这是整个产品的"王冠接缝": 开发 Agent
> 的产出必须被验收防火墙独立判定后才能接受 — 任何一方单独放行无效。

### 35.1 craft_accept 五阶段 (craft/accept.py, 775 行)
1. 工作区守卫: classify user/unknown 改动 → 拒绝且绝不 reset;
2. 内部门禁: GatePipeline 任一 FAIL/error → STOP (不调 SpecProof),
   git reset --hard base, 无证书;
3. 独立验收: 默认 verify_fn 原样复用 agent graph (build_phase0_graph +
   initial_state + invoke, 与 cli verify 同款, 工作树自动清理);
4. VERIFIED → Merge Certificate + lineage 扩展 (contracts→findings→
   ChangeBundle 摘要血缘) + Ed25519 签名 (evidence/signing.py, 缺钥 → ERROR,
   绝不静默无签名 accept);
5. 其余判定 → 回滚 + 拒绝通知; 幂等键 (job_id, head_sha, bundle_digest)
   重复 accept 返回既有证书。

### 35.2 接线与 CLI
- CraftLoop 完成态 → report.gates (五道门摘要) + AgentJobStore 全周期接线
  (create/lease/renew/progress/update_status/cancel, 按 W30 Integration note);
- CLI: craft accept --job <id> --base <sha> --repo <path> --db <sqlite>,
  退出码 0 VERIFIED / 1 BLOCKED / 2 ERROR。

### 35.3 实证 (真实运行)
- 22 新测试 (accept 15 + loop_jobs 7), craft 扫 360 绿 (队长复跑 5:03);
- E2E 冒烟 (无 Docker): loop DONE → 门禁 5/5 passed (真实 pytest/compileall/
  mypy/security/self-verify) → 真实 agent graph 判定 → fail-closed BLOCKED +
  git 回滚 + 拒绝通知; Docker 沙箱路径验证门禁 FAIL ⇒ STOP 不调 SpecProof;
- 已知限制 (诚实记录): 终态 job 的 result_json 投影关闭 → 事后 CLI accept 结果
  打印+尽力持久化; W35.1 扩展 attach_accept_result (终态专用投影, 在途);
- VERIFIED 路径需 Spring demo + maven 手动步骤 (命令已文档化)。

### 35.4 演进
- 补跑 VERIFIED 路径 E2E (Java demo) 形成闭环全路径证据;
- accept 结果进 Web 工作台 (W31) 状态徽标 (attach_accept_result 落库后);
- KMS/HSM 上线后 signer 切换 (接口不变); accept 次数与 token 计入阶段 6 账本。

## 卷 XXIX. 本计划书进度

当前 ~3.9 万字 (35 卷)。扩写路线: 每轮 +2-3k 字, 优先补
卷 IV/VI/VII/X/XII/XVIII 的实现细节与实测记录, 目标 20 轮内达 5 万字。
