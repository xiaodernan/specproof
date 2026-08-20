# Static Checker Compatibility Matrix — run_static_checks (§14.1)

> 生成方式: 本表所有表格由真实运行从 `agent/checkers/registry.py` 的活数据打印
> (见 §9)。唯一事实源是注册表本身 (`REGISTRY` + `EXTENDED_REGISTRY` +
> `FILE_TYPE_MATRIX`); 一致性回归由 `tests/unit/test_static_check_registry.py`
> 钉死。若本表与注册表不一致, 以注册表为准并修复本表。

`run_static_checks` 节点共调度 **10 个确定性检查器**:

- 7 个统一签名 `(base_files, head_files)` 的 java-source 检查器, 经
  `run_registered_checks()` 按 (language, framework) 矩阵执行;
- 3 个异构检查器 (schema.sql / 测试强度 / 宪法条款), 经
  `dispatch_checker(name, **kwargs)` 按注册表名调用 — 未知名字 fail-closed。

## 1. 状态图例

| 状态 | 含义 |
|---|---|
| ✅ 支持 | 检查器为该文件类型实现 (文档范围 + 真实实现); 逐检查器的单测覆盖见 §7 |
| ❌ 不支持 | 显式排除: 路径后缀过滤 (`*Controller.java` 等) 或文档范围 (SQL 解析器、JUnit 构造)。检查器对该类型不会产生任何判定, 配合 fail-closed 机制兜底 (§4) |
| ❓ 未验证 | 实现没有文件类型护栏, 机械上会扫描这类输入, 但 pipeline 从不投喂、测试从未跑过 — 诚实标注, 不声称支持 |

## 2. 检查器清单 (每个检查器一个注册表条目)

| id (registry name) | check target | contract family | file_types (supported) | severity cap | version | cost |
|---|---|---|---|---|---|---|
| `check_auth_annotations` | security annotations on mutating endpoints (*Controller.java methods with @Put/Post/Delete/PatchMapping) | AUTH-01 | java/main | MAJOR | 2.0.0 | low |
| `check_transactional` | write methods in *Service.java must keep @Transactional and write operations must not move outside a transaction boundary | TRANSACTION-01 | java/main | MAJOR | 2.0.0 | low |
| `check_unique_email` | duplicate-email guard (existsByEmail) must not be removed | UNIQUE-01 | java/main | MAJOR | 2.0.0 | low |
| `check_token_invalidation` | old-token invalidation call sites (invalidateOldTokens / redisTemplate.delete) must not be removed | TOKEN_INVALIDATION-01 | java/main | MAJOR | 2.0.0 | low |
| `check_event_once` | event publish count (convertAndSend) must not increase | EVENT_ONCE-01 | java/main | MAJOR | 2.0.0 | low |
| `check_schema_compat` | API DTO fields must not be removed or renamed | BACKWARD_COMPATIBLE-01 | java/main | MAJOR | 2.0.0 | low |
| `check_endpoint_changes` | public endpoint surface (HTTP verb, path) must not shrink or change | OPENAPI-01 | java/main | MAJOR | 2.0.0 | low |
| `check_schema_sql` | schema.sql DDL (tables/columns must not drop, shrink or change type) + JPA entity @Column constraints (nullable/unique/length must not weaken) | MIGRATION-01 | sql/ddl, java/main | MAJOR | 1.1.0 | low |
| `check_test_weakening` | test suite strength: @Test count, @Disabled additions and assertion counts must not drop | TEST_STRENGTH-01 | java/test | MAJOR | 1.1.0 | low |
| `check_forbidden_changes` | constitution 'forbidden changes' clauses from the requirement (annotation removal / duplicate publish / unique guard / token invalidation / DTO field removal) | FORBIDDEN-* | java/main | MAJOR | 1.0.0 | low |

调用签名 (`args_spec` — 节点与 replay 路径都按此调用):

| id | args_spec |
|---|---|
| 7 个 uniform 检查器 | `base_files, head_files` |
| `check_schema_sql` | `base_schema, head_schema, base_files, head_files` |
| `check_test_weakening` | `base_test_files, head_test_files` |
| `check_forbidden_changes` | `base_files, head_files, forbidden_clauses, contract_id` |

## 3. 检查器 × 文件类型兼容矩阵

| checker | java/main | java/test | sql/ddl | python | typescript | go | pom | yaml |
|---|---|---|---|---|---|---|---|---|
| `check_auth_annotations` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `check_transactional` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `check_unique_email` | ✅ | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ |
| `check_token_invalidation` | ✅ | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ |
| `check_event_once` | ✅ | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ | ❓ |
| `check_schema_compat` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `check_endpoint_changes` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `check_schema_sql` | ✅ | ❓ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `check_test_weakening` | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `check_forbidden_changes` | ✅ | ❓ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

依据 (均来自实现代码):

- **pipeline 事实**: 节点只读 `src/main/java/*.java`、`src/test/java/*.java` 与
  `src/main/resources/schema.sql` — python / typescript / go / pom / yaml 今天不会
  进入任何检查器。
- **❌ 来源**: 路径后缀过滤 (`check_auth_annotations`/`check_endpoint_changes`
  只看 `*Controller.java`; `check_transactional` 只看 `*Service.java`;
  `check_schema_compat` 只看 dto 路径/名) 或文档范围 (`check_schema_sql` 的 SQL
  解析器、`check_test_weakening` 的 JUnit 构造、`check_forbidden_changes` 的
  Java 方法切分器)。
- **❓ 来源**: `check_unique_email` / `check_token_invalidation` /
  `check_event_once` 对输入无文件类型护栏 (纯文本扫描) — 若把外来文件塞进 files
  dict, 它们机械上会扫; 没有任何测试跑过这类输入 → 诚实标注未验证。
  `check_schema_sql` / `check_forbidden_changes` 对 java/test 同理 (函数无护栏,
  节点只投喂 main 文件, 无测试覆盖)。

## 4. 语言/框架矩阵与 fail-closed 行为

- `java/spring-boot` → 7 个 uniform 检查器 (`run_registered_checks`); 该目标仓库
  内的 schema.sql / 测试源 / 宪法条款由 3 个异构检查器按需运行。
- 其它目标 (真实运行输出):
  `matrix_note('python','django') = NOT_IMPLEMENTED: no static checker registered for
  target python/django (supported: java/spring-boot)`
- 未知检查器名 (真实运行输出):
  `require_checker('check_does_not_exist') → UnknownCheckerError: unknown checker
  'check_does_not_exist' (registered: check_auth_annotations, check_endpoint_changes,
  check_event_once, check_forbidden_changes, check_schema_compat, check_schema_sql,
  check_test_weakening, check_token_invalidation, check_transactional,
  check_unique_email)`
- 未知文件类型 → `UnknownFileTypeError` (`file_type_status`)。
- 检查器崩溃 → `CHECKER_FAILED` 证据 (severity NONE, confidence 1.0), 所属
  contract family 保持 UNVERIFIED — 绝不因沉默 PASS。

## 5. 严重度映射 (实现事实)

| 来源 | severity | confidence |
|---|---|---|
| 10 个检查器本体 | 只发 MAJOR (三个 `_finding` 助手默认 MAJOR; constitution 字面量 MAJOR) | 0.85 |
| 节点封顶 (checker_failed 除外) | BLOCKER→MAJOR | `min(confidence, 0.85)` + p0_5_note |
| checker_failed 证据 (豁免) | NONE | 1.0 |

契约结果映射: FAIL (发现违例) / PASS (受护构造完整) / UNVERIFIED (构造缺失或检查器崩溃)。

## 6. 输出 schema

`OUTPUT_SCHEMA = ['id','contract_id','severity','type','description','evidence_type',
'confidence','location','source']` — 每个检查器条目都声明它; 真实样本 (MIGRATION-01):

```json
{"id": "SRC-MIGRATION-COLU", "contract_id": "MIGRATION-01", "severity": "MAJOR",
 "type": "column_type_changed", "description": "Column 'users.email' type changed from
 VARCHAR(255) to VARCHAR(50) — may truncate or corrupt existing data",
 "evidence_type": "java_source_diff", "confidence": 0.85,
 "location": "src/main/resources/schema.sql", "source": "contract_checker"}
```

变体: checker_failed 证据另带 `families` 键, severity NONE / confidence 1.0。

## 7. 测试接地 (逐检查器的直接单测, 诚实标注)

| checker | 直接单测 | 备注 |
|---|---|---|
| `check_auth_annotations` | `tests/unit/test_checker_fixes.py` | B1: 嵌套括号注解移除、组合注解等价、接口默认方法保护 |
| `check_transactional` | **无直接单测** | 经 run_contract_checks 被间接调用; golden case-02 (transactional-removal) 属 eval 语料 |
| `check_unique_email` | **无直接单测** | golden case-04 (duplicate-email) 属 eval 语料 |
| `check_token_invalidation` | `tests/unit/test_checker_fixes.py` | B4: 调用点级移除检测 (case-05 回归) |
| `check_event_once` | `tests/unit/test_replay_static_verify.py` | 经 run_contract_checks 重推导 (EVENT_ONCE-01/duplicate_publish) |
| `check_schema_compat` | **无直接单测** | golden case-06 (schema-break) 属 eval 语料 |
| `check_endpoint_changes` | `tests/unit/test_endpoint_checker.py` | (verb, path) 表面收缩检测 |
| `check_schema_sql` | `tests/unit/test_schema_and_tests_checker.py` | DDL 删表/删列/改型/约束弱化 + 类型空白归一 |
| `check_test_weakening` | `tests/unit/test_schema_and_tests_checker.py` | 测试删除/禁用/断言弱化 |
| `check_forbidden_changes` | `tests/unit/test_constitution_checker.py` | 注解移除/重复发布/令牌护栏/字段移除 |
| 注册表本身 | `tests/unit/test_checker_registry.py` + `tests/unit/test_static_check_registry.py` | 完整性/可调用性/fail-closed |
| 节点封顶 | `tests/unit/test_court_no_evidence_blocker.py` | BLOCKER→MAJOR + confidence ≤ 0.85 |

## 8. 未验证项的诚实边界

- 3 个无护栏扫描检查器对非 java/main 输入的 ❓ 状态 (§3)。
- `check_schema_sql` / `check_forbidden_changes` 对 java/test 的 ❓ 状态。
- `check_transactional` / `check_unique_email` / `check_schema_compat` 无直接
  单测 — 覆盖来自 golden-cases eval 语料与 court/矩阵层的间接断言, 不属于本门禁
  单元集。
- python/ts/go/pom/yaml 整列为 ❌/❓ 且 pipeline 从不投喂 — 矩阵描述的是检查器自身
  能力, 不代表产品声称跨语言支持 (backlog #6 跨语言样本仍是待办)。

## 9. 门禁 (真实运行数字, Python 3.12.10 / pytest 9.1.1 / ruff 0.15.21 / mypy 2.2.0)

- 改动前基线 (相关 7 文件): **93 passed in 4.44s**。
- ruff (改动 3 文件): **All checks passed!**
- mypy --strict (改动 2 源文件): **Success: no issues found in 2 source files**
- pytest 门禁集 (新测试 + 相关 7 文件): **108 passed in 3.23s** (15 个新测试)。
- 全量 tests/unit 回归: 见交付报告。

## 10. 变更文件

- `agent/checkers/registry.py` — 补全 3 个异构检查器条目、条目元数据字段
  (check_target/file_types/output_schema/severity_cap/args_spec)、
  `FILE_TYPE_MATRIX`、fail-closed 查询 (`require_checker` / `dispatch_checker` /
  `file_type_status`)。
- `agent/nodes/run_static_checks.py` — 3 个异构检查器改经 `dispatch_checker`
  按注册表名调度 (未知名 fail-closed)。
- `tests/unit/test_static_check_registry.py` — 新建, 15 个测试。
- `docs/design/STATIC_CHECKER_MATRIX.md` — 本文档。
