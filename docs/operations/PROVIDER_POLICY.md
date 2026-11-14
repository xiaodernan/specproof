# PROVIDER_POLICY.md — LLM 语义缓存怎么开、开了会怎样

> 本篇是 #1781 的操作手册。结论先行：**`SPECPROOF_PROVIDER_POLICY=1`，仅此一行，semantic cache 就会在 draft/diagnose 两族任务上真正命中。** 未设置时，provider 的行为与 #1781 之前的逐字节版本一致（policy 不构造）。
>
> The 30-second version / 三十秒版：`SPECPROOF_PROVIDER_POLICY=1` — that is the whole switch. Without it the provider builds no policy at all (byte-identical to before). Semantic cache will engage for `draft`/`diagnose` kinds only, and only after #1781's fix makes the cache lane reachable.

## 一、三条开关的作用域

| 变量 | 默认 | 作用 | 证据 |
|---|---|---|---|
| `SPECPROOF_PROVIDER_POLICY=1` | `0` | 打开 policy 层：router → 语义缓存 → 重试矩阵 | #1781 实测：draft 二次调用 3.0ms 缓存回放、0 新 token |
| `LLM_PROTOCOL=responses|chat_completions` | `responses`（gpt-6* 默认） | 响应协议；policy 层在 chat completions lane 可达缓存 | #1781：responses lane 在策略分支之前就返回，缓存恒为结构 0，本仓库已自动旁路 cacheable kind |
| `SPECPROOF_SEMANTIC_CACHE_BACKEND=memory|redis` | `memory` | policy 缓存的存储：进程内 LRU（1024 键 / 300s TTL）或 Redis（`SPECROOF_REDIS_URL`，50ms socket 预算） | 证据类 kind（court/counterexample/accept_judge/contract_compile）硬排除；Redis 挂了 = miss，永不是失败 |

证据类 kind **永远不会**被语义缓存提供：verdict 不允许被"缓存的观点"替代，这是设计死线，不是性能开关。

## 二、#1781 修复了什么

1. **根因**：`gpt-6*` 默认 `LLM_PROTOCOL=responses`，而 `_chat_dispatch` 对 responses lane 提前 return——policy 分支（语义缓存所在）根本没有路径。SpecCraft 的 `craft/planner.py`（draft）与 `craft/loop.py`（diagnose）自带 kind 标签，但标签从未到达缓存。
2. **修复**：`providers/openai_compatible.py::_chat_dispatch`——仅当 `SPECPROOF_PROVIDER_POLICY=1` 且 `kind ∈ {draft, diagnose}` 时，responses 部署自动改走 chat completions lane；其余一切逐字节不变。
3. **实测**：draft #1 10,255ms/104 tok → #2 **3.0ms**（hits 0→1，内容逐字一致）；court×2 均不入缓存；policy 未开时与修改前完全一致；provider 单测 156 passed（3 个预先红测试 stash A/B 验证 master 同样红）。

## 三、复现

```bash
python scripts/semantic_cache_bench.py    # 不打印 key；4 次小调用，端到端打印时延与缓存计数
```

## 四、诚实边界

- 缓存 TTL=300s、容量 1024——它服务于**机械重复**（计划草稿/诊断提示），不服务于裁决；
- 缓存命中回放旧响应——prompt 不变即命中，确认不需要逐次新鲜输出后才适合 draft 重跑；
- `SPECPROOF_PROVIDER_POLICY` 不影响 streaming 车道、usage 记账或 evidence chain；
- 本手册不替代经 CANARY 发布验证的生产变更——改配置前先在 staging 跑一遍 `provider_smoke.py` + `llm_cache_probe.py`。
