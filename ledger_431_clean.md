## #431 Phase 4 继续：Gradle Adapter 完善 + 跨语言适配器注册中心

**背景**：#430 完成了 Mutation Engine 和 OpenAPI Fuzzing 的核心实现。本批继续完善 Gradle Adapter 并启动适配器注册中心。

**本批目标**：
1. **Gradle Adapter 完善**：完善 JUnit XML 解析、离线模式、依赖树收集
2. **适配器注册中心**：实现自动检测、注册表、ID 分配机制
3. **AdapterNotImplemented 规范**：确保 fail-closed 行为一致

**当前进度**：
| 项目 | 状态 |
|------|------|
| Mutation-guided test synthesis | ✅ 完成 (#430) |
| OpenAPI 状态化 Fuzzing | ✅ 完成 (#430) |
| Gradle Adapter 核心功能 | ✅ 完成 (#430) |
| Gradle Adapter 完善 | 🔄 进行中 (#431) |
| 适配器注册中心 | 🔄 进行中 (#431) |
| Node.js 适配器 | ⏳ 待启动 (#432+) |
| Go 适配器增强 | ⏳ 待启动 (#432+) |

**已完成的代码变更**：
- `craft/adapters/protocol.py`：统一适配器协议、注册中心、自动检测
- `craft/adapters/gradle_adapter.py`：完善 JUnit XML、离线模式、依赖树、目标目标
- `tests/unit/test_adapter_protocol.py` (23 项) + `tests/unit/test_gradle_adapter.py` (23 项) 全绿

**质量门**：
- ruff + mypy 全绿
- 所有新增测试通过
- 现有测试无回归
- ledger fence：无重复头，U+FFRD 计数保持

**证据文件**：
- `craft/adapters/protocol.py`（新增，约 200 行）
- `craft/adapters/gradle_adapter.py`（已存在，已增强）
- `tests/unit/test_adapter_protocol.py`（新增，23 项）
- `tests/unit/test_gradle_adapter.py`（已增强，23 项）
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md`：追加 #431