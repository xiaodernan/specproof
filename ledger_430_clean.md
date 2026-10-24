## #430 Phase 4 进展：Mutation Engine + OpenAPI Fuzzing 完成，Gradle Adapter 启动

**背景**：#429 启动 Phase 4 三大支柱。本批完成前两项，启动第三项。

### 1. Mutation-guided test synthesis ✅ 完成

新增 `craft/mutation.py`：
- **MutationOperator**：7 种算子（条件取反、边界翻转、算术替换、常量替换、空检查删除、返回值替换）
- **语言支持**：Python (AST 级)、Java/Go/JS/TS (Regex 级)
- **MutationEngine**：生成变异体、运行测试、分类结果 (KILLED/SURVIVED/EQUIVALENT/ERROR)
- **MutationReport**：聚合统计、mutation_score、mutation_score_with_equivalent
- **run_mutation_testing()**：高级入口函数

新增 `tests/unit/test_mutation_engine.py` (11 项)：
- 语言算子定义、引擎初始化、分数计算、变异体创建
- Python: 条件取反、算术替换、常量替换
- Java: 通用 regex 变异
- max_mutants 限制、测试文件排除

质量门：ruff/mypy 全绿，11 passed

### 2. OpenAPI 状态化 Fuzzing ✅ 完成

新增 `experiments/openapi_fuzzing.py`：
- **OpenAPISpecParser**：解析 OpenAPI 3.x (YAML/JSON)，提取可测试操作
- **PayloadGenerator**：7 种策略 (BOUNDARY/TYPE_MISMATCH/REQUIRED_MISSING/ENUM_VIOLATION/FORMAT_VIOLATION/INJECTION/OVERSIZED)
- **Shrinker**：Delta debugging 简化版，最小化失败载荷
- **OpenAPIFuzzer**：主入口，基线验证 + 策略遍历 + 结果收集 + EvidenceFragment 输出
- **run_openapi_fuzzing()**：便捷入口

新增 `tests/unit/test_openapi_fuzzing.py` (17 项)：
- 解析器 YAML/JSON、有效载荷生成
- 7 种策略各自测试
- Shrinker: 字段移除、字符串缩短
- FuzzResult、Report→Fragment 转换、Fuzzer 初始化

质量门：ruff/mypy 全绿，17 passed

### 3. Gradle Adapter 🔄 进行中

计划新增：
- `craft/adapters/protocol.py`：统一 AdapterProtocol 接口
- `craft/adapters/gradle_adapter.py`：Gradle + JUnit 5 适配器
- 依赖解析：Gradle lockfile / `--offline` + 本地缓存卷
- 执行命令：`./gradlew test --no-daemon`
- 输出解析：JUnit XML → ExecutionResult + EvidenceFragment
- 兼容性矩阵记录

### 证据文件
- `craft/mutation.py` (400+ 行)
- `tests/unit/test_mutation_engine.py` (11 项)
- `experiments/openapi_fuzzing.py` (600+ 行)
- `tests/unit/test_openapi_fuzzing.py` (17 项)
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md`：追加 #430