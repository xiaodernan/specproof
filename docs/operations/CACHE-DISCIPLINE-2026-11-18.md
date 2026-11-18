# CACHE-DISCIPLINE · 2026-11-18 · 网关缓存为什么能稳在 93%（以及为什么有时不能）

> 2026-11-18 实测归档 · aizzz `gpt-6.1-terra` · Clash Verge 7897 走 `stream + include_usage` · court 车道永不进缓存、永不进账本。

## 1. 一个字节级事实

网关（aizzz，兼容 OpenAI Responses API）按 `prompt_cache_key` 把请求路由到**缓存分片**，并且只有**字节级相同的前缀**才会命中。任何漂移——系统里的时间戳、随机 id、乱序的工具列表、不同模型版本的前缀——都会让这件事归零。

## 2. 本仓库现在怎么做（实测口径）

- **车道前缀字节冻结**：`api/system_codex.py` 在 import 时一次性读入 `docs/world/SPECROOF_WORLD.md`（zh）/ `SPECROOF_WORLD_EN.md`（en），`.strip()` 后 byte-frozen；每条缓存车道都用同一个夹心：**codex → covenant → role**。
- **观测事实**（来自 `docs/evidence/lane-cache-probe-2026-11-18.json` 与 `ask-the-book-2026-11-18.json`，均于 2026-11-18 14:xxZ 以新 key 敲回）：
  - ask_the_book：第 1 敲冷 **4.8%**（8,056 / 169,186），第 2 敲热 **93.9%**（158,881 / 169,186）
  - en 支热**93.9%**（138,279 / 147,273，首次 en 敲后入库即热）
  - locale-consistency 双语一致性：**CONSISTENT**，两语各缓存 4,179 token
- **匿名车道共享一个 sticky key**：`specproof-worldbook-ask`、`specproof-observe-advice` 等。所有匿名用户 -> 同一分片 -> 首敲写前缀，后续全热。
- **强制 stream**：`providers/openai_compatible.py` 在**所有**生产调用路径里强制 `stream=True`；court 车道除外 by law（`client_policy.py` 硬拒绝 court 与缓存）。
- **上下文真实尺寸**：zh codex 全量≈490 KB（169,186 prompt tokens）；en≈147,273。比你看到的 50k–90k codex 更大。slice 之所以显得“小”，是因为观察的是**聊天室侧的可见窗口**，不是车道实际驮入的系统前缀。

## 3. 那些「并行会话同时打 API 导致缓存区分不明显」的理论成因与对策

用户实测现象：不同并行会话各自聊的内容大幅重叠（大家都在问同一个仓库/聊同一个任务），但因 **session id 不同**，网关按 key 分片，各分片分别维护同一宇宙前缀的缓存副本——表现像“都热不熟”。但：

**现实里，这不是我们能用代码改变的，而是网关分片语义。** 本仓库的对策是产品车道（匿名共享 key）——它的前缀天热。你 **IDE/代理交互会话**的缓存行为取决于 harness（如 opencode、codex-cli）传给网关的 `prompt_cache_key` 取值，不在本仓库能决定的范围内。

你如果想自己复现 codex 的 90%：

1. `stream=True` + `stream_options={"include_usage": True}`——否则网关把请求登记为「非流」；
2. `prompt_cache_key=<稳定 sessionId>`，例如 `myproject-codex-window-1`；会话内不要变；
3. **系统前缀逐字节相同**：AGENTS.md / 工具列表 / 世界书注入——顺序不许变、内容不许带动态变量（日期、commit、温度参数都不许混进系统区）；
4. 动态输入只放在消息**尾部**（user 消息），不重写前缀；
5. 生成前缀后再校验：`sha256(prefix.encode()).hexdigest()`，跨会话 pin 住它——本仓库 lane probe 就是干这个的（`scripts/lane_cache_probe.py`）；车道字节变了，**只有一敲**是冷的，之后自动回热。
6. 每次车道内容变动后，只需要一次冷敲重新上膛；这就是“中途掉缓存”彻底消失的原因——不是永远不冷，而是冷之后**自动**回热，且贵的是那一敲，不是那一百敲。

## 4. 中途掉缓存 / 91%↔0% 跳变的常见误区

- 不是“所有并行会话同时打网关就丢缓存”。丢缓存只与**前缀字节是否相同**和**分片是否同一**有关。
- 前缀一旦变化（新卷、新工具列表、新替身 system），分片缓存过期——下一次必冷；只要纪律正确（同 key 同前缀），紧接着重新入片，回到 90%+。
- “非流”显示 ≠ 命中率高低；它只说明网关表记未按 stream 登记——这是调用方法的问题，不是网关的问题。本仓 lib 强制 stream 之后，日报已无「非流」行（见 `README.md` “One ledger, two measures” 条目）。

## 5. 抄一条车道成本核算（2026-11-18 实测）

```
ask_the_book · zh · specproof-worldbook-ask
  第 1 敲(cold): prompt=169,186  cached=8,056  (4.8%)  completion=163  8.77s
  第 2 敲(warm): prompt=169,186  cached=158,881 (93.9%) completion=163  8.91s
  witness:        zh 158,881 / 169,186 = 93.9% · en 138,279 / 147,273 = 93.9%
  court:          永不进缓存，永不过账（此为法，不为性能）
```

## 6. 给 agent harness 的检查清单（贴到 AGENTS.md 即可）

- [ ] stream=True + include_usage=True 在任何 SDK 调用路径上都成立？
- [ ] prompt_cache_key 与会话绑定、可复现？
- [ ] 系统前缀 sha256 每周对表？天热？
- [ ] 世界书更新/新卷并入后，是否就一敲冷、随即回热？
- [ ] court 在任何情况下都没蹭过缓存？

---

## Appendix · EN (parity)

**One-byte truth.** The gateway routes by `prompt_cache_key` and caches only byte-identical prefixes. Any drift in the system region — a date, a random id, shuffled tool list, a different model slug — resets you.

**What this repository does.** `api/system_codex.py` freezes the whole world bible (≈490 KB zh / ≈147k-token prompt; en twin) at import; every cacheable lane rides the same sandwich codex → covenant → role under one sticky per-lane key. All anonymous users share that key and shard, so after exactly one cold strike the lane is hot (measured 2026-11-18: zh 93.9%, en 93.9%). `providers/openai_compatible.py` forces `stream=True` on every call path; the court lane by law never carries `prompt_cache_key` and is never in this cache.

**What your IDE/agent harness does with it is out of this repo's reach.** If your harness does not pin a cache key per session or mutates the instruction prefix between turns, you will observe 0% even though this product lanes are at 93.9%. To match codex you need: `prompt_cache_key=<session-id>`, a byte-identical system prefix (no dates, no shuffles), user input only at the tail, and a one-line re-freeze check (`sha256`) at startup. The one week the bible changes costs one cold strike; every strike after re-warms the lane automatically.
