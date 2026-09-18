# SpecProof — 用证据验收代码变更

SpecProof 做两件事：**让 AI 按需求改代码；独立检查一次变更是否符合需求。**

- **AI 开发**：描述需求 → 模型生成计划 → 你批准 → 修改文件、运行检查 → 审阅差异。
- **变更验收**：提供 Git 仓库、前后版本和需求文件 → 执行可用检查 → 查看覆盖情况、风险和证据。

Spec 是需求，Proof 是验证需求的证据。它适合需要评审 AI 代码、追踪回归和留存交付依据的开发团队。

## 启动

需要 Python 3.12+、Node.js 18+ 和 Docker Desktop。首次安装：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
pwsh scripts/start_local.ps1
```

打开 [本地工作台](http://localhost:5173)。登录凭据由启动脚本显示；本地脚本默认 `specproof-local-demo-key`。它只用于本机工作区访问，不是模型密钥。

脚本会启动数据库、队列、Worker、API 和前端，应用数据库迁移并创建标有“演示”的示例记录。再次执行不会重复创建。修改服务端代码后使用 `pwsh scripts/start_local.ps1 -Restart`；停止使用 `pwsh scripts/stop_local.ps1`。

## 接入真实模型

进入 **模型连接**，填写模型服务商的信息并保存，再点 **测试连接**。当前已实测的组合：

| 配置 | 值 |
|---|---|
| 服务地址 | `https://ynynzyy.xyz/v1` |
| 模型 | `gpt-6-astra` |
| 接口协议 | Responses API |
| 推理强度 | `max` |

API Key 保存在服务端被 Git 忽略的 `.local/llm.json`，不会返回给浏览器，也不保存在浏览器本地存储。部署环境也可通过 `LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / LLM_PROTOCOL / LLM_REASONING_EFFORT` 配置；环境变量优先时，页面明确显示只读。模型设置属于部署级配置，由部署管理员管理。

“已配置”表示信息已保存；只有真实连接测试成功才表示服务可用。调用会消耗模型额度，任务耗时取决于模型、推理强度和项目范围。

## 从哪开始

| 你要做什么 | 入口 | 操作 |
|---|---|---|
| 先理解产品 | 上手指南 | 无需登录，查看流程、案例与结果说明 |
| 让 AI 修复或实现功能 | AI 开发 → 新建任务 | 填服务端能访问的仓库路径和需求，生成计划后审批 |
| 检查已有代码变更 | 变更验收 → 新建验收 | 填仓库、Base、Head 和需求文件路径 |
| 审阅交付 | 任务详情 / 代码差异 / 检查结果 | 查看实际变更、失败项和没有执行的检查 |
| 排查连接问题 | 模型连接 / 服务状态 | 区分模型不可用和本地基础设施故障 |
| 管理团队 | 团队与权限 / 用量与账单 | 需要启用多租户及对应存储、权限配置 |

需求可以这样写：

```text
修复 double 函数，使它返回输入的两倍。
验收: 正数、负数和零的现有测试全部通过。
禁止: 修改或删除测试。
影响: calc.py test_calc.py
```

AI 开发在当前目录执行，批准前不会修改代码。Base/Head 是独立验收的版本范围。开发完成表示执行结束，**不等于**独立验收通过或自动合并。

## 如何读结果

- `VERIFIED`：有实际覆盖且本次执行的检查通过。
- `BLOCKED`：存在风险、检查未通过或覆盖不足，需查看证据后处理。
- `FAILED`：执行环境或管线失败，不能据此判定代码正确。
- `UNVERIFIED`：某条需求缺少足够证据。
- “演示”：预置示例，用于理解页面，不是当前仓库的真实验证结果。

Verify 的现有检查能力主要围绕 Java/Spring 后端及仓库提供的检查器。任意语言、任意自然语言需求都能自动验收，仍不是当前承诺。不能编译为可执行检查的需求必须呈现覆盖不足。无构建配置时检查可以跳过，跳过不算通过。

## 本轮真实验证

2026-09-18：指定网关与模型的普通回复、流式文本、JSON、工具调用和工具结果续接已通过。网页测试连接通过。在独立 Python 测试仓库中，真实模型生成 3 步中文计划，审批后把 `return x / 2` 改为 `return x * 2`，保持测试不变，测试与类型检查通过；无构建配置的构建检查标为跳过。它证明该链路可执行，不代表所有项目都能自动完成。

详见 [本轮改进与实测记录](docs/operations/PRODUCT_REFRESH_2026-09-18.md)。历史基准、架构图和原能力声明保留于 [历史技术记录](docs/operations/TECHNICAL_CAPABILITIES_HISTORY.md)，不能直接作为当前部署或商业 SLA。

## 开发与运维

前端是 `apps/web` 的 React / TypeScript / Vite；API 在 `api/`；AI 开发循环在 `craft/`；Verify 管线在 `agent/`；存储在 `storage/`；模型适配在 `providers/`。

```powershell
# 前端编译与类型检查
cd apps/web
npm run build
# 定向运行受影响的前端测试
npm run test -- src/pages/NewVerification.test.tsx
# Python 在项目根目录运行受影响的测试
.venv/Scripts/python -m pytest tests/unit/test_product_setup.py
```

完整环境要求见 [本地体验](docs/operations/LOCAL_EXPERIENCE.md)，架构见 [架构说明](docs/architecture/ARCHITECTURE.md)。
