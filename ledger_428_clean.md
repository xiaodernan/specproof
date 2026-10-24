## #428 Phase 3 继续：CONTRACT_REVIEW 诚实生产路径 + 证据链回放强化

**背景**：长期计划 Phase 3（动态实验室扩展）已完成 90%+。#306 账本记录的队列中仍有一项：**CONTRACT_REVIEW 的诚实生产路径**（当前管线不在那里停，状态机里有该态但无生产写入方）。

**本批目标**：
1. **落地 CONTRACT_REVIEW 生产写入方**：让管线在契约审查阶段真正停下、记录状态、产出可观测事件
2. **证据链回放强化**：batch replay runner 的成功率统计、失败分类细化、回放记录持久化
3. **阶段 3 收尾验证**：跑通所有 Phase 3 相关测试，确保无回归

**当前 Phase 3 完成度清单**：
| 任务 | 状态 | 证据 |
|---|---|---|
| P3-1 Redis 状态采集器 | ✅ | `experiments/collectors.py` + `tests/unit/test_dynamic_collectors.py` (23) |
| P3-2 RabbitMQ 发布探针 | ✅ | 同上 |
| P3-3 对象存储采集器 | ✅ | 同上 |
| P3-4 六类实验模板 | ✅ | `experiments/experiment_classes.py` + #335 case-101 holdout 验证 |
| P3-4 模板体抽成可移植模板 | ✅ | #319/#320: `agent/experiments/profile.py` + `templates.py` |
| P3-5 统一状态快照 | ✅ | `experiments/db_snapshot.py` + `tests/unit/test_db_snapshot.py` (28) |
| P3-6 contract_id 一贯传递 | ✅ | `agent/nodes/run_differential.py` + `tests/unit/test_contract_id_attribution.py` (13) |
| P3-7 故障注入（服务崩溃/超时/网络断开/消息重投/DB锁/磁盘满/空JSON） | ✅ | #321/#322/#330 |
| P3-7 对象存储诚实失败处理 | ✅ | `storage/artifact_store.py` + `tests/fault/test_artifact_store_faults.py` (10) |
| P3-7 证据包生产路径 | ✅ | #338: `collect_evidence` 节点入图 |
| P3-7 base/head 真实分离 | ✅ | #339: 两工作区共用外部服务，两时刻采样 |
| P3-7 证据链带坐标走 | ✅ | #342/#343: 胶囊上传对象存储回报坐标 |
| **CONTRACT_REVIEW 生产写入方** | ❌ **待做** | #306 队列项 |
| **状态机故障注入覆盖** | ❌ **待做** | 退出条件要求 |

**执行计划**：
1. 在 `agent/nodes/` 下新增 `contract_review.py` 节点，实现：
   - 读取已编译契约清单
   - 检查审批状态（APPROVED / PENDING / REJECTED）
   - 未获批准契约：写入 Job 状态 = CONTRACT_REVIEW，记录原因，推进事件
   - 已获批准：直接通过，记录审批证据
   - 超时/取消处理
2. 在 `agent/job_stage.py` 中确认 CONTRACT_REVIEW 的推进逻辑（已有 ENUM，需确认推进条件）
3. 在 `agent/graph.py` 中将 contract_review 节点接入管线（在 differential 之前、run_differential 之后或合适位置）
4. 补齐状态机故障注入测试：重复推进、乱序、并发、非法转换
5. 运行 `tests/unit/test_job_stage.py` (21) + 相关测试验证

**质量门**：
- ruff + mypy 全绿
- 新增测试通过
- 现有 Phase 3 测试无回归：test_dynamic_collectors.py、test_db_snapshot.py、test_job_stage.py、test_contract_id_attribution.py、test_artifact_store_faults.py
- ledger fence：无重复头，U+FFFD 计数保持

**证据文件**：
- `agent/nodes/contract_review.py`（新增）
- `agent/job_stage.py`（修改）
- `agent/graph.py`（修改）
- `tests/unit/test_contract_review.py`（新增）
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md`：追加 #428