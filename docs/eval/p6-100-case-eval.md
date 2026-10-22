# P6 评测说明 - 100 金案例构成与评测经济学

> 状态: 阶段一完成 (案例文件/构建器/agent 管线/验收测试/docs 全部就绪,
> 约束解除后 agent/ 已重新落地并全量验证)。
> 阶段二 (builder/tag/全量评测) 等队长授权。

## 1. 构成 (100 = 20 + 80)

| 类别 | 现有 | 新增 (case-21..100) | 合计 |
|---|---|---|---|
| Auth | 8 | 7 (4+ / 3-) | 15 |
| Tx/Concurrency | 3 | 12 (8+ / 4-) | 15 |
| Migration/Schema | 1 | 9 (5+ / 4-) | 10 |
| API 兼容 | 3 | 7 (5+ / 2-) | 10 |
| Redis | 0 | 10 (7+ / 3-) | 10 |
| MQ/Outbox/幂等 | 3 | 7 (5+ / 2-) | 10 |
| Logic/Boundary | 1 | 9 (6+ / 3-) | 10 |
| Perf/N+1 | 0 | 5 (4+ / 1-) | 5 |
| Weak-tests/Mutation | 0 | 5 (4+ / 1-) | 5 |
| Prompt-injection/Sandbox | 0 | 5 (全负) | 5 |
| Reliability/dup-events | 1 | 4 (3+ / 1-) | 5 |

总计 100 案例: 正样本 63 / 负样本 37。holdout (case-01/05/09) 锁定不动;
新增负样本全部要求 0 finding (含 5 个 prompt-injection 文本注入到
README/注释/requirement.txt/schema.sql/pom.xml 的沙箱语义案例)。

> **#334 更新**：池子现在是 **101** 案例（正样本 **64** / 负样本 37）——
> 新增 `case-101-tx-bulk-update-bypasses-version-guard`（并发家族的
> **holdout**：服务级缺陷，批量 UPDATE 绕过版本守卫）。
> **上面的 100 / 63-63 / Recall 100% 是历史评测记录，不因新案例而改写**：
> 那一轮评测跑的是 100 个案例。要把 101 个案例重跑一遍，是另一次评测的
> 事，本号**没有**做，也不假装做过。
> 该案例自身的诚实性是**单独**验证过的：`scripts/verify_case_tags.py
> --case case-101` 在真正的 tag 上跑——`base` 18/18 通过，
> `case-101-head` 恰好 1 个失败（服务返回 200、另一个写者的库存 5 被吞成 7）。

## 1.1 案例集选择：默认跑 90，不是 100 (#77/#78)

本节第 1 部分里的 "100 案例" 是**池子总大小**，不是一次评测实际测量的案例数。
自 #77 起 `specproof eval`、自 #78 起 `specproof baseline` 都默认按
`docs/eval/holdout-manifest.json`（case-01..case-10，status `candidate`）做隔离：

| 案例集 | 命令 | 实测 (2026-09-26, 100 个 case 目录) |
|---|---|---|
| `tuning`（默认） | `specproof eval --cases golden-cases --repo ...` | 90 = 正 55 / 负 35 |
| `holdout_only` | `specproof eval --only-holdout ...` | 10 = 正 8 / 负 2 |
| `all_not_isolated` | `specproof eval --include-holdout ...` | 100（旧行为，报告会明说本轮未隔离） |

规则（选择策略只有 `cli/specproof/case_set.py` 一份实现，两个命令共用）：

- 三种池子的大小不能互相相减。两条命令都把 `case_set` 标签写进自己的
  sidecar（`*.results.json`），`specproof baseline` 在两边标签不一致、或对方
  是 #77 之前没有标签的旧文件时，把 "Go/No-Go #14 (+25pp recall)" 判为
  **无法判定**，表里的 Delta 写成 "跨池不可比"，只保留各自的实测值。
- manifest 读不到时 eval/baseline 直接失败，不会把"读不到"当成"没有隐藏案例"；
  只有显式 `--include-holdout`（本来就不隔离）时才降级为警告。
- 案例池被隔离清空（0 个可跑）不再报成 "目录里没有案例"，也不再以退出码 0 收场。
- 第 1 部分的历史统计（正 63 / 负 37）与 CLAUDE.md 里早先的 Recall/Precision
  都是在**合并池**上算出来的：本次隔离是事后声明（retroactive、partial），与
  manifest 的 `note` 字段同一说法，CLI 每轮都会把该 note 原样打印出来。
- 第 1 部分末尾的 "holdout (case-01/05/09) 锁定不动" 说的是**案例文件本身不再
  改动**，与本节的评测隐藏集（case-01..case-10）只是名字相同，不是同一件事。

## 2. 检测面与严重度政策

- 正样本优先 execution-only: 差分测试 + 状态快照 (users/products/orders
  三表 H2 取证) + mock 调用断言 (Redis/RabbitTemplate) + SqlQueryCounter
  查询计数。静态可检的 (注解移除/DTO 字段/DDL 变更/测试弱化) 保留一部分,
  由静态检查器封顶 MAJOR。
- BLOCKER 需 6 条件 (approved contract + 真实 base/head 执行 +
  归因 head + DB/行为证据 + capsule 可回放 + confidence >= 0.90)。
  新案例中 base_pass_head_fail 且 H2 dump 因回归发生表级差异的
  (Auth 4 / Tx 5 / Logic 4 / Rel 1) 期望 BLOCKER; 其余 execution-only
  期望 MAJOR; 纯静态期望 MAJOR。case-17 先例 (期望 BLOCKER 实测 MAJOR)
  提示实际落档以评测输出为准, 评测匹配按 contract-id 而非严重度。
- 负样本: 等价重构/等价注解/收紧权限/注释/文档/空白/注入文本 - 必须
  0 finding (split.json negative.max_findings = 0)。

## 3. 构建与标签 (阶段二执行步骤)

1. 队长/发布流提交 demo/ (P6 扩展基座, 含 cache-aside、orders/products、
   SqlQueryCounter、schema.sql、测试修复) - builder 的 require_clean()
   只检查 demo/ 子树, 主工作树可长期不干净。
2. 运行 python scripts/build_golden_scenarios.py (授权后):
   - tag base 指向该 demo 提交 (新基座);
   - 重建 head-v1 = base 去掉 @PreAuthorize (旗舰回归, 语义不变);
   - 每案例 detached 提交 (父提交 = base) 得到 case-01..100-head;
   - 收尾 restore demo/ 到 base 并自检 demo/ 干净。
3. 案例目录/ground-truth/split.json 由 P6_CASES 数据表单源生成
   (emit 脚本已执行: 100 目录 + registry 98 条)。

## 4. 评测经济学: Base 构建复用

- 机制 (agent/nodes/build_cache.py + run_differential +
  generate_counterexamples), 三项压缩:
  1) Maven 调用 3 -> 2: 确定性路径在 generate_counterexamples 里跑
     头侧完整测试 (compile+surefire 一次沙箱调用), 记录 exit/test_counts/
     compile_error/test_file_sha256; run_differential 校验 sha 一致后
     head_run_reused=true 直接复用该记录 (编译失败仍按原语义归为
     NON_REPRODUCIBLE);
  2) 首个案例 base 全量构建后, target/classes + test-classes 缓存到
     reports/.base-build-cache/<base-sha>/ (surefire 报告与 H2 状态文件
     刻意排除 - 证据必须每案例新鲜产生); 后续案例 base 侧恢复缓存 +
     冻结全部源码 mtime (base 源码跨案例恒定) + -Dmaven.main.skip=true,
     只编译之后注入的生成测试 + surefire;
  3) head 侧播种同一缓存并回拨未变更源码 mtime (变更文件及其 mention
     依赖保持新 mtime 触发重编译); 若 Maven 增量判定与预期不符,
     失败模式是整树重编译 - 只慢不错。
- 实测 (阶段一, 3 案例小样本, 本地模式): 每案例 53-65s, 复用路径
  base_cache_hit=true / head_run_reused=true 端到端验证, 检测 100/100/100;
  第十轮 20 案例基线 75-90min (~3.75-4.5min/case); 沙箱模式按每调用
  +15-30s 启动开销外推 ~2-2.5min/case, 100 案例 ~3.3-4.2h (slow_eval
  timeout 18000s 的依据)。
- 缓存键: git rev-parse base 的提交 sha; 目录在 reports/ 下 (gitignored)。

## 5. 离线依赖状态

- pom.xml 未新增任何依赖 (spring-boot-starter-data-redis 在 W5 已入,
  新代码只用 JPA/Spring/Jackson/Hibernate 既有 API); 沙箱缓存卷
  specproof-maven-cache 离线 mvn -o test 探针全绿 (阶段一实测)。
- 遗留预置需求: 无。

## 6. 验收门禁

- tests/integration/test_phase_acceptance.py: 100 目录断言; slow_eval
  全量 100 案例; HTML 报告子集改为 1 静态+执行正样本 + 1 负样本 +
  1 执行级 + 1 Redis 执行级 (case-01/10/17/56)。
- CI 的 eval-golden-cases job 文本 ("20 golden cases", 90 分钟 timeout)
  需在阶段二前由队长同步更新 (.github/ 不在本子代理范围)。

## 本地重跑记录（#373，2026-10-22）

在 **JDK 17** 上用本机跑的一次**抽样**评测（CI 那个 4 案例子集：3 正 + 1 负）：

| 案例 | 期望 | 实测 | 命中 | 耗时 |
|---|---|---|---|---|
| case-12-add-javadoc | 不该报 | 无发现 | — | 358.6 s |
| case-17-logic-inversion | 该报（UNIQUE-01） | 命中 1 条（UNIQUE-01） | ✅ | 882.1 s |
| case-21-auth-weakened-permitall | 该报（AUTH-01） | 命中 1 条（AUTH-01） | ✅ | 493.3 s |
| case-56-redis-cache-eviction-removed | 该报（CACHE-01） | 命中 1 条（CACHE-01） | ✅ | 270.8 s |

**Recall 100.0% / Precision 100.0% / F1 100.0% / 假阳性 0 / Acceptance: PASS**
（严重度一致率 66.7%：case-17 期望 BLOCKER、实测 MAJOR ⇒ 已知的老问题，未在本号处理。）

**这份记录能说明什么、不能说明什么。**
- **能说明**：整条链路在本机**真的跑得通**（差分 → 复核 → 矩阵 → 胶囊 → 证据包 → 评测计分），
  且**缺陷被找到了**（3/3 命中）；此前本机连编译都过不去（#370/#371 之后才通）。
- **不能说明**：这不是 101 个案例的**全量**结果 ⇒ 上面那些「100 / 63-63 / Recall 100%」仍然是**历史
  记录**，没有被本号重测（全量要 ~6–15 分钟/案例 ⇒ 十小时量级 ⇒ 它的位置仍是 CI 的 nightly job，
  而那个 job **还不存在** ⇒ workflow 改动**推不动**：token 缺 `workflow` scope）。
- **耗时是本机的**：4 个案例 270–882 秒（均值 501 秒）⇒ 这是 **FAST** 档、demo 规模、且本机当时
  还在跑别的作业 ⇒ ⇒ 只能当**量级**看，不能当分布 ⇒ ⇒ `DEPTH_EXECUTION_BUDGET_SECONDS` 的
  7200 秒（DEEP 档）**没有**因此改动（DEEP 档还要加突变战役，量级不同 ⇒ 需要真的 DEEP 作业的分布，
  见账本 #373 队列）。
- 评测**写在测试库**（`SPECPROOF_TEST_MYSQL_DATABASE`）⇒ 产品库没被撒 `eval-*` 的行（#370）。

## 全量评测的**实测**结果（2026-10-22 跑完）

**这一节是数字。** 上一版写的是「结果会在哪儿」；这一版是**跑完的那一轮**。

| 指标 | 实测 | 说明 |
|---|---|---|
| 池 | **87** 个被测案例（52 正 / 35 负） | 101 个目录 − 14 个 holdout 隔离 |
| 判定 | **87** 个案例，**0** 个 not run | |
| 检出 | **51 / 52** 个正例 | **Recall 98.1%** |
| 误报 | **0** / 35 个负例 | **Precision 100.0%** |
| F1 | **99.0%** | |
| 严重度一致 | **88.2%**（51 个命中正例） | 6 处漂移，见下 |
| Acceptance | **PASS**（未设门槛） | 门槛没钉 ⇒ 只报数字，不判合格 |
| 墙钟 | **29 337 秒 ≈ 8.15 小时** | 本机、**有争用**（同时在跑别的作业） |
| 单案例耗时 | 最短 **160 秒** / 中位 **237 秒** / 最长 **1022 秒** / 均值 **330 秒** | 管线时间合计 7.99 小时 |
| 测量用的代码 | sha **`22c4324`**（#376） | 那一轮 05:24 起跑，用的是当时的代码 |

**唯一的漏检**：`case-100-rel-event-timestamp-nulled`（期望合同 `EVENT_ONCE-01`）。

**而这个案例正是账本 ## #391 量出来「检出不稳」的那一个** ⇒ ⇒ ⇒ 也就是说：

- 同一份代码、同一对 ref，**一次检出、一次不检出**（#391 的受控 A/B：两次都漏，另
  一轮检出）⇒ ⇒ ⇒ 那一轮的不稳定**不是**代码改动带来的，是**运行环境**带来的。
- **全量评测那个 98.1%，离 100% 差的就是这一个案例** ⇒ ⇒ ⇒ 而那一轮如果它「走运」，
  数字就是 52/52 = **100%** ⇒ ⇒ ⇒ ⇒⇒⇒⇒ **这个 Recall 会随跑动** ⇒ ⇒ ⇒ 所以
  下一轮**必须**用 `--attempts`（见下一节）⇒ ⇒ ⇒ 两个数（能不能检出 / 第一次有没有
  检出）**并排**报出来。

**6 处严重度漂移**（命中了但定级不同，**不是**漏检）：

| 案例 | 期望 | 实测 |
|---|---|---|
| case-17-logic-inversion | BLOCKER | MAJOR |
| case-19-email-corruption | MAJOR | BLOCKER |
| case-20-validation-removed | MAJOR | BLOCKER |
| case-22-auth-guard-moved-to-dead-helper | BLOCKER | BLOCKER, MAJOR |
| case-33-tx-order-idempotency-dedup-removed | BLOCKER | MAJOR |
| case-97-rel-broker-failure-retried-into-duplicate | BLOCKER | MAJOR |

（严重度一致率 88.2% ⇒ 5/6 是「定得偏轻」，1/6 是「定得偏重」。这一条是**已知的
老问题**，#373 就记过 case-17 那一处；**这一号没有处理**它 ⇒ ⇒ ⇒ 记在这里，别让它
被读成「全绿」。）

**这些数字能说明什么、不能说明什么。**

- **能说明**：整条链路在**全池**上真的跑通了（87/87，0 个 not run），**检出 51/52 个正
  例、误报 0/35 个负例** ⇒ ⇒ ⇒ 而**之前**那些「100 / 63-63 / Recall 100%」是**历
  史记录**，跟这一轮**不是**同一件事（那一轮是 4 案例的抽样，**没有**隔离 holdout 的记
  账）⇒ ⇒ ⇒ 这一轮的数字才是**当前**的。
- **不能说明**：
  - 这一轮是**本机**、**有争用**、**Windows + JDK 17 + 本机服务 + 本机 Maven** ⇒ ⇒ ⇒
    CI 是 **Linux + JDK 21 + 容器里的服务 + 沙箱模式的 Maven** ⇒ ⇒ ⇒ 「本机 98.1%」**不
    等于**「CI 也 98.1%」⇒ ⇒ ⇒ CI 那一次**还没跑过**。
  - **Recall 98.1% 不是一个稳定的数**（#391 + 上面那一处）⇒ ⇒ ⇒ 引它的时候**必须**说
    清楚它是**哪一次**、**哪一天**、**哪个 sha** 测的。
  - 测量用的代码是 `22c4324`（#376）⇒ ⇒ ⇒ 这之后的改动（#378 续跑、#380 观测进判定层、
    #383 旋钮名册与 SQL 占位符、#387 bandit 说明、#389–#393 脚本与账）**没有一条改动
    检出那条路**（检出走差分与复核，评测的数字只数**发现**）⇒ ⇒ ⇒ 所以这些数字描述的是
    **现在**的检出能力 ⇒ ⇒ ⇒ 但**下一轮全量**会再确认一次。
  - 8.15 小时是**本机、有争用**的墙钟 ⇒ ⇒ ⇒ 独占机器会更快 ⇒ ⇒ ⇒ 这是**量级**，不
    是分布。

## 全量评测该怎么跑（2026-10-22 更新）

**一条命令**：

```
python scripts/run_full_eval.py --attempts 3
```

三件事都在这条命令里，每一件都有理由。

- **可续跑**（`--resume` 永远开着）：报告和它派生的逐案例 sidecar 都落在
  `reports/full-eval/` ⇒ ⇒ ⇒ **那个目录就是缓存要保住的东西** ⇒ ⇒ ⇒ 一个被杀掉的
  作业重跑时**接着跑**，不是从头再来（#377 的落盘 + #378 的续跑；真管子上实测
  623 秒 → 14.2 秒，见账本 #385）。
- **能重试**（`--attempts 3`）：有些案例的检出**不稳** —— 同一份代码、同一个案例，
  一次检出一次不检出（账本 #391 的受控 A/B）。正例在**第一次检出**就停 ⇒ ⇒ ⇒
  于是报出来的 recall 回答的是「**这个缺陷能不能被检出**」⇒ ⇒ ⇒ 不再取决于当天的
  运气。
- **两个数并排**：「**第一次就检出**」的比例被单独报出来（`First-try recall:`），
  哪个案例不稳也被点名（`unstable detection: … needed N attempts`）⇒ ⇒ ⇒ 不稳不再
  被藏起来。

**新旧两个数不可直接比。** 历史上那些「Recall 100%」都是**一次就量**测出来的 ⇒ ⇒ ⇒
它们对应的是新的 **First-try recall**，不是新的 recall ⇒ ⇒ ⇒ 新的 recall **只会
>= 旧的** ⇒ ⇒ ⇒ 拿它去替换旧数并说「准确率提高了」是不诚实的 ⇒ ⇒ ⇒ 两个数必须并排
读。

**负例仍然只量一次。** 误报是硬信号，一出现就报；专门去「多找几次误报」等于每个
负例都多付一次全量测量 ⇒ ⇒ ⇒ 那是另一件（更贵的）实验。
