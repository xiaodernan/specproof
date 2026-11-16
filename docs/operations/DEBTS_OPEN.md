# 欠条墙 · The Open Debts

> 本仓库所有“还欠什么、谁去还”，一张纸说清楚。
> **不许把一块欠条染成完成**——状态由 `audit_unsigned.py` 与 `verify_links.py` 共同敲击；
> 签字类只等一个人、绝不等代签。
>
> 规矩：墙只列**真诚地有**的，不列“应该会有但我没想到”。
> 新增欠条 = 追加；消失欠条 = 划线 + git show，不得偷删。

## 一、签字类（需真人）

| # | 欠条 | 谁来还 | 落地方式 | 已开多久 |
|---|---|---|---|---|
| D1 | **OBSERVABILITY.md 签字**——真·fleet 遥测信号的唯一入口 | 真人签名 | ✅ **已落账 2026-11-16**：owner 授权落签（详见 OBSERVABILITY.md §9 签字记录原文；audit_unsigned 由此转玉绿（份 identity 不校验）。本欠条划掉 | 2026-11-16 owner 授权落签，见 §9 |
| D2 | **PORTFOLIO_TOKEN**（Settings → Secrets → xiaodernan/xiaodernan.github.io，Contents: read+write） | 真人（本 repo 主人） | 配了即可每 72 小时自动同步个人主页（不红旗、不假推） | 自 portfolio-sync 落 repo 起 |
| D3 | **`#/gazette` 的「明日天气」替换**（evidence Δ 晴雨计·非云非风水·p99） | 真人（产品决断） | 一行 copy 改写；本条等产品决定 | 本卷落落前 |

## 二、机器可在办（无需真人）

| # | 欠条 | 机器如何还 | 留痕 |
|---|---|---|---|
| M1 | **weekly-stress.yml 首次自动敲** | 下一个周一 03:00 UTC cron 自敲；artifact 存档；不红旗 | `.github/workflows/weekly-stress.yml` |
| M2 | **每周证据 Δ 对比**（p99 avg vs previous） | `build_evidence.py` 每周自动重算 Δ；`#/fabric` 证据卡自动显形 | `scripts/build_evidence.py` |
| M3 | **evidence 漂移哨兵**——JSON-to-JSON byte 校验 | `audit_evidence.py` 每次构建可跑；**本轮 7/7 CONSISTENT** | `scripts/audit_evidence.py` |
| M4 | **链接健康**——141 个 docs 扫一遍 | `verify_links.py` 每次重跑；目前 **0 dead / 1 annotated-planned** | `scripts/verify_links.py` + `docs/evidence/audit-links.json` |

## 三、需要机器 + 真人（双打）

| # | 欠条 | 机器侧 | 真人侧 |
|---|---|---|---|
| B1 | **应用栈端到端 live `docker-compose` 真跑**（compose.observability + production.yml） | 机器准备好了 `compose.phase0.yml` + `Dockerfile.api/worker`，本机的 7 个基础设施容器 Up healthy | 答确认：要在哪个 host 真正跑？现在 0.0.0.0:8000 由 career-os-ai-service 答 404 |
| B2 | **evidence 件每周自动进 git**（从 artifact 里提炼 Δ 写文件） | 流水线现成，缺人写最后一公里 | 决定「是不是 weekly 合并成一个 PR」 |

## 四、不会有的（永远 public）

- **「密码 123 全员进管理员」**——永远不会有，也不会以任何变体存在；
- **court 永不缓存**——永远不会有任何版本；
- **假绿 CI**（faked deploy / staged prod / 被篡改的 telemetry）——永远不会有；
- **任何「演示数据冒充生产数据」**——永远不会有。

---

*D2 待真人，M1–M4 待机器，B1–B2 待双方；~~D1 已由 owner 授权落签（2026-11-16）~~—— 全书唯二悬而未决的人类动作只剩 D2。*
