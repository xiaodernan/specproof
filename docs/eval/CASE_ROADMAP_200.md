# 200 案例扩展路线表 (CASE_ROADMAP_200)

依据: 工业化指南 §A 任务 12 + 主计划 §9.2 (200 金案例, holdout 隔离, 每案例 expected evidence 先行)。
当前: 100 案例 (P6_CASES 表驱动, scripts/build_golden_scenarios.py)。本表为 100→200 的案例族扩展路线, 每族先写 expected evidence 再写实现。

## 扩展分配 (新增 100, 按契约族)

| 族 | 现有 | 新增 | 覆盖点 (expected evidence 先行) |
|---|---|---|---|
| AUTH/权限 | ~10 | +10 | OAuth scope 收窄/角色提升/服务账号越权/注解顺序/多角色组合 (evidence: 401/403 双版本 + H2 行不变) |
| TRANSACTION/ATOMICITY | ~8 | +10 | 半提交/回滚后副作用/嵌套事务/隔离级别 (evidence: DB dump 前后 + 事件计数) |
| CONCURRENCY/幂等 | ~8 | +10 | 乐观锁移除/重复请求/竞态写/幂等键缺失 (evidence: 并发探针 + 副作用账本) |
| EVENT/MQ | ~12 | +10 | 重复发布/错误 routing key/时间戳置空/重试重复 (evidence: 探针计数+载荷捕获 — W36 机制复用) |
| CACHE/一致性 | ~8 | +8 | TTL 失效/写回丢失/key 前缀变更/穿透 (evidence: Redis 快照) |
| BOUNDARY/NPLUSONE/TEST_STRENGTH | ~15 | +12 | 边界/循环查询/断言弱化 (evidence: 静态 diff + 计数探针) |
| 注入/对抗 | ~15 | +15 | README/注释/schema/构建文件/分支名/commit message 注入 (evidence: 0 finding 断言) |
| 跨语言 (新族) | 0 | +15 | Python/TS/Go 各 5 (evidence: 对应适配器执行 — 依赖 W57b Python 适配器) |
| 环境故障 (新族) | ~5 | +10 | 构建失败/依赖缺失/沙箱超时/输出洪水 (evidence: 诚实 FAILED/降级分类) |

## holdout 与防过拟合

- W71 holdout manifest 落地后, 每族预留 20% 作为 holdout, 开发期不跑, 发布前一次性重跑并报告。
- 每案例必须: spec/base/head/期望契约/期望 severity/期望 evidence_type/是否阻断/最小回放命令/人工解释。
- 生成仍走 build_golden_scenarios.py 数据表 (单行一案例), 禁止手写案例目录散落。

## 执行顺序

1. 等 W48b (段1 修复) 与 W57b (Python 适配器) 落地;
2. 派"案例扩展车道": 按上表新增 100 案例 (数据表 + 生成 + 全量 eval 复跑);
3. 发布前: holdout 一次性重跑 + 全量报告 (Recall/Precision/归因/回放率/延迟 p50-p95 全部原始结果)。
