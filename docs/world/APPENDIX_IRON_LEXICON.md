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

## Z

### `cold floor` — 冷敲地板 4.8%
> 铁语境：`lane_cache_probe.py` 五车道两敲实测（2026-11-18T06:46Z，13/13 ok）：冷敲 4.8% 是字节冻结前缀（codex + covenant 装订 + 车道小序言）的结构账单，不是 cache 故障；热敲钉 93.9–94.0%。
> 位置：`scripts/lane_cache_probe.py`、`docs/evidence/lane-cache-probe-2026-11-18.*`、账本 `#1995`。
> 语义：这不是 bug，是账目——别涂成 verdict。

### `dual-value drift` / 双值缝
> 铁语境：同一事实在两份账本里以两个数字同时存在的缝隙。卷 #196 落账瞬间（07:17Z 瓷砖=1,791/196，#197 未落地）与卷 #197 全落地后（07:51Z 瓷砖=1,792/197）各自成账；#1997 的 gazette epigraph 自己指出了这条缝，没人说破过。
> 证据：`docs/evidence/gazette-feature.md`（"现场瓦片验收记 1791、196 卷"）、账本 `#1997` 二节、卷一九八 §198.2、卷一九九 §199.2。
> 语义：缝不是错——缝是时间。眼睛看到两个数时，先翻账本，别用一个挑另一个。

### `epigraph` — 头版一闪 / TODAY'S ECHO
> 铁语境：`scripts/gazette_feature.py` 把最新账本节（`## #NNNN`）原文交给 aizzz；模型 ≤ 280 字 / ≤ 220 词，不过机械门不入门；产物 `gazette_feature.json`，io 页 `#specproof-live` 下方直接渲染，账上落 "as model-written"。
> 证据：`apps/web/src/pages/gazette_feature.json`（2026-11-18T09:38:24Z）、账本 `#1997`、卷一九八。
> 语义：文字量闸、机械门、non-verdict——不是 exhibit，不是判词。

### `fact pack` — 事实包
> 铁语境：`scripts/build_latest.py` 产出的 `docs/latest.json`——commits / scrolls / chronicle / exhibits / strike 全部由本仓库现算；浅克隆自毁（`fetch-depth: 1` 曾吐 `total_commits=1`）；`latest_strike` 从 ledger 尾条 `## #NNNN` 兜底。
> 证据：账本 `#1981`（浅克隆史）、`#1993`（兜底 patch）、`#1994`、`docs/operations/DEEP_OPTIMIZATION_PLAN.md`。
> 语义：机器敲的账可以给页面展示；没有一敲未经敲击就出现在页面上。

### `inline derivation` — 同源派生
> 铁语境：`sync_portfolio.py` 的 fact-pack 从 HEAD 内联推导（世界书 `## ` + ledger `#NNNN` + `git rev-list` / `ls-files`）——不复用带 bot 重敲节奏的 `docs/latest.json`；避免 latest-json 路径过滤下一敲延迟；sync 工作流已 `fetch-depth: 0`。
> 证据：账本 `#1996` 一节、`.github/workflows/portfolio-sync.yml`、`scripts/sync_portfolio.py`。
> 语义：跟 HEAD 运动的东西，就别等别人运动完再读。

### `LIVE SHIP` — 现场直播区
> 铁语境：io 页 `index.html#specproof-live`；fetch `./data/specproof-sync.json`（+products +gazette 协同），显示 head、scrolls、chronicle、exhibits、strike、changelog；完全机器重敲，人手不改一个数。
> 证据：`#1994 / #1996 / #1997 / #1998` 现场记录；`.github/workflows/portfolio-sync.yml` 每次 master push 自动推。
> 语义：写在主页上的数字只有两个来源——一是机器敲的 fact-pack；二是被机器拒绝写上去的旧值（后者绝不上墙）。

### `parallel copies` — 复份
> 铁语境：多个并行会话（parallel agents / 本仓 sync probes / bot 重敲）同时指向同一个 repo，各写各的账；CÆSURA《摆旁的灰》系 KI-677~680、ORACLE strip、nexus-content sync、keaw `SPECROOF_EXHIBIT_COPILOT_PROXY`——都是复份之手。
> 证据：`git log --date-order --oneline -20`；账本 `#1994`、`#1997` 记录的 rebase-merge 收尾。
> 语义：复份不是错误；但每份必须写自己的账、签当事人的 commit；RMH（rebase-merge-hand）收尾——保留基础、推自己的层、不替别人落账。

### `strike` — 敲击 / 实敲
> 铁语境：本仓库唯一认"实敲"的语言——每次 LLM 调用、每次 probe、每次 build、每次 CI run 都叫一敲；数字必落 `docs/evidence/*`；不敲不认，不认不写。
> 证据：`docs/evidence/` 全目录；账本 #199x 系全部当前；任何"听说/据说/应该"都不入账。
> 语义：一敲只是一敲；它不比"克隆下来重跑一遍"更权威，也不比"不敢面对"更卑微。

### `warm-up rotation` — 热冷轮转
> 铁语境：dig 车道第 1 敲时 tester/security 已热（probe 之前一敲写入同前缀），explorer 冷；第 2 敲 explorer 热了，tester 冷。key 同，但 cache line 各持——前缀不同就各守自己的槽；不叫"乱了"，叫"预热"。
> 证据：`docs/evidence/lane-cache-probe-2026-11-18.md` addendum 第 4 条；账本 `#1995`。
> 语义：车道冷热轮转不是 cache 失灵；它叫"不知道就去猜槽"。

---

## 印记 — 验

> 验讫，不是"想让它过"，而是**证据自己证明了**。

每一笔铁证都是验过，每一卷都是一次复验。

*若你在别处看到"都完成了"，请先看矩阵中有没有未验证的格子——*
*铁矩先验证，再谈验讫。*
