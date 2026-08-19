# 检索基准实测报告 — 30 查询黄金集 (M2 / §22-5)

- 生成时间: 2026-08-19 14:50:24 +0800
- 基线: BM25 (真实 Elasticsearch localhost:9200 · index specproof-code-phase0) + 图谱扩展 (开, top-8×1 跳)
- 语料: cli/ + agent/ + craft/ (Python) + demo/spring-backend (Java) · repo=specproof-retrieval-bench · commit_sha=bench-m2

## 方法

- 30 条黄金查询 (10 符号名 / 10 需求句 / 10 错误信息), 每条固定期望文件集; 期望集以「定义或直接佐证该查询行为」为准, 2026-08-18 按语料 grep 核验, 未按任何检索系统调参。
- 指标: recall@10 (期望文件在前 10 条去重路径中的占比) / MRR (首个期望文件排名倒数) / 平均延迟 (search+expand 墙钟, 30 查询平均)。
- 对比系统: BM25 (storage.elasticsearch.search_code, 现有实现只读复用) → BM25+图谱 (retrieval.symbols.SymbolIndex.expand_hits, 与 agent.repo_graph 同风格) → symbol-index (符号名/引用确定性查表, 附加列)。

## 索引统计

- 文件: scanned=93 · ok=93 · failed=0
- 符号: 2022 · 按语言: java=349, python=1673
- 符号按 kind: assign=258, class=121, function=333, import=908, method=402
- 边: calls=5968 · refs=8687

## 汇总 (n=30)

| 系统 | recall@10 | MRR | 平均延迟 | 全命中查询数 |
|---|---:|---:|---:|---:|
| BM25 | 72.2% | 0.561 | 72.3 ms | 19/30 |
| BM25+graph | 38.9% | 0.424 | 152.8 ms | 8/30 |
| symbol-index | 75.6% | 0.683 | 2.3 ms | 20/30 |
| BM25+RRF | 87.2% | 0.760 | 74.6 ms | 23/30 |
| BM25+RRF+graph | 87.2% | 0.760 | 126.6 ms | 23/30 |

### 按查询类型 (BM25+graph)

| 类型 | n | recall@10 | MRR | 平均延迟 |
|---|---:|---:|---:|---:|
| symbol | 10 | 58.3% | 0.536 | 86.5 ms |
| requirement | 10 | 18.3% | 0.230 | 198.5 ms |
| error | 10 | 40.0% | 0.505 | 173.4 ms |

### 按查询类型 (BM25+RRF+graph)

| 类型 | n | recall@10 | MRR | 平均延迟 |
|---|---:|---:|---:|---:|
| symbol | 10 | 100.0% | 0.817 | 92.1 ms |
| requirement | 10 | 76.7% | 0.712 | 117.1 ms |
| error | 10 | 85.0% | 0.750 | 170.5 ms |

## 每查询明细

### s01 · symbol · python

- 查询: RepoGraph
- 期望文件 (1): agent/repo_graph.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=101.8 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=104.3 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.4 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=103.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=112.2 ms
- BM25 top-10: 1. ✔ agent/repo_graph.py
- +graph top-10: 1. ✔ agent/repo_graph.py; 2. · agent/checkers/java_source.py; 3. · agent/checkers/schema_and_tests.py; 4. · agent/contracts/compiler.py; 5. · agent/contracts/parser.py; 6. · agent/fixes.py; 7. · agent/nodes/build_cache.py; 8. · agent/nodes/collect_diff.py; 9. · agent/nodes/compile_contracts.py; 10. · agent/nodes/generate_counterexamples.py; … 共 53 条
- RRF top-10: 1. ✔ agent/repo_graph.py; 2. · agent/nodes/retrieve_repository_context.py; 3. · craft/tools.py
- RRF+graph top-10: 1. ✔ agent/repo_graph.py; 2. · agent/nodes/retrieve_repository_context.py; 3. · craft/tools.py

### s02 · symbol · python

- 查询: MongoDBSaver
- 期望文件 (1): agent/mongo_saver.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=30.2 ms
- BM25+graph   : recall@10=0.0%  MRR=0.024  延迟=56.3 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.2 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=31.4 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=70.2 ms
- BM25 top-10: 1. · agent/worker.py; 2. ✔ agent/mongo_saver.py
- +graph top-10: 1. · agent/worker.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/contracts/records.py; 5. · agent/nodes/compile_contracts.py; 6. · agent/nodes/create_capsule.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/nodes/run_release_checks.py; … 共 62 条
- RRF top-10: 1. ✔ agent/mongo_saver.py; 2. · agent/worker.py
- RRF+graph top-10: 1. ✔ agent/mongo_saver.py; 2. · agent/worker.py; 3. · agent/checkers/constitution.py; 4. · agent/checkers/java_source.py; 5. · agent/checkers/schema_and_tests.py; 6. · agent/contract_results.py; 7. · agent/contracts/parser.py; 8. · agent/contracts/records.py; 9. · agent/contracts/registry.py; 10. · agent/contracts/storage.py; … 共 12 条

### s03 · symbol · python

- 查询: CraftLoop
- 期望文件 (1): craft/loop.py
- BM25         : recall@10=0.0%  MRR=0.000  延迟=78.4 ms
- BM25+graph   : recall@10=100.0%  MRR=0.167  延迟=161.9 ms
- symbol-index : recall@10=100.0%  MRR=0.333  延迟=1.4 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.333  延迟=79.8 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.333  延迟=158.4 ms
- BM25 top-10: 1. · craft/__init__.py; 2. · cli/specproof/commands/craft.py
- +graph top-10: 1. · craft/__init__.py; 2. · craft/accept.py; 3. · cli/specproof/commands/craft.py; 4. · craft/agents.py; 5. · craft/budget.py; 6. ✔ craft/loop.py; 7. · craft/planner.py; 8. · craft/context.py; 9. · craft/editor.py; 10. · craft/tools.py; … 共 60 条
- RRF top-10: 1. · cli/specproof/commands/craft.py; 2. · craft/__init__.py; 3. ✔ craft/loop.py
- RRF+graph top-10: 1. · cli/specproof/commands/craft.py; 2. · craft/__init__.py; 3. ✔ craft/loop.py

### s04 · symbol · python

- 查询: compile_plan
- 期望文件 (1): craft/planner.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=57.9 ms
- BM25+graph   : recall@10=100.0%  MRR=0.143  延迟=170.7 ms
- symbol-index : recall@10=100.0%  MRR=0.333  延迟=1.2 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.333  延迟=59.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.333  延迟=193.4 ms
- BM25 top-10: 1. · craft/__init__.py; 2. ✔ craft/planner.py; 3. · cli/specproof/commands/craft.py
- +graph top-10: 1. · craft/__init__.py; 2. · craft/accept.py; 3. · cli/specproof/commands/craft.py; 4. · craft/agents.py; 5. · craft/budget.py; 6. · craft/loop.py; 7. ✔ craft/planner.py; 8. · craft/context.py; 9. · craft/editor.py; 10. · craft/tools.py; … 共 65 条
- RRF top-10: 1. · cli/specproof/commands/craft.py; 2. · craft/__init__.py; 3. ✔ craft/planner.py
- RRF+graph top-10: 1. · cli/specproof/commands/craft.py; 2. · craft/__init__.py; 3. ✔ craft/planner.py

### s05 · symbol · python

- 查询: deterministic_baseline
- 期望文件 (1): cli/specproof/commands/baseline.py
- BM25         : recall@10=0.0%  MRR=0.000  延迟=56.9 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=57.1 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.2 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=58.1 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=61.1 ms
- BM25 top-10: (无命中)
- +graph top-10: (无命中)
- RRF top-10: 1. ✔ cli/specproof/commands/baseline.py
- RRF+graph top-10: 1. ✔ cli/specproof/commands/baseline.py; 2. · agent/checkers/constitution.py; 3. · agent/checkers/java_source.py; 4. · agent/checkers/schema_and_tests.py; 5. · agent/contract_results.py; 6. · agent/contracts/parser.py; 7. · agent/contracts/records.py; 8. · agent/contracts/registry.py; 9. · agent/contracts/storage.py; 10. · agent/fixes.py; … 共 11 条

### s06 · symbol · python

- 查询: contract_results_for
- 期望文件 (1): agent/checkers/java_source.py
- BM25         : recall@10=100.0%  MRR=0.333  延迟=51.5 ms
- BM25+graph   : recall@10=0.0%  MRR=0.028  延迟=63.5 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.1 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.500  延迟=52.7 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.500  延迟=67.1 ms
- BM25 top-10: 1. · agent/checkers/__init__.py; 2. · agent/nodes/run_static_checks.py; 3. ✔ agent/checkers/java_source.py
- +graph top-10: 1. · agent/checkers/__init__.py; 2. · agent/nodes/run_static_checks.py; 3. · craft/verify.py; 4. · agent/fixes.py; 5. · agent/nodes/build_cache.py; 6. · agent/nodes/create_capsule.py; 7. · agent/nodes/generate_counterexamples.py; 8. · agent/nodes/intake.py; 9. · agent/nodes/prepare_base.py; 10. · agent/nodes/prepare_head.py; … 共 60 条
- RRF top-10: 1. · agent/checkers/__init__.py; 2. ✔ agent/checkers/java_source.py; 3. · agent/nodes/run_static_checks.py
- RRF+graph top-10: 1. · agent/checkers/__init__.py; 2. ✔ agent/checkers/java_source.py; 3. · agent/nodes/run_static_checks.py; 4. · craft/verify.py; 5. · agent/checkers/constitution.py

### s07 · symbol · java

- 查询: changeEmail
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java
- BM25         : recall@10=66.7%  MRR=1.000  延迟=57.5 ms
- BM25+graph   : recall@10=66.7%  MRR=1.000  延迟=63.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.8 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=59.3 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=63.2 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/repo_graph.py
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · craft/memory.py; 4. · craft/planner.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 62 条
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/repo_graph.py; 4. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/repo_graph.py; 4. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java

### s08 · symbol · java

- 查询: placeOrder
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java, demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- BM25         : recall@10=66.7%  MRR=1.000  延迟=55.0 ms
- BM25+graph   : recall@10=66.7%  MRR=1.000  延迟=55.5 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.2 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=56.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=57.3 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 3. · craft/memory.py; 4. · craft/planner.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/CancelOrderRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/PlaceOrderRequest.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; … 共 13 条
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 3. ✔ demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 3. ✔ demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java

### s09 · symbol · java

- 查询: EmailChangedEvent
- 期望文件 (2): demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/main/java/com/specproof/demo/event/EmailChangedEvent.java
- BM25         : recall@10=100.0%  MRR=1.000  延迟=58.7 ms
- BM25+graph   : recall@10=50.0%  MRR=1.000  延迟=59.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.2 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=59.9 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=60.5 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/event/EmailChangedEvent.java
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · craft/memory.py; 3. · craft/planner.py; 4. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 11 条
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/event/EmailChangedEvent.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/event/EmailChangedEvent.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java

### s10 · symbol · java

- 查询: invalidateOldTokens
- 期望文件 (1): demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java
- BM25         : recall@10=100.0%  MRR=1.000  延迟=57.6 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=72.9 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.4 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=59.0 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=77.7 ms
- BM25 top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · agent/checkers/constitution.py; 3. · agent/fixes.py
- +graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · craft/memory.py; 3. · craft/planner.py; 4. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 5. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 10. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java; … 共 66 条
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · agent/checkers/constitution.py; 3. · agent/fixes.py
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · agent/checkers/constitution.py; 3. · agent/fixes.py; 4. · craft/memory.py; 5. · craft/planner.py; 6. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/dto/ChangeEmailRequest.java; 8. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 9. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java

### r01 · requirement · java

- 查询: 用户修改邮箱必须先认证(@PreAuthorize)并作废旧令牌(invalidateOldTokens)
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/main/java/com/specproof/demo/config/SecurityConfig.java
- BM25         : recall@10=66.7%  MRR=0.200  延迟=80.4 ms
- BM25+graph   : recall@10=0.0%  MRR=0.016  延迟=139.5 ms
- symbol-index : recall@10=66.7%  MRR=1.000  延迟=2.0 ms
- BM25+RRF     : recall@10=66.7%  MRR=1.000  延迟=82.4 ms
- BM25+RRF+graph: recall@10=66.7%  MRR=1.000  延迟=121.8 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/rules.py; 3. · craft/budget.py; 4. · craft/executor.py; 5. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 6. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 7. · agent/checkers/constitution.py; 8. · craft/spec.py; 9. · craft/agents.py; 10. · agent/checkers/java_source.py; … 共 16 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. · craft/llm.py; 10. · agent/fixes.py; … 共 71 条
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · cli/specproof/commands/baseline.py; 3. · craft/rules.py; 4. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 5. · craft/budget.py; 6. · craft/executor.py; 7. · agent/checkers/constitution.py; 8. · craft/spec.py; 9. · craft/agents.py; 10. · agent/checkers/java_source.py; … 共 16 条
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 2. · cli/specproof/commands/baseline.py; 3. · craft/rules.py; 4. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 5. · craft/budget.py; 6. · craft/executor.py; 7. · agent/checkers/constitution.py; 8. · craft/spec.py; 9. · craft/agents.py; 10. · agent/checkers/java_source.py; … 共 22 条

### r02 · requirement · java

- 查询: 下单前校验库存(stock)下单后发布订单创建事件(OrderCreatedEvent)
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/controller/OrderController.java, demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java, demo/spring-backend/src/main/java/com/specproof/demo/event/OrderCreatedEvent.java
- BM25         : recall@10=33.3%  MRR=0.500  延迟=62.8 ms
- BM25+graph   : recall@10=0.0%  MRR=0.016  延迟=124.1 ms
- symbol-index : recall@10=66.7%  MRR=1.000  延迟=1.7 ms
- BM25+RRF     : recall@10=66.7%  MRR=1.000  延迟=64.6 ms
- BM25+RRF+graph: recall@10=66.7%  MRR=1.000  延迟=103.4 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 3. · craft/rules.py; 4. · craft/executor.py; 5. · craft/verify.py; 6. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 7. · craft/spec.py; 8. · agent/nodes/compile_contracts.py; 9. · agent/nodes/run_differential.py; 10. · craft/schemas.py; … 共 11 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. · craft/llm.py; 10. · agent/fixes.py; … 共 75 条
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 2. · cli/specproof/commands/baseline.py; 3. ✔ demo/spring-backend/src/main/java/com/specproof/demo/event/OrderCreatedEvent.java; 4. · craft/rules.py; 5. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 6. · craft/executor.py; 7. · craft/verify.py; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 9. · craft/spec.py; 10. · agent/nodes/compile_contracts.py; … 共 13 条
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java; 2. · cli/specproof/commands/baseline.py; 3. ✔ demo/spring-backend/src/main/java/com/specproof/demo/event/OrderCreatedEvent.java; 4. · craft/rules.py; 5. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 6. · craft/executor.py; 7. · craft/verify.py; 8. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 9. · craft/spec.py; 10. · agent/nodes/compile_contracts.py; … 共 19 条

### r03 · requirement · java

- 查询: 用户邮箱必须唯一(unique, existsByEmail)
- 期望文件 (3): demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java, demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java
- BM25         : recall@10=33.3%  MRR=0.333  延迟=64.6 ms
- BM25+graph   : recall@10=0.0%  MRR=0.016  延迟=174.1 ms
- symbol-index : recall@10=33.3%  MRR=0.333  延迟=4.8 ms
- BM25+RRF     : recall@10=66.7%  MRR=0.200  延迟=69.5 ms
- BM25+RRF+graph: recall@10=66.7%  MRR=0.200  延迟=92.2 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/budget.py; 3. ✔ demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java; 4. · agent/checkers/constitution.py; 5. · craft/spec.py; 6. · craft/rules.py; 7. · craft/agents.py; 8. · agent/nodes/compile_contracts.py; 9. · agent/nodes/retrieve_repository_context.py; 10. · agent/fixes.py; … 共 13 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. · craft/llm.py; 10. · agent/fixes.py; … 共 63 条
- RRF top-10: 1. · agent/checkers/java_source.py; 2. · cli/specproof/commands/baseline.py; 3. · agent/nodes/generate_counterexamples.py; 4. · craft/budget.py; 5. ✔ demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java; 6. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 7. · agent/checkers/constitution.py; 8. · craft/spec.py; 9. · craft/rules.py; 10. · craft/agents.py; … 共 16 条
- RRF+graph top-10: 1. · agent/checkers/java_source.py; 2. · cli/specproof/commands/baseline.py; 3. · agent/nodes/generate_counterexamples.py; 4. · craft/budget.py; 5. ✔ demo/spring-backend/src/main/java/com/specproof/demo/repository/UserRepository.java; 6. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 7. · agent/checkers/constitution.py; 8. · craft/spec.py; 9. · craft/rules.py; 10. · craft/agents.py; … 共 16 条

### r04 · requirement · python

- 查询: 构建 Phase0 状态图并发布报告(publish_report)
- 期望文件 (2): agent/graph.py, agent/nodes/publish_report.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=61.9 ms
- BM25+graph   : recall@10=0.0%  MRR=0.025  延迟=103.7 ms
- symbol-index : recall@10=50.0%  MRR=1.000  延迟=1.6 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=63.6 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=105.3 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ agent/graph.py; 3. · craft/rules.py; 4. ✔ agent/nodes/publish_report.py; 5. · craft/agents.py
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. · craft/llm.py; 10. · agent/fixes.py; … 共 62 条
- RRF top-10: 1. ✔ agent/graph.py; 2. · cli/specproof/commands/baseline.py; 3. · agent/nodes/build_cache.py; 4. · craft/rules.py; 5. · agent/nodes/build_matrix.py; 6. ✔ agent/nodes/publish_report.py; 7. · agent/nodes/collect_diff.py; 8. · craft/agents.py; 9. · agent/nodes/compile_contracts.py; 10. · agent/nodes/create_capsule.py; … 共 13 条
- RRF+graph top-10: 1. ✔ agent/graph.py; 2. · cli/specproof/commands/baseline.py; 3. · agent/nodes/build_cache.py; 4. · craft/rules.py; 5. · agent/nodes/build_matrix.py; 6. ✔ agent/nodes/publish_report.py; 7. · agent/nodes/collect_diff.py; 8. · craft/agents.py; 9. · agent/nodes/compile_contracts.py; 10. · agent/nodes/create_capsule.py; … 共 13 条

### r05 · requirement · python

- 查询: 合并契约结果 FAIL 优先 PASS 次之 UNVERIFIED
- 期望文件 (3): agent/contract_results.py, agent/nodes/run_static_checks.py, agent/nodes/run_differential.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=139.8 ms
- BM25+graph   : recall@10=33.3%  MRR=1.000  延迟=207.4 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=2.3 ms
- BM25+RRF     : recall@10=66.7%  MRR=1.000  延迟=142.3 ms
- BM25+RRF+graph: recall@10=66.7%  MRR=1.000  延迟=199.7 ms
- BM25 top-10: 1. ✔ agent/contract_results.py; 2. · agent/nodes/build_matrix.py; 3. · cli/specproof/commands/baseline.py; 4. · agent/preflight.py; 5. · craft/gates.py; 6. · craft/rules.py; 7. ✔ agent/nodes/run_static_checks.py; 8. · agent/checkers/java_source.py; 9. ✔ agent/nodes/run_differential.py; 10. · craft/agents.py; … 共 18 条
- +graph top-10: 1. ✔ agent/contract_results.py; 2. · agent/checkers/constitution.py; 3. · agent/checkers/java_source.py; 4. · agent/checkers/schema_and_tests.py; 5. · agent/contracts/registry.py; 6. · agent/contracts/storage.py; 7. · agent/fixes.py; 8. · agent/mongo_saver.py; 9. · agent/nodes/build_matrix.py; 10. · agent/nodes/generate_counterexamples.py; … 共 63 条
- RRF top-10: 1. ✔ agent/contract_results.py; 2. · agent/review_court/policy.py; 3. · agent/nodes/build_matrix.py; 4. · craft/executor.py; 5. · cli/specproof/commands/baseline.py; 6. · craft/tools.py; 7. · agent/preflight.py; 8. · craft/gates.py; 9. · craft/rules.py; 10. ✔ agent/nodes/run_static_checks.py; … 共 21 条
- RRF+graph top-10: 1. ✔ agent/contract_results.py; 2. · agent/review_court/policy.py; 3. · agent/nodes/build_matrix.py; 4. · craft/executor.py; 5. · cli/specproof/commands/baseline.py; 6. · craft/tools.py; 7. · agent/preflight.py; 8. · craft/gates.py; 9. · craft/rules.py; 10. ✔ agent/nodes/run_static_checks.py; … 共 22 条

### r06 · requirement · python

- 查询: 执行器命令白名单(allowlist)并提取 pytest 失败测试
- 期望文件 (1): craft/executor.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=32.5 ms
- BM25+graph   : recall@10=0.0%  MRR=0.023  延迟=156.7 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.6 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.333  延迟=34.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.333  延迟=72.6 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ craft/executor.py; 3. · craft/rules.py; 4. · craft/agents.py; 5. · craft/spec.py; 6. · craft/verify.py; 7. · craft/memory.py; 8. · craft/planner.py; 9. · craft/loop.py
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. · craft/llm.py; 10. · agent/fixes.py; … 共 67 条
- RRF top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/__init__.py; 3. ✔ craft/executor.py; 4. · craft/rules.py; 5. · craft/agents.py; 6. · craft/loop.py; 7. · craft/spec.py; 8. · craft/verify.py; 9. · craft/memory.py; 10. · craft/planner.py
- RRF+graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/__init__.py; 3. ✔ craft/executor.py; 4. · craft/rules.py; 5. · craft/agents.py; 6. · craft/loop.py; 7. · craft/spec.py; 8. · craft/verify.py; 9. · craft/memory.py; 10. · craft/planner.py; … 共 11 条

### r07 · requirement · python

- 查询: 编辑器原子写入(atomic write)备份与审计日志(audit)
- 期望文件 (1): craft/editor.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=59.6 ms
- BM25+graph   : recall@10=0.0%  MRR=0.043  延迟=248.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=2.2 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.500  延迟=61.9 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.500  延迟=104.7 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ craft/editor.py; 3. · craft/rules.py; 4. · craft/verify.py; 5. · craft/tools.py; 6. · craft/loop.py; 7. · demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 8. · craft/agents.py; 9. · agent/contracts/records.py; 10. · agent/state.py; … 共 20 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. · craft/llm.py; 10. · agent/fixes.py; … 共 73 条
- RRF top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ craft/editor.py; 3. · craft/planner.py; 4. · cli/specproof/commands/craft.py; 5. · craft/rules.py; 6. · craft/loop.py; 7. · craft/verify.py; 8. · craft/tools.py; 9. · agent/mongo_saver.py; 10. · demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; … 共 23 条
- RRF+graph top-10: 1. · cli/specproof/commands/baseline.py; 2. ✔ craft/editor.py; 3. · craft/planner.py; 4. · cli/specproof/commands/craft.py; 5. · craft/rules.py; 6. · craft/loop.py; 7. · craft/verify.py; 8. · craft/tools.py; 9. · agent/mongo_saver.py; 10. · demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; … 共 24 条

### r08 · requirement · python

- 查询: LLM 不可用时降级到确定性计划(deterministic fallback)
- 期望文件 (2): craft/planner.py, craft/llm.py
- BM25         : recall@10=100.0%  MRR=0.143  延迟=59.5 ms
- BM25+graph   : recall@10=50.0%  MRR=0.111  延迟=284.1 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=2.0 ms
- BM25+RRF     : recall@10=0.0%  MRR=0.091  延迟=61.6 ms
- BM25+RRF+graph: recall@10=0.0%  MRR=0.091  延迟=123.4 ms
- BM25 top-10: 1. · cli/specproof/commands/baseline.py; 2. · craft/rules.py; 3. · cli/specproof/commands/craft.py; 4. · craft/schemas.py; 5. · craft/tools.py; 6. · craft/context.py; 7. ✔ craft/planner.py; 8. · agent/nodes/generate_counterexamples.py; 9. ✔ craft/llm.py; 10. · craft/gates.py; … 共 20 条
- +graph top-10: 1. · cli/specproof/commands/baseline.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/review_court.py; 7. · cli/specproof/commands/probe.py; 8. · craft/agents.py; 9. ✔ craft/llm.py; 10. · agent/fixes.py; … 共 66 条
- RRF top-10: 1. · agent/contracts/parser.py; 2. · cli/specproof/commands/baseline.py; 3. · craft/rules.py; 4. · agent/nodes/compile_contracts.py; 5. · cli/specproof/commands/craft.py; 6. · agent/nodes/generate_counterexamples.py; 7. · craft/schemas.py; 8. · agent/nodes/review_court.py; 9. · craft/tools.py; 10. · craft/context.py; … 共 22 条
- RRF+graph top-10: 1. · agent/contracts/parser.py; 2. · cli/specproof/commands/baseline.py; 3. · craft/rules.py; 4. · agent/nodes/compile_contracts.py; 5. · cli/specproof/commands/craft.py; 6. · agent/nodes/generate_counterexamples.py; 7. · craft/schemas.py; 8. · agent/nodes/review_court.py; 9. · craft/tools.py; 10. · craft/context.py; … 共 22 条

### r09 · requirement · python

- 查询: 安全扫描 canary 与密钥泄漏(secret leak)
- 期望文件 (1): agent/security_scanner.py
- BM25         : recall@10=100.0%  MRR=0.333  延迟=53.8 ms
- BM25+graph   : recall@10=0.0%  MRR=0.050  延迟=346.1 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=2.3 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=56.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=92.6 ms
- BM25 top-10: 1. · craft/rules.py; 2. · craft/verify.py; 3. ✔ agent/security_scanner.py; 4. · cli/specproof/commands/baseline.py; 5. · cli/specproof/commands/craft.py; 6. · craft/loop.py; 7. · craft/tools.py; 8. · craft/gates.py
- +graph top-10: 1. · craft/rules.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/records.py; 4. · agent/nodes/create_capsule.py; 5. · agent/nodes/generate_counterexamples.py; 6. · agent/nodes/run_differential.py; 7. · agent/nodes/run_release_checks.py; 8. · agent/review_court/policy.py; 9. · cli/specproof/commands/contract.py; 10. · cli/specproof/commands/verify.py; … 共 67 条
- RRF top-10: 1. ✔ agent/security_scanner.py; 2. · craft/rules.py; 3. · craft/editor.py; 4. · craft/verify.py; 5. · craft/loop.py; 6. · cli/specproof/commands/baseline.py; 7. · craft/memory.py; 8. · cli/specproof/commands/craft.py; 9. · craft/tools.py; 10. · craft/gates.py
- RRF+graph top-10: 1. ✔ agent/security_scanner.py; 2. · craft/rules.py; 3. · craft/editor.py; 4. · craft/verify.py; 5. · craft/loop.py; 6. · cli/specproof/commands/baseline.py; 7. · craft/memory.py; 8. · cli/specproof/commands/craft.py; 9. · craft/tools.py; 10. · craft/gates.py; … 共 20 条

### r10 · requirement · python

- 查询: 预检 JDK(JAVA_HOME) Maven Wrapper(mvnw) 与 Docker
- 期望文件 (1): agent/preflight.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=61.9 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=200.9 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=8.8 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=70.8 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=155.5 ms
- BM25 top-10: 1. ✔ agent/preflight.py; 2. · cli/specproof/commands/fix.py; 3. · craft/rules.py; 4. · cli/specproof/commands/baseline.py; 5. · agent/security_scanner.py; 6. · agent/nodes/generate_counterexamples.py; 7. · craft/llm.py; 8. · craft/budget.py; 9. · agent/nodes/build_cache.py; 10. · agent/contracts/registry.py; … 共 16 条
- +graph top-10: 1. ✔ agent/preflight.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/build_cache.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/generate_counterexamples.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/worker.py; … 共 61 条
- RRF top-10: 1. ✔ agent/preflight.py; 2. · cli/specproof/commands/fix.py; 3. · craft/rules.py; 4. · cli/specproof/commands/baseline.py; 5. · agent/security_scanner.py; 6. · agent/nodes/generate_counterexamples.py; 7. · craft/llm.py; 8. · craft/budget.py; 9. · agent/nodes/build_cache.py; 10. · agent/contracts/registry.py; … 共 16 条
- RRF+graph top-10: 1. ✔ agent/preflight.py; 2. · cli/specproof/commands/fix.py; 3. · craft/rules.py; 4. · cli/specproof/commands/baseline.py; 5. · agent/security_scanner.py; 6. · agent/nodes/generate_counterexamples.py; 7. · craft/llm.py; 8. · craft/budget.py; 9. · agent/nodes/build_cache.py; 10. · agent/contracts/registry.py; … 共 17 条

### e01 · error · python

- 查询: CommandNotAllowedError
- 期望文件 (2): craft/executor.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=57.6 ms
- BM25+graph   : recall@10=50.0%  MRR=1.000  延迟=291.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.6 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=59.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=241.4 ms
- BM25 top-10: 1. ✔ craft/executor.py; 2. ✔ craft/__init__.py; 3. · craft/tools.py
- +graph top-10: 1. ✔ craft/executor.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/build_cache.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/generate_counterexamples.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/preflight.py; … 共 65 条
- RRF top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/executor.py; 3. · craft/tools.py
- RRF+graph top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/executor.py; 3. · craft/tools.py

### e02 · error · python

- 查询: STUCK
- 期望文件 (1): craft/loop.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=58.7 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=142.1 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=1.8 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=60.6 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=138.7 ms
- BM25 top-10: 1. ✔ craft/loop.py; 2. · craft/memory.py
- +graph top-10: 1. ✔ craft/loop.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/parser.py; 4. · agent/contracts/records.py; 5. · agent/nodes/compile_contracts.py; 6. · agent/nodes/create_capsule.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/nodes/run_release_checks.py; … 共 65 条
- RRF top-10: 1. ✔ craft/loop.py; 2. · craft/memory.py
- RRF+graph top-10: 1. ✔ craft/loop.py; 2. · craft/memory.py; 3. · agent/checkers/java_source.py

### e03 · error · python

- 查询: EditError
- 期望文件 (2): craft/editor.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=58.4 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=246.2 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=1.7 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=60.2 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=209.7 ms
- BM25 top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/editor.py; 3. · craft/tools.py
- +graph top-10: 1. ✔ craft/__init__.py; 2. · craft/accept.py; 3. · cli/specproof/commands/craft.py; 4. · craft/agents.py; 5. · craft/budget.py; 6. · craft/loop.py; 7. · craft/planner.py; 8. · craft/context.py; 9. ✔ craft/editor.py; 10. · craft/tools.py; … 共 64 条
- RRF top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/editor.py; 3. · craft/loop.py; 4. · craft/tools.py
- RRF+graph top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/editor.py; 3. · craft/loop.py; 4. · craft/tools.py

### e04 · error · python

- 查询: PlanTooComplexError
- 期望文件 (2): craft/planner.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=53.6 ms
- BM25+graph   : recall@10=100.0%  MRR=1.000  延迟=166.7 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=3.6 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=57.3 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=181.0 ms
- BM25 top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/planner.py
- +graph top-10: 1. ✔ craft/__init__.py; 2. · craft/accept.py; 3. · cli/specproof/commands/craft.py; 4. · craft/agents.py; 5. · craft/budget.py; 6. · craft/loop.py; 7. ✔ craft/planner.py; 8. · craft/context.py; 9. · craft/editor.py; 10. · craft/tools.py; … 共 63 条
- RRF top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/planner.py
- RRF+graph top-10: 1. ✔ craft/__init__.py; 2. ✔ craft/planner.py

### e05 · error · python

- 查询: LLMUnavailableError
- 期望文件 (2): craft/llm.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=0.500  延迟=61.3 ms
- BM25+graph   : recall@10=0.0%  MRR=0.050  延迟=208.7 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.5 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.500  延迟=62.9 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.500  延迟=223.7 ms
- BM25 top-10: 1. · cli/specproof/commands/craft.py; 2. ✔ craft/__init__.py; 3. · craft/planner.py; 4. ✔ craft/llm.py
- +graph top-10: 1. · cli/specproof/commands/craft.py; 2. · agent/checkers/java_source.py; 3. · agent/contracts/records.py; 4. · agent/contracts/parser.py; 5. · agent/nodes/compile_contracts.py; 6. · agent/nodes/create_capsule.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/nodes/run_release_checks.py; … 共 65 条
- RRF top-10: 1. · cli/specproof/commands/craft.py; 2. ✔ craft/__init__.py; 3. ✔ craft/llm.py; 4. · craft/planner.py; 5. · craft/loop.py
- RRF+graph top-10: 1. · cli/specproof/commands/craft.py; 2. ✔ craft/__init__.py; 3. ✔ craft/llm.py; 4. · craft/planner.py; 5. · craft/loop.py

### e06 · error · python

- 查询: BudgetError
- 期望文件 (2): craft/budget.py, craft/__init__.py
- BM25         : recall@10=100.0%  MRR=1.000  延迟=59.8 ms
- BM25+graph   : recall@10=50.0%  MRR=1.000  延迟=142.6 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=1.5 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.500  延迟=61.4 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.500  延迟=151.0 ms
- BM25 top-10: 1. ✔ craft/budget.py; 2. ✔ craft/__init__.py; 3. · cli/specproof/commands/craft.py
- +graph top-10: 1. ✔ craft/budget.py; 2. · agent/checkers/java_source.py; 3. · agent/nodes/build_cache.py; 4. · agent/nodes/compile_contracts.py; 5. · agent/nodes/create_capsule.py; 6. · agent/nodes/generate_counterexamples.py; 7. · agent/nodes/review_court.py; 8. · agent/nodes/run_deep_experiments.py; 9. · agent/nodes/run_differential.py; 10. · agent/preflight.py; … 共 60 条
- RRF top-10: 1. · cli/specproof/commands/craft.py; 2. ✔ craft/budget.py; 3. ✔ craft/__init__.py
- RRF+graph top-10: 1. · cli/specproof/commands/craft.py; 2. ✔ craft/budget.py; 3. ✔ craft/__init__.py

### e07 · error · java

- 查询: Expected status 401 changeEmail unauthorized
- 期望文件 (2): demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java, demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java
- BM25         : recall@10=0.0%  MRR=0.000  延迟=425.1 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=425.4 ms
- symbol-index : recall@10=100.0%  MRR=1.000  延迟=3.1 ms
- BM25+RRF     : recall@10=100.0%  MRR=1.000  延迟=428.3 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=1.000  延迟=431.2 ms
- BM25 top-10: (无命中)
- +graph top-10: (无命中)
- RRF top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java; 3. · demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 4. · agent/contracts/registry.py; 5. · agent/contracts/storage.py; 6. · agent/worker.py; 7. · craft/tools.py; 8. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java; 3. · demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 4. · agent/contracts/registry.py; 5. · agent/contracts/storage.py; 6. · agent/worker.py; 7. · craft/tools.py; 8. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java

### e08 · error · java

- 查询: changeEmail duplicate email already registered
- 期望文件 (2): demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java, demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java
- BM25         : recall@10=0.0%  MRR=0.000  延迟=8.3 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=8.3 ms
- symbol-index : recall@10=100.0%  MRR=0.500  延迟=3.0 ms
- BM25+RRF     : recall@10=100.0%  MRR=0.500  延迟=11.4 ms
- BM25+RRF+graph: recall@10=100.0%  MRR=0.500  延迟=17.5 ms
- BM25 top-10: (无命中)
- +graph top-10: (无命中)
- RRF top-10: 1. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/checkers/java_source.py; 4. · agent/contracts/storage.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/config/RabbitMQConfig.java; 6. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 7. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java
- RRF+graph top-10: 1. · demo/spring-backend/src/main/java/com/specproof/demo/controller/UserController.java; 2. ✔ demo/spring-backend/src/main/java/com/specproof/demo/service/UserService.java; 3. · agent/checkers/java_source.py; 4. · agent/contracts/storage.py; 5. · demo/spring-backend/src/main/java/com/specproof/demo/config/RabbitMQConfig.java; 6. · demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 7. ✔ demo/spring-backend/src/test/java/com/specproof/demo/UserControllerTest.java

### e09 · error · python

- 查询: 缺少 JAVA_HOME 或 Maven Wrapper(mvnw) 检查失败
- 期望文件 (1): agent/preflight.py
- BM25         : recall@10=0.0%  MRR=0.000  延迟=52.3 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=52.3 ms
- symbol-index : recall@10=0.0%  MRR=0.000  延迟=2.8 ms
- BM25+RRF     : recall@10=0.0%  MRR=0.000  延迟=55.0 ms
- BM25+RRF+graph: recall@10=0.0%  MRR=0.000  延迟=55.1 ms
- BM25 top-10: (无命中)
- +graph top-10: (无命中)
- RRF top-10: (无命中)
- RRF+graph top-10: (无命中)

### e10 · error · java

- 查询: 库存不足(stock insufficient)时下单失败
- 期望文件 (2): demo/spring-backend/src/main/java/com/specproof/demo/service/OrderService.java, demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- BM25         : recall@10=0.0%  MRR=0.000  延迟=50.5 ms
- BM25+graph   : recall@10=0.0%  MRR=0.000  延迟=50.5 ms
- symbol-index : recall@10=50.0%  MRR=1.000  延迟=5.0 ms
- BM25+RRF     : recall@10=50.0%  MRR=1.000  延迟=55.5 ms
- BM25+RRF+graph: recall@10=50.0%  MRR=1.000  延迟=55.9 ms
- BM25 top-10: (无命中)
- +graph top-10: (无命中)
- RRF top-10: 1. ✔ demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java
- RRF+graph top-10: 1. ✔ demo/spring-backend/src/test/java/com/specproof/demo/OrderControllerTest.java; 2. · demo/spring-backend/src/main/java/com/specproof/demo/dto/OrderResponse.java; 3. · demo/spring-backend/src/main/java/com/specproof/demo/dto/PlaceOrderRequest.java; 4. · demo/spring-backend/src/main/java/com/specproof/demo/dto/UserResponse.java; 5. · demo/spring-backend/src/main/java/com/specproof/demo/entity/CustomerOrder.java; 6. · demo/spring-backend/src/main/java/com/specproof/demo/entity/Product.java; 7. · demo/spring-backend/src/main/java/com/specproof/demo/entity/User.java

## RRF 融合实测 — 加性融合 (additive-only)

- 实测时间: 2026-08-19 14:50:24 +0800
- 方法: RRF(k=60) 对 [hybrid_semantic(BM25), symbol, vector] 三列表求和融合; 图谱邻域经 retrieval.fusion.GraphBoost 加性策略处理 — 融合排序永不被重排/替换, 邻域仅在未命中融合列表时追加末尾 (最多 10 条, 种子=融合前 8 条 × 1 跳)。
- 向量通道: absent — embeddings unconfigured: LLM_EMBEDDING_BASE_URL/LLM_BASE_URL not set — embeddings unconfigured。

| 系统 | recall@10 | MRR | 平均延迟 | 全命中查询数 |
|---|---:|---:|---:|---:|
| BM25 | 72.2% | 0.561 | 72.3 ms | 19/30 |
| BM25+RRF (无图谱) | 87.2% | 0.760 | 74.6 ms | 23/30 |
| BM25+RRF+graph | 87.2% | 0.760 | 126.6 ms | 23/30 |

### 每查询对比 (BM25 vs BM25+RRF vs BM25+RRF+graph)

| 查询 | BM25 r@10 | BM25 MRR | RRF r@10 | RRF MRR | RRF+graph r@10 | RRF+graph MRR |
|---|---:|---:|---:|---:|---:|---:|
| s01 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| s02 | 100.0% | 0.500 | 100.0% | 1.000 | 100.0% | 1.000 |
| s03 | 0.0% | 0.000 | 100.0% | 0.333 | 100.0% | 0.333 |
| s04 | 100.0% | 0.500 | 100.0% | 0.333 | 100.0% | 0.333 |
| s05 | 0.0% | 0.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| s06 | 100.0% | 0.333 | 100.0% | 0.500 | 100.0% | 0.500 |
| s07 | 66.7% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| s08 | 66.7% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| s09 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| s10 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| r01 | 66.7% | 0.200 | 66.7% | 1.000 | 66.7% | 1.000 |
| r02 | 33.3% | 0.500 | 66.7% | 1.000 | 66.7% | 1.000 |
| r03 | 33.3% | 0.333 | 66.7% | 0.200 | 66.7% | 0.200 |
| r04 | 100.0% | 0.500 | 100.0% | 1.000 | 100.0% | 1.000 |
| r05 | 100.0% | 1.000 | 66.7% | 1.000 | 66.7% | 1.000 |
| r06 | 100.0% | 0.500 | 100.0% | 0.333 | 100.0% | 0.333 |
| r07 | 100.0% | 0.500 | 100.0% | 0.500 | 100.0% | 0.500 |
| r08 | 100.0% | 0.143 | 0.0% | 0.091 | 0.0% | 0.091 |
| r09 | 100.0% | 0.333 | 100.0% | 1.000 | 100.0% | 1.000 |
| r10 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| e01 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| e02 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| e03 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| e04 | 100.0% | 1.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| e05 | 100.0% | 0.500 | 100.0% | 0.500 | 100.0% | 0.500 |
| e06 | 100.0% | 1.000 | 100.0% | 0.500 | 100.0% | 0.500 |
| e07 | 0.0% | 0.000 | 100.0% | 1.000 | 100.0% | 1.000 |
| e08 | 0.0% | 0.000 | 100.0% | 0.500 | 100.0% | 0.500 |
| e09 | 0.0% | 0.000 | 0.0% | 0.000 | 0.0% | 0.000 |
| e10 | 0.0% | 0.000 | 50.0% | 1.000 | 50.0% | 1.000 |

## 历史基线 (2026-08-18, 图谱消融)

| 系统 | recall@10 | MRR | 平均延迟 | 全命中查询数 |
|---|---:|---:|---:|---:|
| BM25 | 82.2% | 0.656 | 50.5 ms | 21/30 |
| BM25+graph | 48.9% | 0.528 | 89.6 ms | 11/30 |
| symbol-index | 75.6% | 0.683 | 1.3 ms | 20/30 |

- 48.9% 消融根因: top-8 种子做 1 跳邻域展开后, 邻域列表整体【替换】了语义排序 (旧 BM25+graph 列直接以展开结果作为最终排序; retrieval/hybrid.py 同样以 `merged = list(expanded)` 替换融合结果), 而非把邻域作为补充候选追加 — 期望文件因此被邻居噪音淹没。本报告 BM25+RRF+graph 使用 retrieval/fusion.py 的 GraphBoost 加性策略修正此缺陷。

## 诚实性说明

1. 融合数字来自 retrieval/fusion.py (N 列表 RRF + 加性图谱增强); BM25 / BM25+graph / symbol-index 三列为原有实现, 代码路径未改动。
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
