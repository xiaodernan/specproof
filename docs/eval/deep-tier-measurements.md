# DEEP 档的耗时测量（第一份真实数据）

`storage/mysql.py` 里的 `DEPTH_EXECUTION_BUDGET_SECONDS` 写着
`FAST=3600 / DEEP=7200 / RELEASE=10800` 秒。这三个数从落地那天起就是
**估的**：没有任何一次 DEEP 作业被计时过，回收器（`expire_overdue_jobs`）
却会照着它去杀作业。估的数一旦比真实作业短，工具就会把还在老实干活的
作业判成超时。

本页是那份**第一次真测**的记录。每加一行测量，`tests/unit/
test_deep_tier_measurements.py` 会重算：那一档的实测耗时必须小于
该档的预算 ⇒ ⇒ ⇒ **预算被改小到装不下已经量过的作业时，测试会红。**
（反方向不成立：预算是上限，不是目标；实测一直比预算短也不需要改。）

## 怎么量的

```
.\.venv\Scripts\python.exe -m cli.specproof.main verify \
  --repo . --base base --head case-17-head \
  --spec golden-cases/case-17-logic-inversion/spec.md \
  --depth DEEP --no-llm --app-dir demo/spring-backend --no-evidence-pack
```

计时用 `Get-Date` 卡在命令前后（墙钟时间，含准备 Base/Head 工作树、
跑测试、收集证据、生成 capsule、落 MySQL 摘要的全过程）。

## 测量表

sample-count: 1

| 日期 | 档 | 案例 | 合同数 | 墙钟（秒） | 判定 | finding | 机器条件 |
|---|---|---|---|---|---|---|---|
| 2026-10-22 | DEEP | golden-cases/case-17-logic-inversion | 1 | 1450 | BLOCKED | 1 MAJOR (base_pass_head_fail) | 笔记本；JDK 17；Maven 离线；MySQL/Redis 本机；`--no-llm`；`--no-evidence-pack` |

## 这份数据的**薄**在哪（不许把它说厚）

- **n = 1。** 一个案例、一个合同（`UNIQUE-01`）、一台机器。
- 那个案例**只编译出 1 个合同**。合同数是 DEEP 耗时的主要驱动因素
  （每个合同要跑自己的检查），合同多的案例会成倍地慢 ⇒ ⇒ ⇒ 1450 秒
  **不是** DEEP 档的上界。
- 机器是**笔记本**，而且当时**有别的项目在同时跑测试**（全量单测
  1:35:34 就是这么来的）⇒ ⇒ ⇒ 1450 秒里有一部分是**排队**时间 ⇒
  ⇒ ⇒ 独占机器时可能更快。
- 本机 JDK 是 17，项目声明 21（preflight 报了一条 warning）⇒ ⇒ ⇒
  快不了也慢不了多少，但**不是** CI 的条件（CI 用 21）。
- 这一档**没有**跑 LLM（`--no-llm`）⇒ ⇒ ⇒ 带 LLM 的 DEEP 作业会
  更慢 ⇒ ⇒ ⇒ 1450 秒也**不是**上界。

## 结论（以及为什么预算没动）

- 1450 秒 = DEEP 预算（7200 秒）的 **20%** ⇒ ⇒ ⇒ 这次的测量
  **没有**证伪预算 ⇒ ⇒ ⇒ 预算**保持 7200**。
- 按这**一个**样本把预算砍到 3600 看着"够用"（2.5 倍余量）⇒ ⇒ ⇒
  但 n=1 + 合同数只有 1 + 机器有争用 ⇒ ⇒ ⇒ 这种余量是**猜的**，
  不是量的 ⇒ ⇒ ⇒ 砍预算省下的那点执行时间，代价是**可能把还在
  干活的长作业杀掉** ⇒ ⇒ ⇒ 不砍。
- 反过来，7200 是不是也**太大**？现在没有数据能说 ⇒ ⇒ ⇒ 等
  合同数多的 DEEP 作业被量过再说。
- **下一条**能改善这件事的证据：**合同数 > 1 的 DEEP 作业的耗时**，
  以及**独占机器**时的耗时 ⇒ ⇒ ⇒ 夜间全量评测作业（#375 的
  `eval-full-golden-cases`）落地的 artifact 里带每个案例的耗时
  ⇒ ⇒ ⇒ 那份数据回来时，本页要补行。

## 这次作业顺手暴露的另一个问题（已修，见 #376）

那档 DEEP 生成的 capsule 被打印成
`capsule-COURT-UNIQUE-01.zip (WARNING: digest mismatch)` ⇒ ⇒ ⇒
**假的**：文件完好，digest 对得上 ⇒ ⇒ ⇒ 是元数据查表把**旧记录**
（另一次运行、另一个字节版本）当成了当前文件的记录 ⇒ ⇒ ⇒ 工具对着
健康产物喊"狼来了" ⇒ ⇒ ⇒ 修法与证据见 `## #376`。
