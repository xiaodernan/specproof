# golden-cases-crosslang — 跨语言最小案例样本 (offline)

backlog #6 (docs/plan/W170_BACKLOG.md): 跨语言案例样本 TS/Go。Python 已在
W78/W105 落地 (experiments/adapters.py PythonAdapter + experiments/minimize.py
ddmin); 本目录交付 TypeScript 1 例 + Go 1 例的**离线、格式就绪**样本。

## 样本清单

| case | 语言 | 缺陷场景 | 镜像的 Java 案例 | 管线执行 | 直接工具链验证 |
|---|---|---|---|---|---|
| case-ts-01-auth-check-removed | TypeScript (node --test, 零依赖) | Head 移除 changeEmail 的鉴权检查, 未认证调用被接受 | case-01-auth-bypass | **unsupported** | ✅ 真跑 (见下) |
| case-go-01-validation-inverted | Go (go test) | Head 反转黑名单判定 (单字符 !) | case-17-logic-inversion | **unsupported** | ❌ 本机无 Go 工具链, 未跑 |

## 格式 (与 golden-cases/ 三件套一致)

每例包含 `spec.md` (自然语言要求 + 期望检出) / `ground-truth.json`
(期望检出 + 诚实执行状态) / `scenario.json` (version 2.0,
base_ref/head_ref, 与 cli/specproof/commands/eval.py 读取的字段一致)。

**关键差异 (诚实标注)**: `base_ref`/`head_ref` **没有在任何仓库物化** —
scripts/build_golden_scenarios.py 只构建 Java demo 案例。本样本以
`src/base` 与 `src/head` 两个目录携带两个修订, 每个修订是独立可跑的小项目。
**不要** 用 `specproof eval --cases golden-cases-crosslang --repo .` 运行
(会把 Java demo 仓库的 base/head 当作执行对象, 产生与本案例无关的结果)。

## 管线执行状态: unsupported (真实检测, 2026-08-20)

experiments/adapters.py 兼容矩阵中 JS/TS (npm/Jest) 与 Go 均为
`规划 (planned)`, detect 抛 AdapterNotImplemented。用样本目录真实调
`registry.get(RepositorySnapshot(...))` 全部 4 个目录 (TS base/head,
Go base/head) 均返回:

    AdapterNotImplemented: unsupported repository — no execution adapter
    matched: ... Node adapter is planned (compatibility matrix
    status=planned); no executor is wired; ... Go adapter is planned ...

即: 差分执行 / 测试生成对 TS/Go **尚未接线**, 本目录不声称任何管线检出结果。

## 直接工具链验证 (不是 SpecProof 管线, 只为证明缺陷场景语义真实)

- **TS** (host: node v24.17.0, npm 11.13.0):
  - `node --test test/auth.test.ts` @ src/base → **2 pass, 0 fail, exit 0**;
  - 同命令 @ src/head → **1 pass, 1 fail, exit 1** (真实断言:
    actual 'EMAIL_CHANGED:attacker@evil.com', expected 'UNAUTHORIZED');
  - `tsc --noEmit` (仓库自带 apps/web/node_modules/typescript):
    首次报 TS2307 (样本零依赖, 无 @types/node) → 补离线类型垫片
    src/types.d.ts 后 base/head 均 **exit 0**。
- **Go**: 本机 PATH 无 Go 工具链 (2026-08-20 实测) → **未执行**。
  validator.go/validator_test.go 依仓库 toycalc-sum 风格手写, 未经验证,
  README 内如实标注。

## 诚实边界

1. 以上直接运行只验证「缺陷场景语义」, 不是 SpecProof 检出结果; 检出结果在
   Node/Go 适配器落地前不存在, 绝不伪造。
2. scenario 引用未物化; 样本是格式就绪的离线资产。
3. 样本零依赖、零网络、零 API key, 可离线复跑。

## 门禁证据 (真实运行)

`python -m pytest tests/ -k "adapter or polyglot" -q`:
- 第一次运行 (22:03 前后) 收集期中断: craft/loop.py:2371 IndentationError
  (该文件 mtime 2026-08-20 22:04:22, 两次运行之间被并发车道改写; 本交付只新增
  文件、不触碰任何既有文件, 与该错误无关);
- 重跑 (22:05:39): **60 passed, 2541 deselected in 6.84s** ✅。
另跑 `tests/integration/test_phase_acceptance.py` 两例不变式 (2 passed),
确认 golden-cases/ 的 100 案例不受本目录影响。

## 复跑命令

    node --test test/auth.test.ts      # 在 case-ts-01-*/src/{base,head} 下
    node <repo>/apps/web/node_modules/typescript/bin/tsc --noEmit -p src/base
