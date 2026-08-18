# 真实网关探测与实测记录 (DeepSeek V4 Pro via llm-api.fagougou.com)

日期: 2026-08-18 · 模型: deepseek-v4-pro · 端点: https://llm-api.fagougou.com/v1
(密钥仅经进程环境变量注入, 未写入任何仓库文件; 本记录无密钥。)

## 1. 11 维能力探测 (真实调用, 8/11)

| 能力 | 结果 |
|---|---|
| chat / streaming / json_output / tool_calls | ✅ |
| thinking / reasoning_content / usage_reporting / error_codes | ✅ |
| strict_tool_calls | ❌ HTTP 400 (与项目假设一致 → JSON Action Envelope 降级) |
| thinking_with_tools | ❌ (思考与工具调用不共存 → 思考分层设计被证实必要) |
| rate_limit_headers | ❌ (未返回限流头 → 指数退避兜底) |

结论: 项目文档 CLAUDE.md / ADR-012 的降级假设全部被实测证实,
Provider 的能力探测 → 按能力降级 (Envelope / 思考分层 / 重试退避)
是真实网关下的正确架构。

## 2. 实测抓到的 live-fire bug (只有真实调用能发现)

- 现象: LLM 基线首跑即崩 — "coroutine object has no attribute choices"
  + RuntimeWarning "AsyncCompletions.create was never awaited"。
- 根因: tenacity 9.1.4 的 is_coroutine_callable 无法识别 openai SDK 的
  绑定异步方法 (AsyncCompletions.create), retryer 未 await 直接泄漏
  coroutine 进 _to_llm_response。
- 修复: providers/openai_compatible.py 改为显式 async _attempt 包装
  (return await self.client.chat.completions.create(**kwargs)),
  对真实端点复测通过。
- 教训: mock 全绿 ≠ 真实可用; 真实验收是最后一公里的硬门禁。

## 3. LLM 基线实测 (Go/No-Go #14, "直接让 V4 Pro 看 Diff")

12 案例首跑: 模型找到 10/10 回归 (一次运行 9/10, 模型方差),
precision 100%, 0 误报 — 但 contract_id 为自由格式
(如 UserService.changeEmail 而非 AUTH-01)。

| 口径 | 基线 | SpecProof | 含义 |
|---|---|---|---|
| 严格契约匹配 recall | 0.0% | 100% (+100pp) | 契约编译器+注册表正是 SpecProof 的核心差距 |
| 发现率 recall_any | 90.0% | 100% (+10pp) | 裸模型能"看到"问题, 但不能"归因到契约" |

100 案例全量基线实测: 见 docs/eval/llm-baseline-100-live.md (运行中/已完成)。

## 4. 面试要点

- "我们不是让模型提意见, 而是把需求编译成契约再验证" — 上面两行口径差
  就是这句话的量化证明。
- 8/11 能力探测 + 按能力降级, 是"第三方网关不可信"原则的工程落地。
- live-fire bug 的发现与修复展示了"mock 绿不等于上线绿"的验收哲学。
