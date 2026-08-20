# case-go-01-validation-inverted — Go 校验逻辑反转

Go 镜像 golden-cases/case-17-logic-inversion: Base 的 `EmailAllowed()`
返回 `!blockedDomains[...]` (黑名单域名被拒); Head 反转判定
`blockedDomains[...]` (黑名单被放行、普通域名被拒)。diff 仅一个 `!`,
静态读 diff 无法判定, 必须执行才能暴露 (execution-only)。

## 布局

    src/base/   go.mod + validator.go + validator_test.go — 判定正确
    src/head/   同一项目, validator.go 判定反转 (测试文件相同)
    spec.md / ground-truth.json / scenario.json

## 案例意图与预期检测路径

- 期望检出: BLOCKER, contract GO-VALID-01, evidence differential_test
  (ground-truth.json, should_detect=true — 仅当执行被支持时的期望)。
- 检测路径 (Go 适配器落地后): 差分执行 `go test` — 同一测试 base 2/2 通过、
  head 2/2 失败 (两个断言同时反转) → base_pass_head_fail → BLOCKER。
- 单字符 `!` 反转对静态分析不可判定, 差分执行是唯一诚实证据 (与 case-17 同口径)。

## 真实运行记录 (2026-08-20)

| 命令 | 结果 |
|---|---|
| go test (base/head) | **未运行** — 本机 PATH 无 Go 工具链 (实测 NOT FOUND) |
| registry.get(RepositorySnapshot) | AdapterNotImplemented (Go adapter planned, no executor wired) — 管线 fail-closed |

## 诚实边界

- SpecProof 管线对 Go 的执行 **未支持** (experiments/adapters.py Go 行 =
  planned)。本样本不声称任何检出结果。
- 源码依仓库 scripts/aider_sample toycalc-sum 的极简风格手写, **未被执行验证**;
  在有 Go 工具链的环境按布局直接 `go test` 即可验证场景语义。
