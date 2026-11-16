# ROADMAP · LIVE — SpecProof

> 自动生成·2026-11-16 19:55Z（scripts/build_roadmap_live.py）·下次 chronicle 重推会变灯花。
> **不含任何承诺** — 每一条都是「门下一要敲什么 + 谁来敲（机器 / 人类）」的清单。

| # | 件 | 谁来敲 / 阻塞 |
|---|---|---|
| 1 | 等待首班 weekly-stress 实敲 | .github/workflows/weekly-stress.yml 已合入✓；首班 = 合入后下一个周一 03:00 UTC（cron）。**不阻吞吐、不红旗；artifact 到手后人工决定是否入库**。 |
| 2 | 真·fleet 遥测仍欠真人签字 | OBSERVABILITY.md 签字 = **signature-block-found**。需要人类（不是人类的它那边）；签完 audit_unsigned.py 自动转玉绿。 |
| 3 | 重敲一笔 evidence 对最早一篇核 Δ | 目前 27 件落库；latest `2026-11-16-static-warm-15.json` worst p99 2061.0ms、verdict BUDGET-BLOWN。Δ 只有两件以后才有意义。 |
| 4 | PORTFOLIO_TOKEN（若你要让个人主页知道） | Settings → Secrets → `PORTFOLIO_TOKEN`（Contents: read+write，xiaodernan/xiaodernan.github.io）；没配 = 工作流绿但永不推送，不红旗。 |
| 5 | 已确认：24 件 hash-named 文件＝SWE-bench eval 证据（非 scratch、非垃圾） | `scripts/audit_scratch_residue.py` 逐件定性：docs/eval/swebench-logs/*/craft/backup/*.<timestamp>.<6-hex> — SWE-bench runner 对源码快照的内容寻址备份，11 件 git-tracked、91,524 字节、全部位于 eval 日志目录——**不删除、不动它们、不算 scratch**；md 文件里早先‘可疑约 1000 件 542-byte hash 残片’的猜测已被此次审计否证并入账。 |
| 6 | 新增卷继续随本体入账 | 编年 1,742 节；每本书都 atomic 入账，数量漂了就要重跑 build_chronicle.py。 |
| 7 | LLM 账本 live lane | engineer lane = aizzz/gpt-6.1-terra · responses · stream+include_usage；每次 live_lane_probe 敲回 cached_tokens=4,224；两次不同前缀 probe 命中 0/0（R16）。它不是 SLO，也不许被写成 SLO；要提升命中 = 稳 prompt · 稳 ordering · 全车道 stream（本仓库已全车道 stream+include_usage）。 |
| 8 | tests/unit 既存红门登记册（HEAD 复核 · 本夜 #1943 入册） | stash-parity 复核把「本夜引入」与「历史红」完全分开：①设计系统四道门（4 px grid / theme-blind colours / radius ladder / shadows · 计 608/1,315/101/71/406）**一直红着**，计数与 HEAD 一致。【2026-11-17 补记 · #1945/#1946】：4 px 网格 601→**0** · 字阶 scale 406→**0** · 圆角 ladder 101→**0** · 阴影 71→**0**（#1945 落册）；theme-blind 字色 1,315→1,165（#1945）→1,154→950→944→898→775→666→**593**（#1946 实敲）——**只剩字色门红**，久攻不涂绿。【2026-11-17 再补记 · #1947】：theme-blind 字色 593→**0**（逐字节登记为 `--pigment-*` · 463 枚新 token + 13 枚 context-invariant 复用 · `--print-*` lane 不复用 · `test_no_painted_color_bypasses_the_theme_tokens` **3/3 绿**）——**设计系统家族至此全部落窗**（601→0 / 101→0 / 406→0 / 71→0 / 1,315→0）；Item #8 剩余既存红门家族照册不动，不涂绿。【2026-11-17 再补记 · fix/payload-census-ai-summary-stream-register】：payload-census 24 红中 1 红（SSE 端点登记）已于 fix 分支修复，**23 红待主干签核**。【2026-11-17 再补记 · fix/verdict-channel-witness】：verdict_channel_parity **2 红 → 0**：七个 StateGraph + 审计车道十九个文件的 `verdict`（OK/REGRESSION/CRACKED/CLEAR/ASKED/ANSWERED/UNAVAILABLE…）登记为新的 `witness` 通道（18 owners · 15 个 scale 词 · 18 个 opaque 全声明）+ +1 EXEMPT（`build_crewcard_markdown.py` · 纯展示透传）；**分支待签核，主干照红**。同批现况（无涂绿、仅实测）：audit-disposition 全族（test_audit_action_parity / test_branches_without-… / test_review_court_policy / test_tenant_auth / test_the_provider_smoke_ci_leg_carries_the_branch_job / test_audit_disposition_labels）本轮回敲 **139/139 绿**——这一支已在主干；设计系统四门全绿（#1947 落窗）。Item #8 仍未归零的只有 payload-census 一族（23 红待主干签核）。；②`test_the_payload_the_frontend_declares_is_the_payload_a_route_publishes`（24 红）与审计处置签名标签族（16 红）绑定晚中快照体系；③`verdict_channel_parity`（2 红）fail 在 HEAD 同位置。这一整个家族都还欠一个 remediation batch——**签名要落在专门的分支上、按审计正确走，不在本夜补丁封堵**。修复之后，gate 计数必须精确归零（不允许部分涂绿）。 |

## 出厂事实（build 时快照）

- commits **2,606** · ledger **1,742** · worldbook **149** ·
- engineer lane aizzz/gpt-6.1-terra · responses · stream+include_usage · cached_tokens 105,206（live_lane_probe 每次敲回 ~4224；R16）·
- 端口 8000 归属：other-project-answering · 外网搜索：HTTP 402 · court 永不缓存

## 字典

- **不是 SLO、不是 SLA、不是签名**——记账；
- **欠债画红绿灯，不画口号**——`python scripts/audit_unsigned.py`  10ms 一次；
- **git 只收人类确证的证据**——weekly-stress.yml 的 artifact 不自动并入 repo；
