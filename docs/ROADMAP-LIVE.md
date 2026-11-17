# ROADMAP · LIVE — SpecProof

> 自动生成·2026-11-17 15:41Z（scripts/build_roadmap_live.py）·下次 chronicle 重推会变灯花。
> **不含任何承诺** — 每一条都是「门下一要敲什么 + 谁来敲（机器 / 人类）」的清单。

| # | 件 | 谁来敲 / 阻塞 |
|---|---|---|
| 1 | 等待首班 weekly-stress 实敲 | .github/workflows/weekly-stress.yml 已合入✓；首班 = 合入后下一个周一 03:00 UTC（cron）。**不阻吞吐、不红旗；artifact 到手后人工决定是否入库**。 |
| 2 | 真·fleet 遥测仍欠真人签字 | OBSERVABILITY.md 签字 = **signature-block-found**。需要人类（不是人类的它那边）；签完 audit_unsigned.py 自动转玉绿。 |
| 3 | 重敲一笔 evidence 对最早一篇核 Δ | 目前 34 件落库；latest `2026-11-17-static-warm-18.json` worst p99 2027.1ms、verdict OK。Δ 只有两件以后才有意义。 |
| 4 | PORTFOLIO_TOKEN（若你要让个人主页知道） | Settings → Secrets → `PORTFOLIO_TOKEN`（Contents: read+write，xiaodernan/xiaodernan.github.io）；没配 = 工作流绿但永不推送，不红旗。 |
| 5 | 已确认：24 件 hash-named 文件＝SWE-bench eval 证据（非 scratch、非垃圾） | `scripts/audit_scratch_residue.py` 逐件定性：docs/eval/swebench-logs/*/craft/backup/*.<timestamp>.<6-hex> — SWE-bench runner 对源码快照的内容寻址备份，11 件 git-tracked、91,524 字节、全部位于 eval 日志目录——**不删除、不动它们、不算 scratch**；md 文件里早先‘可疑约 1000 件 542-byte hash 残片’的猜测已被此次审计否证并入账。 |
| 6 | 新增卷继续随本体入账 | 编年 1,774 节；每本书都 atomic 入账，数量漂了就要重跑 build_chronicle.py。 |
| 7 | LLM 账本 live lane | engineer lane = aizzz/gpt-6.1-terra · responses · stream+include_usage；每次 live_lane_probe 敲回 cached_tokens=4,224；两次不同前缀 probe 命中 0/0（R16）。它不是 SLO，也不许被写成 SLO；要提升命中 = 稳 prompt · 稳 ordering · 全车道 stream（本仓库已全车道 stream+include_usage）。 |
| 8 | tests/unit 既存红门登记册（HEAD 复核 · 本夜 #1943 入册） | stash-parity 复核把「本夜引入」与「历史红」完全分开：①设计系统四道门（4 px grid / theme-blind colours / radius ladder / shadows · 计 608/1,315/101/71/406）**一直红着**，计数与 HEAD 一致；②`test_the_payload_the_frontend_declares_is_the_payload_a_route_publishes`（24 红）与审计处置签名标签族（16 红）绑定晚中快照体系；③`verdict_channel_parity`（2 红）fail 在 HEAD 同位置。这一整个家族都还欠一个 remediation batch——**签名要落在专门的分支上、按审计正确走，不在本夜补丁封堵**。修复之后，gate 计数必须精确归零（不允许部分涂绿）。 |

## 出厂事实（build 时快照）

- commits **2,654** · ledger **1,774** · worldbook **178** ·
- engineer lane aizzz/gpt-6.1-terra · responses · stream+include_usage · cached_tokens 105,206（live_lane_probe 每次敲回 ~4224；R16）·
- 端口 8000 归属：other-project-answering · 外网搜索：HTTP 402 · court 永不缓存

## 字典

- **不是 SLO、不是 SLA、不是签名**——记账；
- **欠债画红绿灯，不画口号**——`python scripts/audit_unsigned.py`  10ms 一次；
- **git 只收人类确证的证据**——weekly-stress.yml 的 artifact 不自动并入 repo；
