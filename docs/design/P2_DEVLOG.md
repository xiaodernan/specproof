# SpecProof P2 阶段开发记录 (2026-08-17, 第二轮)

本文档追加在 DESIGN_REVIEW.md 之后, 记录 P2 契约编译器开发中发现并修复的问题。

## 本轮实现

1. **agent/contracts/parser.py** — 结构化需求解析器:
   编号章节(冒号前截断为标题, 冒号后保留在正文)、模态动词验收标准提取
   (bullet 与散文两种)、禁止变更提取、优先级推导、LLM 富化 + Pydantic schema 校验。
2. **agent/contracts/compiler.py** — 契约候选编译器:
   需求→checker 家族映射、仓库宪法(README/ADR)规则提取、去重、
   family_id_for 映射(候选 id → 检查器家族 id AUTH-01/UNIQUE-01/...)。
3. **agent/contracts/registry.py** — 契约注册表 (MySQL contract_registry +
   contract_approvals): propose/approve/reject/revoke, spec_digest 版本隔离
   (旧 spec 的批准不转移到新 spec), CAS 状态迁移 + 审计表。
4. **cli contract** — specproof contract propose/list/approve/reject。
5. **checker 注册表** — 新增 OPENAPI-01 端点面检查器 (verb+path 集合差分)。
6. **storage/elasticsearch.py** — 仓库级 symbol 分块索引 + bulk 写入 +
   BM25 检索 (content/symbol 双字段); retrieve_repository_context 节点接入
   13 节点管线, 按 checker 家族词典增强查询。
7. **verify --use-approved-contracts** — 审批契约映射到家族 id 进入管线;
   Review Court 条件 1 要求契约 approved (未批准候选不能支撑 BLOCKER)。

## 本轮发现并修复的问题

1. **契约注册表 DDL 索引过长**: repo_path VARCHAR(1024) 上建索引在 utf8mb4
   下 4096 字节 > InnoDB 3072 上限 → 缩为 VARCHAR(512)。
2. **ES 客户端主版本与服务端不匹配**: pip 装的 elasticsearch 9.4.1 对
   ES 8.16 发送 compatible-with=9 头, 服务端 400 拒绝 → pyproject 固定
   elasticsearch>=8.16,<9。
3. **delete_by_query 在 Windows 上原生崩溃** (elasticsearch-py 8.19.3,
   进程级 crash 无 traceback) → 改用 delete-index + recreate 实现仓库重索引。
4. **per-doc refresh=True 索引过慢** (30+ 文档 × 每文档一次磁盘刷新 →
   分钟级) → 改 bulk 写入 + 单次 refresh。
5. **注解切分正则灾难性回溯**: entity/User.java (12 个 @Column 注解) 让
   外层注解重复组指数级分区, 单文件分钟级 → 外层重复改为 possessive (*+),
   内层保留可回溯以支持嵌套括号 @PreAuthorize("isAuthenticated()")。
   实测: 全部文件 0.0s, 49 symbol chunks。
6. **需求解析器吃标题**: 原标题正则吞掉冒号后的需求正文 → 改为 lookahead
   截断 + body 保留; 序言(preamble)拼接到第一节末尾而非开头, 避免遮蔽正文。
7. **检索词法失配**: 需求散文 ("require authentication") 与代码 token
   (@PreAuthorize) 不匹配 → 按 checker 家族词典增强查询词。
8. **registry 测试夹具** — DELETE 语句的占位符测试了缺失的 requirement 列
   → DDL 补列 + 单游标执行修复。

## 实测 (P2 里程碑)

- 全量 pytest 262 passed (新增 20 个 P2 测试)
- ruff / mypy strict 全绿
- contract 流: propose(8 候选) → approve(6) → verify --use-approved-contracts
  → "Using 6 registry-approved contract(s)" → BLOCKER+MAJOR → BLOCKED
- ES 检索: 实测 Indexed 49 symbol chunks; 2 retrieved (auth 需求命中
  @PreAuthorize 相关符号)
