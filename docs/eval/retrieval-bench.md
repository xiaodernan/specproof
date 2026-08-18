# 检索基准实测报告 — 30 查询黄金集 (M2 / §22-5)

- 生成时间: 2026-08-18 23:34:37 +0800
- 基线: BM25 (真实 Elasticsearch localhost:9200 · index specproof-code-phase0) + 图谱扩展 (开, top-8×1 跳)
- 语料: cli/ + agent/ + craft/ (Python) + demo/spring-backend (Java) · repo=specproof-retrieval-bench · commit_sha=bench-m2

## 方法

- 30 条黄金查询 (10 符号名 / 10 需求句 / 10 错误信息), 每条固定期望文件集; 期望集以「定义或直接佐证该查询行为」为准, 2026-08-18 按语料 grep 核验, 未按任何检索系统调参。
- 指标: recall@10 (期望文件在前 10 条去重路径中的占比) / MRR (首个期望文件排名倒数) / 平均延迟 (search+expand 墙钟, 30 查询平均)。
- 对比系统: BM25 (storage.elasticsearch.search_code, 现有实现只读复用) → BM25+图谱 (retrieval.symbols.SymbolIndex.expand_hits, 与 agent.repo_graph 同风格) → symbol-index (符号名/引用确定性查表, 附加列)。

## 索引统计

- 文件: scanned=86 · ok=86 · failed=0
- 符号: 1610 · 按语言: java=349, python=1261
- 符号按 kind: assign=190, class=94, function=263, import=739, method=324
- 边: calls=4819 · refs=6951

## 汇总 (n=30)

| 系统 | recall@10 | MRR | 平均延迟 | 全命中查询数 |
|---|---:|---:|---:|---:|
| BM25 | 82.2% | 0.656 | 50.5 ms | 21/30 |
| BM25+graph | 48.9% | 0.528 | 89.6 ms | 11/30 |
| symbol-index | 75.6% | 0.683 | 1.3 ms | 20/30 |

### 按查询类型 (BM25+graph)

| 类型 | n | recall@10 | MRR | 平均延迟 |
|---|---:|---:|---:|---:|
| symbol | 10 | 58.3% | 0.551 | 55.3 ms |
| requirement | 10 | 28.3% | 0.329 | 109.8 ms |
| error | 10 | 60.0% | 0.704 | 103.7 ms |

## 每查询明细

### s01 · symbol · python

- 查询: RepoGraph
- 期望文件 (1): agent/repo_graph.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=9.3 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=11.4 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.1 ms
- BM25 top-10: 1. ✔ agent/repo_graph.py
- +graph top-10: 1. ✔ agent/repo_graph.py; 2. · agent/checkers/java_source.py; 3. · agent/checkers/schema_and_tests.py; 4. · agent/contracts/compiler.py; 5. · agent/contracts/parser.py; 6. · agent/fixes.py; 7. · agent/nodes/build_cache.py; 8. · agent/nodes/collect_diff.py; 9. · agent/nodes/compile_contracts.py; 10. · agent/nodes/generate_counterexamples.py; … 共 46 条

### s02 · symbol · python

- 查询: MongoDBSaver
- 期望文件 (1): agent/mongo_saver.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=68.8 ms
- BM25+graph   : recall@10=0.0%  MRR=0.030  延迟=79.7 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.9 ms
- BM25 top-10: 1. · agent/worker.py; 2. ✔ agent/mongo_saver.py
- +graph top-10: 1. · agent/worker.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/review_court.py; 7. · agent/nodes/run_deep_experiments.py; 8. · agent/nodes/run_differential.py; 9. · agent/nodes/run_release_checks.py; 10. · cli/specproof/commands/baseline.py; … 共 55 条

### s03 · symbol · python

- 查询: CraftLoop
- 期望文件 (1): craft/loop.py
- BM25         : recall@10=0.0%  MRR=0.000  延迟=50.1 ms
- BM25+graph   : recall@10=100.0%  MRR=0.250  延迟=67.2 ms
- symbol-index : recall@10=100.0%  MRR=0.333  延迟=0.6 ms
- BM25 top-10: 1. · craft/__init__.py; 2. · cli/specproof/commands/craft.py
- +graph top-10: 1. · craft/__init__.py; 2. · craft/budget.py; 3. · cli/specproof/commands/craft.py; 4. ✔ craft/loop.py; 5. · craft/planner.py; 6. · craft/editor.py; 7. · craft/tools.py; 8. · craft/executor.py; 9. · craft/llm.py; 10. · craft/rules.py; … 共 50 条

### s04 · symbol · python

- 查询: compile_plan
- 期望文件 (1): craft/planner.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=51.9 ms
- BM25+graph   : recall@10=100.0%  MRR=0.200  延迟=84.3 ms
- symbol-index : recall@10=100.0%  MRR=0.333  延迟=0.9 ms
- BM25 top-10: 1. · craft/__init__.py; 2. ✔ craft/planner.py; 3. · cli/specproof/commands/craft.py
- +graph top-10: 1. · craft/__init__.py; 2. · craft/budget.py; 3. · cli/specproof/commands/craft.py; 4. · craft/loop.py; 5. ✔ craft/planner.py; 6. · craft/editor.py; 7. · craft/tools.py; 8. · craft/executor.py; 9. · craft/llm.py; 10. · craft/rules.py; … 共 56 条

### s05 · symbol · python

- 查询: deterministic_baseline
- 期望文件 (1): cli/specproof/commands/baseline.py
- BM25         : recall@10=0.0%  MRR=0.000  延迟=46.9 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=47.1 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.8 ms
- BM25 top-10: (无命中)
- +graph top-10: (无命中)

### s06 · symbol · python

- 查询: contract_results_for
- 期望文件 (1): agent/checkers/java_source.py
- BM25         : recall@10=100.0%  MRR=0.333  延迟=51.2 ms
- BM25+graph   : recall@10=0.0%  MRR=0.030  延迟=55.1 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=0.5 ms
- BM25 top-10: 1. · agent/checkers/__init__.py; 2. · agent/nodes/run_static_checks.py; 3. ✔ agent/checkers/java_source.py
- +graph top-10: 1. · agent/checkers/__init__.py; 2. · agent/nodes/run_static_checks.py; 3. · craft/verify.py; 4. · agent/fixes.py; 5. · agent/nodes/build_cache.py; 6. · agent/nodes/create_capsule.py; 7. · agent/nodes/generate_counterexamples.py; 8. · agent/nodes/intake.py; 9. · agent/nodes/prepare_base.py; 10. · agent/nodes/prepare_head.py; … 共 53 条

### s07 · symbol · java

- 查询: changeEmail
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java
- BM25         : recall@10=66.7%  MRR=1.000  延迟=52.4 ms
- BM25+graph   : recall@10=66.7%  MRR=1.000  延迟=54.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.7 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/repo_graph.py
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · craft/memory.py; 4. · craft/planner.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 55 条

### s08 · symbol · java

- 查询: placeOrder
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java, demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- BM25         : recall@10=66.7%  MRR=1.000  延迟=50.4 ms
- BM25+graph   : recall@10=66.7%  MRR=1.000  延迟=50.8 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.8 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 3. · craft/memory.py; 4. · craft/planner.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/CancelOrderRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/PlaceOrderRequest.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; … 共 13 条

### s09 · symbol · java

- 查询: EmailChangedEvent
- 期望文件 (2): demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/main/java/com/specproof/demo/event/EmailChangedEvent.java
- BM25         : recall@10=100.0%  MRR=1.000  延迟=46.9 ms
- BM25+graph   : recall@10=50.0%  MRR=1.000  延迟=47.3 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.9 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/event/EmailChangedEvent.java
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · craft/memory.py; 3. · craft/planner.py; 4. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 11 条

### s10 · symbol · java

- 查询: invalidateOldTokens
- 期望文件 (1): demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java
- BM25         : recall@10=100.0%  MRR=1.000  延迟=50.5 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=55.8 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.5 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · agent/checkers/constitution.py; 3. · agent/fixes.py
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · craft/memory.py; 3. · craft/planner.py; 4. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 59 条

### r01 · requirement · java

- 查询: 用户修改邮箱必须先认证(@PreAuthorize)并作废旧令牌(invalidateOldTokens)
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/main/java/com/specproof/demo/config/SecurityConfig.java
- BM25         : recall@10=66.7%  MRR=0.200  延迟=54.9 ms
- BM25+graph   : recall@10=0.0%  MRR=0.018  延迟=73.3 ms
- symbol-index : recall@10=66.7%  MRR=1.000  延迟=0.8 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/rules.py; 3. · craft/budget.py; 4. · craft/executor.py; 5. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 6. · cli/specproof/commands/craft.py; 7. · agent/checkers/constitution.py; 8. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 9. · craft/spec.py; 10. · agent/checkers/java_source.py; … 共 16 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/llm.py; 9. · agent/fixes.py; 10. · agent/nodes/create_capsule.py; … 共 64 条

### r02 · requirement · java

- 查询: 下单前校验库存(stock)下单后发布订单创建事件(OrderCreatedEvent)
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java, demo/spring-backend/src/main/java/com/specproof/demo/event/OrderCreatedEvent.java
- BM25         : recall@10=33.3%  MRR=0.500  延迟=47.1 ms
- BM25+graph   : recall@10=0.0%  MRR=0.018  延迟=66.9 ms
- symbol-index : recall@10=66.7%  MRR=1.000  延迟=1.1 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 3. · craft/rules.py; 4. · cli/specproof/commands/craft.py; 5. · craft/executor.py; 6. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 7. · craft/verify.py; 8. · craft/spec.py; 9. · agent/nodes/compile_contracts.py; 10. · agent/nodes/run_differential.py; … 共 11 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/llm.py; 9. · agent/fixes.py; 10. · agent/nodes/create_capsule.py; … 共 67 条

### r03 · requirement · java

- 查询: 用户邮箱必须唯一(unique, existsByEmail)
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java
- BM25         : recall@10=33.3%  MRR=0.333  延迟=46.7 ms
- BM25+graph   : recall@10=0.0%  MRR=0.018  延迟=76.1 ms
- symbol-index : recall@10=33.3%  MRR=0.333  延迟=0.7 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/budget.py; 3. ✔ demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java; 4. · cli/specproof/commands/craft.py; 5. · agent/checkers/constitution.py; 6. · craft/spec.py; 7. · craft/rules.py; 8. · agent/nodes/compile_contracts.py; 9. · agent/nodes/retrieve_repository_context.py; 10. · agent/fixes.py; … 共 13 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/llm.py; 9. · agent/fixes.py; 10. · agent/nodes/create_capsule.py; … 共 55 条

### r04 · requirement · python

- 查询: 构建 Phase0 状态图并发布报告(publish_report)
- 期望文件 (2): agent/graph.py, agent/nodes/publish_report.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=46.3 ms
- BM25+graph   : recall@10=0.0%  MRR=0.028  延迟=72.2 ms
- symbol-index : recall@10=50.0%  MRR=1.000  延迟=1.3 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ agent/graph.py; 3. · craft/rules.py; 4. ✔ agent/nodes/publish_report.py; 5. · cli/specproof/commands/craft.py
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/llm.py; 9. · agent/fixes.py; 10. · agent/nodes/create_capsule.py; … 共 54 条

### r05 · requirement · python

- 查询: 合并契约结果 FAIL 优先 PASS 次之 UNVERIFIED
- 期望文件 (3): agent/contract_results.py, agent/nodes/run_static_checks.py, agent/nodes/run_differential.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=52.1 ms
- BM25+graph   : recall@10=33.3%  MRR=1.000  延迟=81.3 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=1.6 ms
- BM25 top-10: 1. ✔ agent/contract_results.py; 2. · agent/nodes/build_matrix.py; 3. · cli/specproof/commands/baseline.py; 4. · agent/preflight.py; 5. · craft/rules.py; 6. ✔ agent/nodes/run_static_checks.py; 7. · agent/checkers/java_source.py; 8. ✔ agent/nodes/run_differential.py; 9. · agent/state.py; 10. · agent/contracts/compiler.py; … 共 14 条
- +graph top-10: 1. ✔ agent/contract_results.py; 2. · agent/checkers/constitution.py; 3. · agent/checkers/java_source.py; 4. · agent/checkers/schema_and_tests.py; 5. · agent/fixes.py; 6. · agent/mongo_saver.py; 7. · agent/nodes/build_matrix.py; 8. · agent/nodes/generate_counterexamples.py; 9. · agent/nodes/publish_report.py; 10. · agent/nodes/review_court.py; … 共 55 条

### r06 · requirement · python

- 查询: 执行器命令白名单(allowlist)并提取 pytest 失败测试
- 期望文件 (1): craft/executor.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=55.0 ms
- BM25+graph   : recall@10=0.0%  MRR=0.026  延迟=119.8 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.4 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ craft/executor.py; 3. · craft/rules.py; 4. · craft/spec.py; 5. · cli/specproof/commands/craft.py; 6. · craft/loop.py; 7. · craft/verify.py; 8. · craft/memory.py; 9. · craft/planner.py
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/llm.py; 9. · agent/fixes.py; 10. · agent/nodes/create_capsule.py; … 共 60 条

### r07 · requirement · python

- 查询: 编辑器原子写入(atomic write)备份与审计日志(audit)
- 期望文件 (1): craft/editor.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=48.2 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=145.8 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.9 ms
- BM25 top-10: 1. ✔ craft/editor.py; 2. · cli/specproof/commands/baseline.py; 3. · craft/rules.py; 4. · craft/verify.py; 5. · craft/tools.py; 6. · craft/loop.py; 7. · demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 8. · craft/schemas.py; 9. · cli/specproof/commands/contract.py; 10. · craft/memory.py; … 共 16 条
- +graph top-10: 1. ✔ craft/editor.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/create_capsule.py; 4. · agent/nodes/generate_counterexamples.py; 5. · agent/nodes/review_court.py; 6. · agent/nodes/run_differential.py; 7. · agent/nodes/run_release_checks.py; 8. · cli/specproof/commands/contract.py; 9. · cli/specproof/commands/verify.py; 10. · craft/rules.py; … 共 66 条

### r08 · requirement · python

- 查询: LLM 不可用时降级到确定性计划(deterministic fallback)
- 期望文件 (2): craft/planner.py, craft/llm.py
- BM25         : recall@10=100.0%  MRR=0.167  延迟=53.6 ms
- BM25+graph   : recall@10=50.0%  MRR=0.125  延迟=165.9 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=2.2 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/rules.py; 3. · cli/specproof/commands/craft.py; 4. · craft/schemas.py; 5. · craft/tools.py; 6. ✔ craft/planner.py; 7. · agent/nodes/generate_counterexamples.py; 8. ✔ craft/llm.py; 9. · craft/__init__.py; 10. · craft/editor.py; … 共 20 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. ✔ craft/llm.py; 9. · agent/fixes.py; 10. · agent/nodes/create_capsule.py; … 共 59 条

### r09 · requirement · python

- 查询: 安全扫描 canary 与密钥泄漏(secret leak)
- 期望文件 (1): agent/security_scanner.py
- BM25         : recall@10=100.0%  MRR=0.333  延迟=52.6 ms
- BM25+graph   : recall@10=0.0%  MRR=0.053  延迟=187.0 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=2.0 ms
- BM25 top-10: 1. · craft/rules.py; 2. · craft/verify.py; 3. ✔ agent/security_scanner.py; 4. · cli/specproof/commands/baseline.py; 5. · cli/specproof/commands/craft.py; 6. · craft/loop.py; 7. · craft/tools.py
- +graph top-10: 1. · craft/rules.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/create_capsule.py; 4. · agent/nodes/generate_counterexamples.py; 5. · agent/nodes/review_court.py; 6. · agent/nodes/run_differential.py; 7. · agent/nodes/run_release_checks.py; 8. · cli/specproof/commands/contract.py; 9. · cli/specproof/commands/verify.py; 10. · craft/editor.py; … 共 60 条

### r10 · requirement · python

- 查询: 预检 JDK(JAVA_HOME) Maven Wrapper(mvnw) 与 Docker
- 期望文件 (1): agent/preflight.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=48.3 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=109.9 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=3.6 ms
- BM25 top-10: 1. ✔ agent/preflight.py; 2. · cli/specproof/commands/fix.py; 3. · craft/rules.py; 4. · cli/specproof/commands/baseline.py; 5. · agent/security_scanner.py; 6. · agent/nodes/generate_counterexamples.py; 7. · craft/llm.py; 8. · craft/budget.py; 9. · agent/nodes/build_cache.py; 10. · craft/executor.py; … 共 11 条
- +graph top-10: 1. ✔ agent/preflight.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/build_cache.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/generate_counterexamples.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/worker.py; … 共 54 条

### e01 · error · python

- 查询: CommandNotAllowedError
- 期望文件 (2): craft/executor.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=53.9 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=120.4 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=0.8 ms
- BM25 top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/executor.py; 3. · craft/tools.py
- +graph top-10: 1. ✔ craft/__init__.py; 2. · craft/budget.py; 3. · cli/specproof/commands/craft.py; 4. · craft/loop.py; 5. · craft/planner.py; 6. · craft/editor.py; 7. · craft/tools.py; 8. ✔ craft/executor.py; 9. · craft/llm.py; 10. · craft/rules.py; … 共 58 条

### e02 · error · python

- 查询: STUCK
- 期望文件 (1): craft/loop.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=51.4 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=87.0 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=0.8 ms
- BM25 top-10: 1. ✔ craft/loop.py; 2. · craft/memory.py
- +graph top-10: 1. ✔ craft/loop.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/review_court.py; 7. · agent/nodes/run_deep_experiments.py; 8. · agent/nodes/run_differential.py; 9. · agent/nodes/run_release_checks.py; 10. · agent/worker.py; … 共 58 条

### e03 · error · python

- 查询: EditError
- 期望文件 (2): craft/editor.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=51.9 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=152.3 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.7 ms
- BM25 top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/editor.py; 3. · craft/tools.py; 4. · craft/loop.py
- +graph top-10: 1. ✔ craft/__init__.py; 2. · craft/budget.py; 3. · cli/specproof/commands/craft.py; 4. · craft/loop.py; 5. · craft/planner.py; 6. ✔ craft/editor.py; 7. · craft/tools.py; 8. · craft/executor.py; 9. · craft/llm.py; 10. · craft/rules.py; … 共 58 条

### e04 · error · python

- 查询: PlanTooComplexError
- 期望文件 (2): craft/planner.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=51.1 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=87.3 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.1 ms
- BM25 top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/planner.py
- +graph top-10: 1. ✔ craft/__init__.py; 2. · craft/budget.py; 3. · cli/specproof/commands/craft.py; 4. · craft/loop.py; 5. ✔ craft/planner.py; 6. · craft/editor.py; 7. · craft/tools.py; 8. · craft/executor.py; 9. · craft/llm.py; 10. · craft/rules.py; … 共 55 条

### e05 · error · python

- 查询: LLMUnavailableError
- 期望文件 (2): craft/llm.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=51.8 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=157.0 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.0 ms
- BM25 top-10: 1. ✔ craft/__init__.py; 2. · cli/specproof/commands/craft.py; 3. · craft/planner.py; 4. ✔ craft/llm.py; 5. · craft/loop.py
- +graph top-10: 1. ✔ craft/__init__.py; 2. · craft/budget.py; 3. · cli/specproof/commands/craft.py; 4. · craft/loop.py; 5. · craft/planner.py; 6. · craft/editor.py; 7. · craft/tools.py; 8. · craft/executor.py; 9. ✔ craft/llm.py; 10. · craft/rules.py; … 共 59 条

### e06 · error · python

- 查询: BudgetError
- 期望文件 (2): craft/budget.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=56.8 ms
- BM25+graph   : recall@10=50.0%  MRR=1.000  延迟=90.9 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.6 ms
- BM25 top-10: 1. ✔ craft/budget.py; 2. ✔ craft/__init__.py; 3. · cli/specproof/commands/craft.py
- +graph top-10: 1. ✔ craft/budget.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/build_cache.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/generate_counterexamples.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/preflight.py; … 共 50 条

### e07 · error · java

- 查询: Expected status 401 changeEmail unauthorized
- 期望文件 (2): demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java, demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java
- BM25         : recall@10=50.0%  MRR=0.143  延迟=54.2 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=89.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=2.0 ms
- BM25 top-10: 1. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 2. · craft/editor.py; 3. · agent/nodes/compile_contracts.py; 4. · agent/nodes/generate_counterexamples.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 6. · agent/contracts/registry.py; 7. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java; 8. · agent/contracts/compiler.py; 9. · agent/preflight.py; 10. · craft/verify.py; … 共 12 条
- +graph top-10: 1. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 2. · craft/memory.py; 3. · craft/planner.py; 4. · craft/tools.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/instrument/SqlQueryCounter.java; … 共 63 条

### e08 · error · java

- 查询: changeEmail duplicate email already registered
- 期望文件 (2): demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java
- BM25         : recall@10=100.0%  MRR=1.000  延迟=48.7 ms
- BM25+graph   : recall@10=50.0%  MRR=1.000  延迟=54.0 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=2.4 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/checkers/constitution.py; 4. · agent/nodes/compile_contracts.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 9. · agent/worker.py; 10. · agent/nodes/publish_report.py; … 共 12 条
- +graph top-10: 1. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java; 2. · agent/mongo_saver.py; 3. · craft/memory.py; 4. · craft/planner.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 63 条

### e09 · error · python

- 查询: 缺少 JAVA_HOME 或 Maven Wrapper(mvnw) 检查失败
- 期望文件 (1): agent/preflight.py
- BM25         : recall@10=100.0%  MRR=0.333  延迟=55.4 ms
- BM25+graph   : recall@10=0.0%  MRR=0.023  延迟=119.4 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=1.7 ms
- BM25 top-10: 1. · craft/rules.py; 2. · cli/specproof/commands/fix.py; 3. ✔ agent/preflight.py; 4. · cli/specproof/commands/baseline.py; 5. · craft/memory.py; 6. · craft/planner.py; 7. · craft/spec.py; 8. · agent/security_scanner.py; 9. · agent/nodes/generate_counterexamples.py; 10. · cli/specproof/commands/craft.py; … 共 13 条
- +graph top-10: 1. · craft/rules.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/create_capsule.py; 4. · agent/nodes/generate_counterexamples.py; 5. · agent/nodes/review_court.py; 6. · agent/nodes/run_differential.py; 7. · agent/nodes/run_release_checks.py; 8. · cli/specproof/commands/contract.py; 9. · cli/specproof/commands/verify.py; 10. · craft/editor.py; … 共 58 条

### e10 · error · java

- 查询: 库存不足(stock insufficient)时下单失败
- 期望文件 (2): demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java, demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- BM25         : recall@10=50.0%  MRR=0.333  延迟=55.4 ms
- BM25+graph   : recall@10=0.0%  MRR=0.018  延迟=79.1 ms
- symbol-index : recall@10=50.0%  MRR=1.000  延迟=2.5 ms
- BM25 top-10: 1. · craft/rules.py; 2. · cli/specproof/commands/baseline.py; 3. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 4. · cli/specproof/commands/craft.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 6. · agent/nodes/compile_contracts.py; 7. · craft/executor.py; 8. · craft/planner.py; 9. · agent/nodes/run_differential.py; 10. · craft/schemas.py; … 共 14 条
- +graph top-10: 1. · craft/rules.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/create_capsule.py; 4. · agent/nodes/generate_counterexamples.py; 5. · agent/nodes/review_court.py; 6. · agent/nodes/run_differential.py; 7. · agent/nodes/run_release_checks.py; 8. · cli/specproof/commands/contract.py; 9. · cli/specproof/commands/verify.py; 10. · craft/editor.py; … 共 66 条

## 诚实性说明

1. 本基线的数字只覆盖 BM25 与图谱扩展; 向量/RRF 融合/重排 (卷IV 4.2, retrieval/hybrid.py 已实现) 留作后续消融, 不并入本次汇总。
2. ES standard 分析器不做中文分词: 中文需求/错误查询依赖内嵌技术 token (符号名/错误串) 命中; 纯中文检索不在本基线范围。
3. Python 文件在 ES 中按整文件成块 (symbol=path, storage.elasticsearch._chunk_files 现有行为, 未改动); Java 按方法分块。
3a. 已知截断: _chunk_files 把块内容截到 4000 字符, 大文件后半部分的符号 不进 ES (实测 s05 deterministic_baseline / s03 CraftLoop 因此 BM25 零命中, symbol-index 列 100% 找回 — 这正是符号索引的用途)。
3b. specproof-code-phase0 是共享索引, 并行的其他车道会重索引各自的 repo 快照; 本基准 repo 名 (specproof-retrieval-bench) 与其他车道隔离, 每次运行 开头幂等重建自己的文档。
4. Java 图谱扩展使用 retrieval/symbols.py 的等价切分 (与 agent/repo_graph.py 同风格); TS/Go 为保守正则, 符号标 conservative; 本基准语料不含 TS/Go 文件 (解析器由单测覆盖)。
5. --offline 数字仅供 CI 冒烟, 不代表真实 ES 基线。
6. 延迟为本机 Docker ES 单次测量 (30 查询平均), 未做多轮取均值。

## 复现

    python scripts/bench_retrieval.py  # 真实 ES, 写 docs/eval/retrieval-bench.md
    python scripts/bench_retrieval.py --offline  # mock BM25 (CI)
    python -m pytest tests/unit/test_symbols_index.py -v
