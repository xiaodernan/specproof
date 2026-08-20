# Job 创建白名单 (Backlog #8)

> 状态: 已实施并验证 (2026-08-20)。范围: 两条 Job 创建路径的输入面审计 + 缺失白名单加固。
> 涉及文件: api/routes/jobs.py (审计, 无需改动), api/routes/agent_console.py (加固),
> tests/unit/test_job_whitelist.py (新建), 本文档 (新建)。

## 1. 威胁模型与拒绝语义

验证 API 绝不能成为远程执行面: 客户端提交的 payload 里, 任何可解释为执行指令的
字段 (任意 command / shell / env / docker / 容器 / 输出路径 / tool 参数) 都必须无法到达
worker。两条创建路径都采用同一语义:

- **未知字段一律 422 拒绝** (fail-closed), 不是静默丢弃。拒绝发生在 pydantic
  model_validator(mode=before) 层, 早于任何持久化调用。
- 拒绝响应走 §8.1 错误信封: HTTP 422 + error.code = VALIDATION_FAILED +
  error.retryable = false, legacy detail 列表保留并**点名违规字段**
  (Value error, Unknown field(s): command, env)。
- 命令/env/docker 类字段**没有预注册集合** (两条路径的合法字段里根本不存在这类字段),
  因此任何此类字段都作为未知字段被拒 — 预注册集合为空本身即最严白名单。
- depth 是 /jobs 唯一的枚举型执行参数, 以正则锚定 (^FAST$) 锁定; 实测
  fast / DEEP / FULL / FAST 后接换行符 / 空串 全部 422。

## 2. 路径 1 审计: POST /jobs (api/routes/jobs.py)

现状 (审计时已存在, 本次未改动):

- JOB_CREATE_ALLOWLIST = frozenset({repo_path, base_ref, head_ref, spec_path, depth})
- JobCreateRequest._reject_unknown_fields (mode=before): 任何不在白名单内的键
  (含非字符串键) 触发 ValueError → FastAPI RequestValidationError → 422 VALIDATION_FAILED。
- 路由只把白名单字段构造成 job dict 后写入 MySQL outbox; worker 收到的 dict 键集合
  与白名单完全一致。

**结论: 完整且 fail-closed。** 实测 (pydantic 2.13.4) 未知字段全部 ValidationError,
非对象 payload (JSON 数组) 同样 422。不需要改动。白名单是否 fail-closed: 是 (拒绝,
非丢弃)。

## 3. 路径 2 审计: POST /agent/jobs (api/routes/agent_console.py)

现状 (加固前, 实测复现):

- AgentJobCreateRequest 只有 repo_path / spec_text / task_name / auto_start
  四个字段, 但**没有未知字段校验** — pydantic 默认 extra=ignore,
  未知字段被**静默丢弃**。
- 实测 (加固前): POST /agent/jobs 带 command / env / docker_image /
  container / tool / output_path 等字段返回 **202**, 字段无声消失。
  这正是被禁止的 "静默吞掉危险字段"。
- 调用方盘点 (回归安全): SPA apps/web/src/api.ts、VSCode 插件 ide/vscode/src/client.ts、
  scripts/seed_demo.py 都只发送白名单内字段。

加固 (本次改动, api/routes/agent_console.py):

- 新增 AGENT_JOB_CREATE_ALLOWLIST = frozenset({repo_path, spec_text, task_name, auto_start})。
- AgentJobCreateRequest 新增 _reject_unknown_fields (mode=before), 与 /jobs
  完全相同的拒绝语义; 原有的 _check_run_shape (mode=after) 不受影响
  (before 先于 after 执行)。
- 实测 (加固后): 同一批恶意 payload 全部 **422 VALIDATION_FAILED**, 且 store 无任何
  持久化记录 (拒绝, 非丢弃); 合法 payload (含 auto_start=true 且 repo+spec 齐全)
  保持 202, 运行时收到与白名单一一对应的参数。

## 4. 相邻路径说明 (审计附注, 不在本次改动范围)

- **POST /webhooks/github** (api/routes/webhooks.py): 第三方创建路径, 但不解析客户端
  任意字段 — job dict 由签名校验过的 GitHub payload 中固定提取的 ref/clone_url 构造,
  其余字段服务端硬编码。无注入面。
- **ApprovalRequest** (/agent/jobs/{id}/approve): 非 Job 创建路径, 未加白名单;
  如需统一收紧可作为后续 backlog。
- **worker 执行面** (sandbox/runner.py 等): 本次只审计创建输入面, 执行面沙箱不在
  本 backlog 范围。

## 5. 测试清单 (tests/unit/test_job_whitelist.py, 44 项)

恶意 payload — 两条路径各 14 种变体, 全部必须 422 且零持久化:

| 变体类别 | 示例 payload 字段 | /jobs | /agent/jobs |
|---|---|---|---|
| 任意命令 | command: calc.exe / [cmd.exe, /c, whoami] / shell: powershell ... | 422 | 422 |
| env 注入 | env: {LLM_API_KEY: ...} / environment: [MYSQL_PASSWORD=...] | 422 | 422 |
| docker 覆盖 | docker_image / docker: {privileged: true} / container: {image: ...} | 422 | 422 |
| 输出路径 | output_path / output_dir | 422 | 422 |
| tool 类 | tool: bash / tools: [{type: shell}] | 422 | 422 |
| 其他注入 | extra_args: [--privileged] / unknown_field: x | 422 | 422 |

附加负例: 错误信封点名违规字段; 非对象 payload 422; depth 枚举外值 422;
模型级直接校验 (含非字符串键) 抛 ValidationError。

回归正例 (合法 payload 不受影响): /jobs 全字段 202 且持久化键集合恰好为白名单;
depth 缺省 → FAST; /agent/jobs 全字段 202 + detail 往返一致; auto_start=true
(repo+spec 齐全) 202 且运行时收到完全相同的 4 个参数; auto_start 运行形状规则
(只给 repo 不给 spec → 422) 保持原语义。

加固前实测 (红): agent 侧 16 项失败 — 恶意 payload 返回 202; 加固后 (绿): 44/44 通过。

## 6. 门禁结果 (真实运行, 2026-08-20)

| 门禁 | 命令 | 结果 |
|---|---|---|
| lint | python -m ruff check api/routes/agent_console.py api/routes/jobs.py tests/unit/test_job_whitelist.py | All checks passed (exit 0) |
| type | python -m mypy --strict api/routes/agent_console.py api/routes/jobs.py | Success: no issues found in 2 source files (exit 0) |
| 单元 | python -m pytest tests/unit/test_job_whitelist.py -q | 44 passed (exit 0) |
| 相关既有 | python -m pytest tests/unit/test_job_whitelist.py tests/unit/test_api_jobs.py tests/unit/test_agent_jobs.py tests/unit/test_agent_console_api.py tests/unit/test_agent_runtime.py tests/unit/test_webhook_endpoint.py -q | 171 passed (exit 0, 113.50s); 明细: whitelist 44 + api_jobs 13 + agent_jobs 69 + agent_console_api 27 + agent_runtime 11 + webhook_endpoint 7 |
| 测试文件 mypy | python -m mypy --strict tests/unit/test_job_whitelist.py | Success: no issues found in 1 source file (exit 0) |

说明: mypy 配置 (pyproject.toml) 排除 tests/ 目录, 但显式传文件名时仍会检查,
结果同样通过 — 测试文件类型检查不是仓库既有门禁的一部分, 此处仅作附加验证。

## 7. 允许文件清单

- [改动] api/routes/agent_console.py — 新增 AGENT_JOB_CREATE_ALLOWLIST + before 校验器
- [新建] tests/unit/test_job_whitelist.py — 44 项白名单测试
- [新建] docs/design/JOB_CREATION_WHITELIST.md — 本文档
- [未改动] api/routes/jobs.py — 审计确认已 fail-closed, 无需加固

未触碰门面三文档、未执行任何 git 命令、未写入任何 API key。
