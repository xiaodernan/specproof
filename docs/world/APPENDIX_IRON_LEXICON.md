# 铁证词典 · Iron Lexicon · SpecProof Glossary

> 此词典不是定义集，是**验收官认得的字面表**——每一条都能在仓库里指到确切的位置。
> 每一条来自本项目已经落地、真正跑过的代码——不是杜撰。
> 若你英文阅读本词典：请先读 `EN/SPECROOF_WORLD_EN.md`。

---

## A

### `accept_judge` — 接受审判官
> 铁语境：本项目中一个 **Kind**。`accept_judge` 是裁决动作的编码名——它来自 `accept.py`，
> 是不可缓存的一种 evidence 动作；它的存在证明一个变更既被接受，判决书已经落地。
> 文档位置：`providers/semantic_cache.py`（硬排除）、`docs/operations/DEEP_OPTIMIZATION_PLAN.md` 大量使用。

### `AUTH-01` — AUTH（权限）系列契约
> 铁语境：**验收契约的编号**。AUTH-01 是 demo repo 中 `changeEmail` 接口上
> "未认证请求应被拒绝（401/403）且数据库行不变"的需求化表达；checker_type=`http`。
> 验收的真理样式之一——一行 requirement → 一个 contract_id → 一次 differential execute →
> 一个 verdict。
> 真跑过证据：`tests/integration/test_differential.py`，Tag `head-v1` 刻意移除 `@PreAuthorize`，差分必跑 `base_pass_head_fail`。

---

## C

### `capsule` — 复现包
> 铁语境：验收的**便携真相**。每次验收完成后，`create_capsule`（`agent/nodes/create_capsule.py`）
> 会把结论、证据、执行环境、commit hash 连同生成的脚本压成一个 `<job_id>.zip`，
> 作为有独立生命的证据压缩包。它证明的事：任何第三方按 capsule 全量重放都能看到同一个 finding。
> 前端入口：JobDetail 「复现包」Tab，「复制评审链接」按钮。
> 红线：capsule 永远不加密到你不能看——它是验收官给未来的快递，不是加密货。

### `counterexample_test` — 反例测试
> 铁语境：**为验收官服务的测试**（不是给代码提质量用的）。
> `agent/nodes/generate_counterexamples.py` 按需求生成：base_pass_head_fail 的反例在 head 上 FAIL、
> 在 base 上 PASS——它是判决真假的唯一试金石。证据以 `base_pass_head_fail` 给出铁名。

---

## D

### `differential execution` — 差分执行
> 铁语境：**本项目最贵也最可靠的一把尺**。两个 ref（base / head）编译到同一个沙箱里
> （`docker_sandbox.py`），同一套测试依次跑-over，看结论往哪边倒。
> 倒的方向（基线过、头版本挂 = `base_pass_head_fail`）就是反例。
> 铁律：`base_pass_head_fail` 是唯一被冠以「铁」的证据等级；其它全是「可能」可能。

---

## E

### `execution_surface` — 执行面
> 铁语境：**证据在哪里跑出来的**。`sandbox`（Docker 隔离，意指 base/head 正常）/ `host`（宿主机直接跑，有降级，需要标注）/
> `none`（铁证缺失，矩阵标出 UNVERIFIED）。`execution_surface` 强制携带于每一条 finding，
> 缺了它，就是**隐瞒证据**。
> 文件：`integrations/rollup_differential`、`tests/unit/test_matrix_pure.py`。

---

## F

### `findings_court_*` — 审判庭家族事件指标
> 铁语境：**observability 里针对验收裁决的一整族 Prometheus 指标**。
> 真机实例：审判庭每次开庭就 `incr("findings_court_candidates_total", float(len(candidates)))` 一口；
> 裁决结果分别打到 `incr(f"findings_court_{final_status}_total")`（final_status 来自审判庭审计条款）。
> 全家族被 `tests/unit/test_observability_metric_parity.py` 钉死（独立的 parity 测试：一行动事件必须有一条指标对应）。
> 文件：`agent/nodes/review_court.py`、`tests/unit/test_observability_metric_parity.py`。

---

## G

### `gate` — 门
> 铁语境：验收不是"看看差不多"，是**门**——门开了才进。门后面是可执行脚本：
> `tests/unit/*`、`tests/e2e/*`、`tests/integration/*`——一次红就是一根钉子打进去；
> 多少次红了，哪一根钉子拔了，都写在 ledger。SpecProof 的哲学不是"零红=收手"，
> 是"**红了几例你告诉我，少一个都别瞒**"——这条仅适用于任何只靠 LLM 给判断的产品。

---

## J

### `JUNIT_GENERATION_PROMPT` — 反例生成 prompt 的稳定前缀
> 铁语境：**最被信任的不变的那一段文字**（2270 字符 / ~567 tokens）。
> 它先产生稳定 prefix，再活动变量尾巴（`ADDITIONAL_CONTEXT`），
> 正是为了让 wkapi.pro 的 prefix-cache 每次命中 ≈84%（实测：_cache_probe.py、_threshold_probe.py）。
> 该常数在 `_JUNIT_GENERATION_PROMPT`，不改变 → 缓存一直命中 → 成本下降 → 反例持续产出。

---

## L

### `ledger (DEEP_OPTIMIZATION_PLAN.md)` — 史官账本
> 铁语境：**把每一桩真实事件都写进来的铁卷子**。#1600 起，到 #1683（本节），每一条记录
> 包含：承诺的事、真实做了的事、剩余风险、证据、以及下个一步。
> 不允许假装看到"已经完成了"假装无事发生但实施者作废。
> 是本项目的心脏。是其他记账系统的母亲。

---

## M

### `matrix` — 矩阵
> 铁语境：验收每一条需求对应一行 contract_id，每行带 `result=PASS/FAIL/UNVERIFIED` 与
> `evidence_type`。矩阵是「可验证的整体」。为 `apps/web/src/pages/Matrix.tsx` 与相关测试提供事实。

---

## P

### `policy (specproof_review_court)` — 审判庭政策表
> 铁语境：裁决不是由 AI 思考出来的，是由 `agent/review_court/policy.py`（`specproof_review_court`）钉住的政策表决定的。
> 该表 6 段——perf/中性词集/ base/amount-rank/等级门/ severity nuking。
> 它是验收文件的心脏：tests/unit/test_review_court_policy.py 和 tests/unit/test_matrix_pure.py（与同白名单文档）锁住它。

---

## S

### `spec` — 需求清单
> 铁语境：用户写的「一组需求」。与 contracts 不同：**spec 是自然语言对人类的回答**；
> contracts 是对机器的回答。一个 spec → 多个 contracts。

---

## W

### `wkapi.pro` — 本产品的模型端点
> 铁语境：你自己实验过的真实端点 `https://wkapi.pro/v1`，
> 模型 `gpt-6-sol`，protocol: chat_completions。API 调用经由
> `providers/openai_compatible.py`——双车道：chat() 自动走 stream=True+include_usage；
> chat_stream() 走 chunked SSE，双路都开 `stream_options={include_usage:True}`。
> 密钥仅存在 `.local/llm.json`，从不入库。

---

## 印记 — 验

> 验讫，不是"想让它过"，而是**证据自己证明了**。

每一笔铁证都是验过，每一卷都是一次复验。

*若你在别处看到"都完成了"，请先看矩阵中有没有未验证的格子——*
*铁矩先验证，再谈验讫。*
