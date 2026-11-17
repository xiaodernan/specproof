# Investigation Dig

**verdict: EVIDENCE-GATHERED** · generation_time_ms 52904

question: 本仓库做了什么？

## Agents

| name | outcome | duration (s) | tokens |
|---|---|---|---|
| investigate_explorer | ok | 37.4s | 6309 |
| investigate_tester | ok | 24.0s | 6351 |
| investigate_security | ok | 4.5s | 4547 |

## Findings

- **explorer** — SpecProof 是一个用于验收 AI 生成代码变更的独立验证平台：一侧让 AI 根据需求修改代码，另一侧收集测试、差异和运行结果作为证据，判断变更是否符合需求。后端看起来是 Python 3.12+ 技术栈，基于 FastAPI、LangGraph、Pydantic 等实现工作流、模型接入和验收服务，并集成 Git、Docker、Redis、数据库、对象存储及 Elasticsearch 等基础设施。前端是 TypeScript/TSX 应用，入口从 README 提到的本地 `http://127.0.0.1:5173/` 开始，提供“巡览”“史诗”“铁证词典”等工作台功能。仓库的主要模块包括 AI 开发流程、变更验收与证据判定、沙箱/检查执行、多租户身份、Merge Certificate 签名，以及覆盖这些行为的 Python 单元测试；具体前端框架和精确入口文件仅凭当前事实包无法确定。
- **tester** — 我先根据工作区提供的测试清单识别测试分层，并核对这些测试描述实际覆盖的系统行为；对测试清单未明确支持的结论，我会标注为无法确认。从现有工作区事实和测试描述可以确认，本仓库主要是在做一个“代码变更验证与安全验收平台”，大致包含以下能力：

- 对代码变更进行 Base 与 Head 的差分验证。
- 生成并执行测试，比较变更前后的测试结果、编译状态、退出码、标准输出和错误输出。
- 在沙箱中运行生成的测试，并记录 Maven 或沙箱执行失败。
- 分析失败是否真正涉及本次变更的代码，区分“Head 失败”与“该变更导致失败”，避免把无关失败判定为回归。
- 对变更执行安全扫描，并给验收发现标注严重性。
- 将验收结果和严重性信息展示在 Web UI 中。

从测试中能明确识别出的测试 lane 有：

1. Unit lane

路径：`tests/unit/`

覆盖内容：单元级规则和数据流验证，包括失败归因、运行记录、严重性定义等。当前给出的测试都属于这一目录，但不能据此确认是否存在其他正式测试 lane。

2. Regression attribution lane

代表测试：`test_a_regression_that_never_names_the_changed_code_is_unattributed.py`

覆盖行为：当测试在 Head 上失败、但失败信息没有提及或明确指向本次变更的代码时，将该失败记录为“未归因”证据。它不会据此改变最终 verdict、严重性或置信度，避免把“Head 失败”直接误判为“本次变更导致的回归”。

3. Reused Head run / sandbox-error lane

代表测试：`test_a_reused_head_run_carries_its_sandbox_error.py`

覆盖行为：复用生成阶段已经执行过的 Head 测试结果时，必须保留原始沙箱错误；健康运行也应保持稳定的数据结构。该 lane 防止沙箱失败被错误解释成“生成测试没有执行任何测试”，并验证生产端记录错误、消费端正确展示错误。

4. Acceptance severity parity lane

代表测试：`test_accept_severity_parity.py`

覆盖行为：安全扫描器、`craft` 验收逻辑和 Web UI 使用同一套验收严重性词汇和映射。测试会从源码中解析扫描规则、严重性字面量、阻断常量以及 UI 的 `ACCEPT_SEVERITY_CN` 定义，确保后端产出的严重性能够被前端一致解释和展示。

无法确认的部分：

- 无法仅凭当前事实确认仓库的具体产品名称、完整 CLI/API、部署方式或支持的编程语言范围。
- 无法确认是否有独立的 integration、e2e、acceptance 或 CI lane；目前明确看到的是 `tests/unit/` 及其中针对差分验证和安全验收的专题测试。
- 无法确认 `craft` 是独立命令行工具、流水线阶段，还是仓库内部模块；只能确认它参与安全扫描结果和严重性处理。
- **security** — 仅凭当前提供的事实包，无法判断本仓库做什么。它只列出了 `.env` 和 `.env.example` 两个环境文件名；认证相关的静态检查已明确排除，因此不能据此推断仓库功能或认证实现。
