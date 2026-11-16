# ROADMAP · LIVE — SpecProof

> 自动生成于 2026-11-16 09:06Z（scripts/build_roadmap_live.py）· 下次 chronicle 重推会变灯花。
> **不含任何承诺** — 每一条都是「门下一要敲什么 + 谁来敲（机器 / 人类）」的清单。

| # | 门 | 谁来敲 / 阻塞 |
|---|---|---|
| 1 | 等待首班 weekly-stress 实敲 | .github/workflows/weekly-stress.yml 已合入 是；首班 = 合入后下一个周一 03:00 UTC（cron）。**不阻吞吐、不红旗；artifact 到手后人工决定是否入库**。 |
| 2 | 真·fleet 遥测仍欠真人签字 | OBSERVABILITY.md 签字 = **awaiting-signature**。需要人类（不是人类的它那边）；签完 audit_unsigned.py 自动转玉绿。 |
| 3 | 重敲一次 evidence 对最早一篇核对 Δ | 目前 13 件落库；latest `2026-11-16-static-warm-6.json` worst p99 1058.3ms、verdict OK。Δ 只有两件以后才有意义。 |
| 4 | PORTFOLIO_TOKEN（若你要让个人主页知道） | Settings → Secrets → `PORTFOLIO_TOKEN`（Contents: read+write，xiaodernan/xiaodernan.github.io）；没配 = 工作流绿但永不推送，不红旗。 |
| 5 | 已确认：24 个 hash-named 文件＝SWE-bench eval 证据（非 scratch、非垃圾） | `scripts/audit_scratch_residue.py` 逐件定性：docs/eval/swebench-logs/*/craft/backup/*.<timestamp>.<6-hex> 是 SWE-bench runner 对源码快照的内容寻址备份，21 件 git-tracked、591,524 字节、全部位于 eval 日志目录——**不删除、不动它们、不是 scratch**；.md 文件里早先‘可疑约 1000 个 542-byte hash 残片’的猜测已被此次审计否证并入账。 |
| 6 | 新增卷继续随本体入账 | 编年史 1,894 节；每本书都要 atomic 入账，数量漂了就要重跑 build_chronicle.py。 |
| 7 | LLM 账本如实变冷不过夜 | cached_tokens 75,638 · cache_hit_rate 42.1%。**它不是 SLO，也不许被写成 SLO**；提升缓存 = 缩 prefix、稳 ordering、stream 车道（本仓库已全车道 stream+include_usage）。 |

## 出厂事实（build 时快照）

- commits **2,554** · ledger **1,695** 节 · worldbook **111** 卷
- engineer lane wkapi.pro · gpt-6-sol · stream+include_usage · cached_tokens 75,638
- 端口 8000 归属：other-project-answering · 外网搜索：HTTP 402 · court 永不缓存

## 字典

- **不是 SLO、不是 SLA、不是签字**——记账；
- **欠债画红绿灯，不画口号**——`python scripts/audit_unsigned.py` 每 10ms 一次；
- **git 只收人类确证的证据**——weekly-stress.yml 的 artifact 不自动并入 repo。
