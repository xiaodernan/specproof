# DeepSeek V4 Pro 深度适配 (Provider 层)

日期: 2026-08
范围: providers/ 全部 + .env.example + 本文件 + tests/unit/test_providers_dsv4.py
状态: 已实现, wire 级 mock 验证 (见第 6 节诚实声明)

本文件把平台 LLM 调用对 DeepSeek V4 Pro (经 OpenAI-compatible 网关) 的适配
决策固化下来: 模型画像、适配决策表、预算模型、提示词分层, 以及它们与
ADR-012 / ADR-017 的关系。所有行为变更都保证向后兼容: 现有调用点不传新参数
时, 请求形态与旧实现逐字节一致 (由 tests/unit/test_providers_dsv4.py 锁定)。

---

## 1. 模型画像 (工作前提)

| # | 特性 | 对本项目的影响 |
|---|---|---|
| 1 | 网关 always-on thinking: 每个响应都带 reasoning_content | 思考 token 与延迟是常驻成本; 响应解析必须把 reasoning_content 单独承载, 绝不混入 content |
| 2 | strict tool calls 返回 HTTP 400 | 不能用 tool_choice="required"; 工具调用走 JSON Action Envelope 降级 (保留并强化) |
| 3 | JSON output mode 可用, 但偶发空 content | response_format 可用时照发; 空 content 重试后回退 Schema Parser (调用方现有容错保持不变) |
| 4 | 大上下文 + 自动上下文缓存 (KV cache), 命中 token 计费折扣 | 提示词必须"稳定前缀在前, 变量数据在后"以最大化缓存命中 |
| 5 | usage 含 reasoning 相关 token 与 prompt_cache_hit_tokens / prompt_cache_miss_tokens | 按网关实际字段名解析, 缺失时诚实跳过, 不伪造 0 |
| 6 | 429 限流带 Retry-After header | 重试必须尊重 Retry-After, 重试次数受 LLM_MAX_RETRIES 约束 |
| 7 | 思考模式正确用法 | 规划/Judge/诊断类推理任务开思考; 工具循环/机械步骤关思考 (省 token 省延迟) |

## 2. 适配决策表

| 项 | 决策 | 实现位置 | 验证方式 | 降级路径 |
|---|---|---|---|---|
| reasoning_content 承载 | 只进 LLMResponse.reasoning_content (内存), 不进 content / tool_calls / JSON 解析路径, 不落盘 (ADR-017) | providers/openai_compatible.py _to_llm_response (message 级 + choice 级回退) | test_reasoning_content_* 3 例 | 字段缺失则 reasoning_content=None, 其余路径零影响 |
| usage 解析 | prompt/completion/total 恒存在; prompt_cache_hit_tokens / prompt_cache_miss_tokens / reasoning_tokens (completion_tokens_details.reasoning_tokens 或顶层) 存在才解析, 缺失跳过 | providers/openai_compatible.py _parse_usage | test_parse_usage_* 4 例 + roundtrip 1 例 | usage=None 则核心三项记 0, 可选字段缺省 |
| 429 限流 | tenacity 重试, 429 优先按 Retry-After 秒数等待, 缺失或 HTTP-date 回退指数退避 (60s 封顶); SDK client 建为 max_retries=0, tenacity 是唯一重试者 (避免双重重试) | providers/openai_compatible.py _create_chat_completion / _retry_after_seconds / _wait_retry_after_or_exponential | test_429_* 3 例 + wait/parse 3 例 | 重试耗尽则原样抛 RateLimitError (上层已有 fallback) |
| 重试次数语义 | LLM_MAX_RETRIES 含义保持"最多重试 N 次" (默认 2, 总尝试 N+1); 构造参数 max_retries 可覆盖 | __init__ + _env_int | test_429_retry_count_reads_llm_max_retries_env | 环境变量非法则回退默认 2 |
| thinking 控制 | chat()/chat_stream() 的 thinking 从 bool 扩展为 bool 或 dict: False/None=不发 (旧行为), True=type enabled (旧行为), dict=原样透传 (如 type disabled / type auto) | providers/base.py + openai_compatible.py | test_thinking_true_still_sends_enabled_body / test_thinking_dict_and_opts_passthrough / test_chat_without_new_params_keeps_old_request_shape | 网关能力位 thinking=false 则不发 extra_body (旧行为) |
| 网关专属参数逃生门 | chat()/chat_stream() 新增 opts: dict 合并进 extra_body 且后合并 (显式覆盖自动生成的 thinking) | openai_compatible.py | test_thinking_dict_and_opts_passthrough | opts 缺省 None 则请求形态不变 |
| 缓存友好提示词 | 稳定前缀在前 (SYSTEM_BLOCK + 任务块), 变量数据在后, 前缀逐字节稳定; envelope 块可选尾部 | providers/prompt_templates.py assemble / stable_prefix_identical / verify_variables_after_prefix | test_assemble_* 4 例 + resolve_thinking 2 例 | 未知模板则 KeyError (响亮失败, 不静默) |
| 思考分层 | 模板标注 thinking_on; LLM_THINKING_MODE=plan_only (可选 auto/off) 用 resolve_thinking 解析 | providers/prompt_templates.py | test_templates_thinking_flags / test_resolve_thinking_modes | 非法 mode 则 ValueError |
| 预算核算 | TokenBudget 账本: 记录 prompt/completion/reasoning/cache_hit/miss; 可配置成本权重; 调用前 check() 超限抛 BudgetExceeded (可捕获, 不静默); record() 先入账后抛错, 超支留痕; to_report() 可序列化 | providers/budget.py | test_budget_* 4 例 | 权重缺省则用默认权重 (见第 3 节), 接入真实端点后必须用价格卡覆盖 |
| 能力探测 | 新增第 11 项 reasoning_content 能力位: 无 thinking 请求的普通 chat 仍返回 reasoning_content 则为 true; 探不到为 false, 不伪造; rate_limit_headers 位早已存在, 原样保留 | providers/capability_probe.py _check_reasoning_content + probe_result.py CAPABILITY_KEYS | test_probe_* 3 例 + keys 1 例 | 网关不可达则全部能力位 false (既有行为) |
| JSON Action Envelope | 保留原注入文本, 尾部追加 prompt_templates.JSON_ACTION_ENVELOPE_BLOCK 作为唯一权威契约块 (强化 = 单一事实来源) | openai_compatible.py _inject_tool_prompt | test_providers.py / test_baseline.py 既有套件 | 网关有 tool_calls 则不发注入 (既有行为) |

## 3. 预算模型

口径 (providers/budget.py):

- 账本按"charge 单位"记账, 默认 1 token = 1 单位; 权重可配置
  cost_weights = {prompt, completion, reasoning, cache_hit, cache_miss}。
- 默认权重 (诚实占位, 接真实端点后必须按价格卡覆盖):
  - prompt = 1.0
  - completion = 1.0
  - reasoning = 1.0 (reasoning token 计入预算: thinking 打开的任务,
    其 reasoning token 与 completion 一样占预算, 且消耗 max_tokens 预算,
    因此机械步骤默认关思考)
  - cache_hit = 0.1 (KV 命中折扣), cache_miss = 1.0
- 记账单位来源: LLMResponse.usage 的 prompt_tokens / completion_tokens /
  reasoning_tokens / prompt_cache_hit_tokens / prompt_cache_miss_tokens。
- 执行序: 调用前 check(prompt_tokens, ...) 预估校验, 超限抛
  BudgetExceeded (带 limit/used/charge, 可捕获可上报); 调用后
  record(usage, label) 入账: 先追加账目 (证据链诚实留痕) 再判超限,
  超限同样抛 BudgetExceeded。
- to_report() 输出 JSON 可序列化快照: 限额/已用/剩余/权重/逐条账目,
  报告里可完整复现预算消耗证据链。
- LLM_BUDGET_TOKENS (示例 500000) 由调用方读取并构建 TokenBudget;
  节点层接线属于其他工作流, 不在本次范围内。

## 4. 提示词分层

模板库 providers/prompt_templates.py: SYSTEM_BLOCK (稳定系统指令, 固定首位),
任务块 (稳定), 变量数据 (按 key 排序后拼入), 可选 JSON Action Envelope
尾部。变量段按 key 排序, 保证同任务两次构建前缀逐字节相同
(stable_prefix_identical 自检)。

| 任务 | 模板 | thinking_on | LLM_THINKING_MODE=plan_only 下 | 依据 |
|---|---|---|---|---|
| 验证规划 | plan | True | 开 | 规划类推理, 思考即产物 |
| Review Court 判决 (prosecutor/defender/judge) | judge | True | 开 | Judge 类推理 |
| 回归根因诊断 | diagnose | True | 开 | 诊断类推理 |
| 需求转合约编译 | contract_compile | False | 关 | 结构化抽取, 机械步骤 |
| diff 对照审查 (baseline) | baseline | True | 关 (保守档; auto 档才开) | 判定类但当前调用点未开思考, plan_only 保持现状 |

resolve_thinking(task, mode): off 则全关; plan_only (默认) 则仅
plan/judge/diagnose 开; auto 则跟随模板 thinking_on。工具循环与代码生成
(如 JUnit 反例生成, thinking=False) 一律关思考。

## 5. 与 ADR 的关系

- 主引用 [ADR-012 (第三方 OpenAI-Compatible 网关兼容策略)](../adr/ADR-012.md):
  本文件是 ADR-012 针对 DeepSeek V4 Pro 网关的深度落地: 能力探测从 10 项
  扩为 11 项 (新增 reasoning_content 位), 降级路径 (JSON Action Envelope、
  thinking 分场景开关、usage 诚实解析) 全部在 Provider 层完成, 业务节点
  不感知网关差异。
- [ADR-017 (LLM 私有推理不保存)](../adr/ADR-017.md): reasoning_content
  只在内存 LLMResponse 中, 不进 content、不进 tool-call/JSON 解析路径、
  不落盘; 预算账本只记 token 计数与结构化数字, 不记模型原文。

## 6. 诚实声明

- 本环境没有真实 DeepSeek V4 Pro Key; 全部验证按 wire 格式 mock 完成
  (transport stub 替换 AsyncOpenAI client 与 httpx.AsyncClient, 与
  tests/unit/test_baseline.py 同一约定; responses 库 0.26.2 不拦截
  httpx, 不可用)。测试 fixture 的假 key 一律用字符串拼接构造
  (tests/unit/test_baseline.py 同款修法), 满足
  tests/security/test_no_key_leak.py 的"源码内不得出现完整假密钥模式"规则。
- usage 字段名 (prompt_cache_hit_tokens / prompt_cache_miss_tokens /
  completion_tokens_details.reasoning_tokens) 按网关公开格式解析, 并做了
  顶层 reasoning_tokens 回退与 dict/对象双形态读取; 若真实网关字段名不同,
  解析器会诚实跳过 (缺失字段不进 usage), 由首次能力探测暴露差异。
- 接真实端点的第一步 = specproof probe (providers/capability_probe.py,
  现在 11 项): 先拿到 reasoning_content / rate_limit_headers /
  strict_tool_calls 等能力位的真实值, 再据此调整 thinking 策略与
  budget.py 的成本权重 (默认权重是占位值, 不是定价)。

## 7. 变更清单

- 修改: providers/openai_compatible.py (usage 解析 / tenacity+Retry-After /
  thinking+opts / envelope 强化), providers/base.py (签名与文档),
  providers/capability_probe.py (+reasoning_content 探测, 11 项),
  providers/probe_result.py (+CAPABILITY_KEYS 位), .env.example
  (+LLM_MODEL 注释 / LLM_THINKING_MODE / LLM_BUDGET_TOKENS)
- 新增: providers/prompt_templates.py, providers/budget.py,
  tests/unit/test_providers_dsv4.py (33 例), 本文件
- 未改动: providers/redaction.py (本工作流无需修改), agent/、cli/、
  storage/、sandbox/、infra/、demo/、golden-cases/ 一律未碰
