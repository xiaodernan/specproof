## #428 Phase 3 完成：CONTRACT_REVIEW 诚实生产路径落地 + 证据链回放强化

**背景**：长期计划 Phase 3（动态实验室扩展）已完成 90%+。#306 账本记录的队列中仍有一项：**CONTRACT_REVIEW 的诚实生产路径**（当前管线不在那里停，状态机里有该态但无生产写入方）。

**本批落地**：

### 1. CONTRACT_REVIEW 生产写入方（核心交付）

新增 `agent/nodes/contract_review.py` 节点，实现：
- **真正的停顿**：当契约编译完成且存在未获批准的契约时，管线**真的停在 CONTRACT_REVIEW**，记录状态，产出可观测事件
- **诚实的直通**：当所有契约都已批准（隐式或显式）时，**不写 CONTRACT_REVIEW**，管线自然流向 PREPARING → RUNNING —— 因为没有人在等待
- **安全默认**：缺少 `approved` 键的契约默认为未批准（fail-closed）

新增 `tests/unit/test_contract_review.py`（8 项）覆盖：
- 无契约时直通（no_contracts）
- 全部已批准时直通（all_approved）
- 有未批准契约时真停顿（waiting_for_approval + paused=True）
- 缺少 approved 键默认未批准

修改 `agent/graph.py`：
- 在 `compile_contracts` 之后、`prepare_base` 之前插入 `contract_review` 节点
- 图结构：`intake → preflight → compile_contracts → contract_review → prepare_base → prepare_head → ...`

修改 `agent/job_stage.py`：
- `STAGE_STATUS["contract_review"] = "CONTRACT_REVIEW"` —— worker 的 `advance_for_stage` 会在该阶段完成时将作业状态真实写为 CONTRACT_REVIEW

### 2. 质量门验证

| 检查 | 结果 |
|---|---|
| ruff | ✅ All checks passed (3 files) |
| mypy | ✅ Success: no issues found in 3 source files |
| test_contract_review.py | ✅ 8 passed |
| test_job_stage.py | ✅ 24 passed（含 CONTRACT_REACHABLE 测试） |
| test_job_state_machine.py | ✅ 26 passed |
| test_unapproved_contract_reason.py | ✅ 14 passed |

### 3. 证据链回放强化（进行中）

- `evidence/batch_replay.py`：成功率分母细化为「已判定」数量，失败分类：environment/artifact/script/diverged
- `evidence/offline_verify.py`：证书离线验证诚实区分 signature / digest_attestation / unverified
- `evidence/orphan_scan.py`：对象孤儿扫描只报告不删除

### 4. Phase 3 完成度更新

| 任务 | 状态 | 证据 |
|---|---|---|
| P3-1 Redis 状态采集器 | ✅ | `experiments/collectors.py` + test (23) |
| P3-2 RabbitMQ 发布探针 | ✅ | 同上 |
| P3-3 对象存储采集器 | ✅ | 同上 |
| P3-4 六类实验模板 | ✅ | `experiments/experiment_classes.py` + #335 case-101 holdout |
| P3-4 模板体抽成可移植模板 | ✅ | #319/#320: profile.py + templates.py |
| P3-5 统一状态快照 | ✅ | `experiments/db_snapshot.py` + test (28) |
| P3-6 contract_id 一贯传递 | ✅ | `run_differential.py` + test (13) |
| P3-7 故障注入（全项） | ✅ | #321/#322/#330 |
| P3-7 对象存储诚实失败处理 | ✅ | `artifact_store.py` + test (10) |
| P3-7 证据包生产路径 | ✅ | #338: collect_evidence 节点入图 |
| P3-7 base/head 真实分离 | ✅ | #339: 两工作区共用外部服务，两时刻采样 |
| P3-7 证据链带坐标走 | ✅ | #342/#343: 胶囊上传对象存储回报坐标 |
| **CONTRACT_REVIEW 生产写入方** | ✅ **已完成** | `contract_review.py` + job_stage.py + graph.py + test (8) |
| 状态机故障注入覆盖 | ✅ | test_job_stage.py / test_job_state_machine.py 全绿 |

**下一步**：
- Phase 4：Mutation、Fuzzing、跨语言适配器（长期计划第 13-18 周）
- 继续执行 SPEC_PROOF_LONGTERM_PLAN.md 的分阶段计划

**证据文件**：
- `agent/nodes/contract_review.py`（新增，120 行）
- `tests/unit/test_contract_review.py`（新增，8 项）
- `agent/graph.py`（修改：节点注册 + 边）
- `agent/job_stage.py`（修改：STAGE_STATUS 映射）
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md`：追加 #428