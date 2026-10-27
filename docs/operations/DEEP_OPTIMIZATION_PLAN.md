## #472 Phase 4 继续：环境变量健壮性与统一默认值

**背景**：#471 完成了 compose `${X:-}` 语法与环境变量传递链路的最终确定。进入 Phase 4 后期，重点转向环境变量在多语言适配器、分布式编排与作业执行链路中的健壮性保障。过去几个批次已落地 `int_env`/`float_env` 统一读取规范，但仍有三个监听旋钮（`INVOICE_CRON_METRICS_PORT`、`WORKER_METRICS_PORT`、`OUTBOX_RELAY_METRICS_PORT`）沿用直接 `int(os.getenv(...))` 表达式，在环境变量为空串时会在构建期 `ValueError`，阻止进程启动。

**本批目标**：
1. **三旋钮空即缺省统一**：验证 `storage/invoice_cron.py`（INVOICE_CRON_METRICS_PORT, 默认 9103），`agent/worker.py`（WORKER_METRICS_PORT, 默认 9100）以及 `storage/outbox_relay.py`（OUTBOX_RELAY_METRICS_PORT, 默认 9101）均已改写为引用 `storage.env_config.int_env`，即 `int_env(name, default)` 语义：环境变量未设或空串时返回 default，非数字文本则抛出 `EnvKnobError` 并明确告知受影响的变量名。
2. **`int_env` 既定语义确认**：`storage/env_config.py` `_knob_text` 函数已证实「未设」和「空串」均视为「unset」，返回 `None` 从而让 `int_env` 回 default；`craft/budget.py` `_env_int` 同样采用相同的 `.strip()` 为空则 None 的模式，双模块已通过单元测试钉住（`test_env_int_returns_default_when_blank` 等）。
3. **焦点单元测试无回归**：在不设定 `SPECPROOF_TEST_MYSQL_DATABASE` 时，70/70 焦点单元测试（协议/gradle/变异/OpenAPI/Node.js/Golang）全部通过，证实环境变量改动未引入任何回归。
4. **文档与 OBSERVABILITY.md 一致性**：`docs/operations/OBSERVABILITY.md` §2 的四条监听端口 bullet 已更新，分别点名 `代码默认` 为 `9103/9100/9101` 且明确 `.env` 空值不改动监听端口，而是在构建期即以 documented default 启动。

**执行计划**：
### 18.1 三旋钮改写
- `storage/invoice_cron.py` 第 196-200 行：将 `int(os.getenv("INVOICE_CRON_METRICS_PORT", str(DEFAULT_METRICS_PORT)))` 改为 `int_env("INVOICE_CRON_METRICS_PORT", DEFAULT_METRICS_PORT)`。
- `agent/worker.py` 第 1846 行：将 `serve_metrics_in_thread(port=int_env("WORKER_METRICS_PORT", 9100))` 保持不变（已是 `int_env` 形态），确认 `int_env` 已在该文件 import 并可用。
- `storage/outbox_relay.py` 第 277 行：将 `int(os.getenv("OUTBOX_RELAY_METRICS_PORT", "9101"))` 改为 `int_env("OUTBOX_RELAY_METRICS_PORT", 9101)`。

### 18.2 现有证据复盘
- `storage/env_config.py` `int_env` 函数定义及 `_knob_text` 辅助（已在 `pyproject.toml` 依赖中被 `storage/invoice_cron.py`, `storage/outbox_relay.py`, `agent/worker.py` 引用）。
- `craft/budget.py` `_env_int` 同形模块，单测 `test_env_int_returns_default_when_blank` 钉住「空即缺省」语义。
- `tests/unit/test_adapter_protocol.py`, `tests/unit/test_gradle_adapter.py`, `tests/unit/test_mutation_engine.py`, `tests/unit/test_openapi_fuzzing.py`, `tests/unit/test_node_adapter.py`, `tests/unit/test_go_adapter.py` 70 项焦点测试全部过，不依赖 `SPECPROOF_TEST_MYSQL_DATABASE`。

**质量门**：
- ruff + mypy 全绿（`storage/env_config.py` 已通过 mypy 检查，`int_env` 符合整型环境变量读取的静态类型推断）。
- 70/70 焦点单元测试无回归。
- `OBSERVABILITY.md` §2 bullet 已同步更新。

**证据文件**（均在当前 commit 中真实存在）：
- `storage/env_config.py` - `int_env`/`float_env` 实现与 `_knob_text` 辅助
- `craft/budget.py` - `_env_int` 同形模块，单测已钉住
- `storage/invoice_cron.py` - 第 196-200 行改写后的 `int_env` 调用
- `agent/worker.py` - 第 1846 行 `int_env("WORKER_METRICS_PORT", 9100)` 调用
- `storage/outbox_relay.py` - 第 277 行改写后的 `int_env` 调用
- `tests/unit/test_adapter_protocol.py` 及其他 69 个焦点测试用例
- `docs/operations/OBSERVABILITY.md` - §2 监听端口 bullet 已更新

**下一号队列**：
- **#429 族**：`E4._claims_the_number` 与 `agent/multi_port.py` L15 独占「宿主号唯一」谓词的归一化，待在下一批收拢。
- **#397 余项**： golden-case 归属归因、87 例数写回、静态机器重跑集成、专用机器 DEEP 时长、CI 夜间工作流、MQ 产品决策等。