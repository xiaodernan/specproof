# ROADMAP · LIVE — SpecProof

> 自动生成于 2026-11-15 18:04Z（scripts/build_roadmap_live.py）· 下次 chronicle 重推会变灯花。
> **不含任何承诺** — 每一条都是「门下一要敲什么 + 谁来敲（机器 / 人类）」的清单。

| # | 门 | 谁来敲 / 阻塞 |
|---|---|---|
| 1 | 等待首班 weekly-stress 实敲 | .github/workflows/weekly-stress.yml 已合入 是；首班 = 合入后下一个周一 03:00 UTC（cron）。**不阻吞吐、不红旗；artifact 到手后人工决定是否入库**。 |
| 2 | 真·fleet 遥测仍欠真人签字 | OBSERVABILITY.md 签字 = **awaiting-signature**。需要人类（不是人类的它那边）；签完 audit_unsigned.py 自动转玉绿。 |
| 3 | 重敲一次 evidence 对最早一篇核对 Δ | 目前 2 件落库；latest `2026-11-16-static-warm-2.json` worst p99 1537.3ms、verdict OK。Δ 只有两件以后才有意义。 |
| 4 | PORTFOLIO_TOKEN（若你要让个人主页知道） | Settings → Secrets → `PORTFOLIO_TOKEN`（Contents: read+write，xiaodernan/xiaodernan.github.io）；没配 = 工作流绿但永不推送，不红旗。 |
| 5 | 清理工作区不再需要的 `site-packages` 增长 | LOC 500,133 · 2,780 files；缓存别管，保留证据。本条由 repoStats 自动推导数字。 |
| 6 | 新增卷继续随本体入账 | 编年史 1,862 节；每本书都要 atomic 入账，数量漂了就要重跑 build_chronicle.py。 |
| 7 | LLM 账本如实变冷不过夜 | cached_tokens 75,638 · cache_hit_rate 46.4%。**它不是 SLO，也不许被写成 SLO**；提升缓存 = 缩 prefix、稳 ordering、stream 车道（本仓库已全车道 stream+include_usage）。 |

## 出厂事实（build 时快照）

- commits **2,504** · ledger **1,663** 节 · worldbook **80** 卷
- engineer lane wkapi.pro · gpt-6-sol · stream+include_usage · cached_tokens 75,638
- 端口 8000 归属：port-free · 外网搜索：HTTP 402 · court 永不缓存

## 字典

- **不是 SLO、不是 SLA、不是签字**——记账；
- **欠债画红绿灯，不画口号**——`python scripts/audit_unsigned.py` 每 10ms 一次；
- **git 只收人类确证的证据**——weekly-stress.yml 的 artifact 不自动并入 repo。
