# P6 评测说明 - 100 金案例构成与评测经济学

> 状态: 阶段一完成 (案例文件/构建器/agent 管线/验收测试/docs 全部就绪,
> 约束解除后 agent/ 已重新落地并全量验证)。
> 阶段二 (builder/tag/全量评测) 等队长授权。

## 1. 构成 (100 = 20 + 80)

| 类别 | 现有 | 新增 (case-21..100) | 合计 |
|---|---|---|---|
| Auth | 8 | 7 (4+ / 3-) | 15 |
| Tx/Concurrency | 3 | 12 (8+ / 4-) | 15 |
| Migration/Schema | 1 | 9 (5+ / 4-) | 10 |
| API 兼容 | 3 | 7 (5+ / 2-) | 10 |
| Redis | 0 | 10 (7+ / 3-) | 10 |
| MQ/Outbox/幂等 | 3 | 7 (5+ / 2-) | 10 |
| Logic/Boundary | 1 | 9 (6+ / 3-) | 10 |
| Perf/N+1 | 0 | 5 (4+ / 1-) | 5 |
| Weak-tests/Mutation | 0 | 5 (4+ / 1-) | 5 |
| Prompt-injection/Sandbox | 0 | 5 (全负) | 5 |
| Reliability/dup-events | 1 | 4 (3+ / 1-) | 5 |

总计 100 案例: 正样本 63 / 负样本 37。holdout (case-01/05/09) 锁定不动;
新增负样本全部要求 0 finding (含 5 个 prompt-injection 文本注入到
README/注释/requirement.txt/schema.sql/pom.xml 的沙箱语义案例)。

## 2. 检测面与严重度政策

- 正样本优先 execution-only: 差分测试 + 状态快照 (users/products/orders
  三表 H2 取证) + mock 调用断言 (Redis/RabbitTemplate) + SqlQueryCounter
  查询计数。静态可检的 (注解移除/DTO 字段/DDL 变更/测试弱化) 保留一部分,
  由静态检查器封顶 MAJOR。
- BLOCKER 需 6 条件 (approved contract + 真实 base/head 执行 +
  归因 head + DB/行为证据 + capsule 可回放 + confidence >= 0.90)。
  新案例中 base_pass_head_fail 且 H2 dump 因回归发生表级差异的
  (Auth 4 / Tx 5 / Logic 4 / Rel 1) 期望 BLOCKER; 其余 execution-only
  期望 MAJOR; 纯静态期望 MAJOR。case-17 先例 (期望 BLOCKER 实测 MAJOR)
  提示实际落档以评测输出为准, 评测匹配按 contract-id 而非严重度。
- 负样本: 等价重构/等价注解/收紧权限/注释/文档/空白/注入文本 - 必须
  0 finding (split.json negative.max_findings = 0)。

## 3. 构建与标签 (阶段二执行步骤)

1. 队长/发布流提交 demo/ (P6 扩展基座, 含 cache-aside、orders/products、
   SqlQueryCounter、schema.sql、测试修复) - builder 的 require_clean()
   只检查 demo/ 子树, 主工作树可长期不干净。
2. 运行 python scripts/build_golden_scenarios.py (授权后):
   - tag base 指向该 demo 提交 (新基座);
   - 重建 head-v1 = base 去掉 @PreAuthorize (旗舰回归, 语义不变);
   - 每案例 detached 提交 (父提交 = base) 得到 case-01..100-head;
   - 收尾 restore demo/ 到 base 并自检 demo/ 干净。
3. 案例目录/ground-truth/split.json 由 P6_CASES 数据表单源生成
   (emit 脚本已执行: 100 目录 + registry 98 条)。

## 4. 评测经济学: Base 构建复用

- 机制 (agent/nodes/build_cache.py + run_differential +
  generate_counterexamples), 三项压缩:
  1) Maven 调用 3 -> 2: 确定性路径在 generate_counterexamples 里跑
     头侧完整测试 (compile+surefire 一次沙箱调用), 记录 exit/test_counts/
     compile_error/test_file_sha256; run_differential 校验 sha 一致后
     head_run_reused=true 直接复用该记录 (编译失败仍按原语义归为
     NON_REPRODUCIBLE);
  2) 首个案例 base 全量构建后, target/classes + test-classes 缓存到
     reports/.base-build-cache/<base-sha>/ (surefire 报告与 H2 状态文件
     刻意排除 - 证据必须每案例新鲜产生); 后续案例 base 侧恢复缓存 +
     冻结全部源码 mtime (base 源码跨案例恒定) + -Dmaven.main.skip=true,
     只编译之后注入的生成测试 + surefire;
  3) head 侧播种同一缓存并回拨未变更源码 mtime (变更文件及其 mention
     依赖保持新 mtime 触发重编译); 若 Maven 增量判定与预期不符,
     失败模式是整树重编译 - 只慢不错。
- 实测 (阶段一, 3 案例小样本, 本地模式): 每案例 53-65s, 复用路径
  base_cache_hit=true / head_run_reused=true 端到端验证, 检测 100/100/100;
  第十轮 20 案例基线 75-90min (~3.75-4.5min/case); 沙箱模式按每调用
  +15-30s 启动开销外推 ~2-2.5min/case, 100 案例 ~3.3-4.2h (slow_eval
  timeout 18000s 的依据)。
- 缓存键: git rev-parse base 的提交 sha; 目录在 reports/ 下 (gitignored)。

## 5. 离线依赖状态

- pom.xml 未新增任何依赖 (spring-boot-starter-data-redis 在 W5 已入,
  新代码只用 JPA/Spring/Jackson/Hibernate 既有 API); 沙箱缓存卷
  specproof-maven-cache 离线 mvn -o test 探针全绿 (阶段一实测)。
- 遗留预置需求: 无。

## 6. 验收门禁

- tests/integration/test_phase_acceptance.py: 100 目录断言; slow_eval
  全量 100 案例; HTML 报告子集改为 1 静态+执行正样本 + 1 负样本 +
  1 执行级 + 1 Redis 执行级 (case-01/10/17/56)。
- CI 的 eval-golden-cases job 文本 ("20 golden cases", 90 分钟 timeout)
  需在阶段二前由队长同步更新 (.github/ 不在本子代理范围)。
