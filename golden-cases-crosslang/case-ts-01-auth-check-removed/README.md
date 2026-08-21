# case-ts-01-auth-check-removed — TS 鉴权检查被移除

TypeScript 镜像 golden-cases/case-01-auth-bypass: Base 的 `changeEmail()`
先经 `isAuthorized(user, "user")` 鉴权, 未认证调用返回 "UNAUTHORIZED";
Head 移除该检查, 未认证调用直接改邮箱。

## 布局

    src/base/   完整小项目 (package.json + tsconfig.json + src/auth.ts
                + test/auth.test.ts) — 鉴权存在
    src/head/   同一项目, auth.ts 移除鉴权块 (其余相同; 测试文件相同)
    spec.md / ground-truth.json / scenario.json

零依赖 (node --test 内置), 无需 npm install / 网络 / API key。

## 案例意图与预期检测路径

- 期望检出: BLOCKER, contract TS-AUTH-01, evidence differential_test
  (ground-truth.json, should_detect=true — 仅当执行被支持时的期望,
  当前管线不执行, 见下)。
- 检测路径 (适配器落地后): 差分执行 — 同一不变量测试在 base 全绿、
  在 head 红 (base_pass_head_fail) → BLOCKER。
- 静态 diff 可看到被移除的 guard 块 (次级信号); 金标准证据仍是差分执行,
  与 case-01 口径一致。

## 真实运行记录 (2026-08-20, 直接工具链, 非管线检出)

| 命令 | 对象 | 结果 |
|---|---|---|
| node --test test/auth.test.ts | src/base | 2 pass / 0 fail, exit 0 |
| node --test test/auth.test.ts | src/head | 1 pass / 1 fail, exit 1 — 真实断言: actual 'EMAIL_CHANGED:attacker@evil.com', expected 'UNAUTHORIZED' |
| tsc --noEmit (仓库 vendored tsc) | base/head | 补 src/types.d.ts 离线垫片后均 exit 0 (首跑 TS2307: 样本不捆 @types/node) |
| registry.get(RepositorySnapshot) | base/head | AdapterNotImplemented (Node adapter planned, no executor wired) — 管线 fail-closed |

## 诚实边界

- SpecProof 管线对 TypeScript 的执行 (差分/测试生成) **未支持**
  (experiments/adapters.py Node 行 = planned)。本样本不声称任何管线检出结果。
- 上述 node/tsc 运行只证明缺陷场景语义真实, 是离线复现材料, 不是检出报告。
