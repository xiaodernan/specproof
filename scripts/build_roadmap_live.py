#!/usr/bin/env python
"""build_roadmap_live.py — render docs/ROADMAP-LIVE.md from this repo's own
tracked artifacts. No ambition here, only the next real knocks with their
true blockers named. Any human can re-run; the file rewrites itself.
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "apps" / "web" / "src" / "pages"

stats = json.loads((PAGES / "repoStats.json").read_text(encoding="utf-8"))
chron = json.loads((PAGES / "chronicle.json").read_text(encoding="utf-8"))
evidence = json.loads((PAGES / "evidence.json").read_text(encoding="utf-8"))
unsigned = json.loads((PAGES / "unsigned.json").read_text(encoding="utf-8"))
engine = json.loads((PAGES / "engine.json").read_text(encoding="utf-8"))
latest = evidence.get("latest") or {}
audit = {c["id"]: c["status"] for c in unsigned.get("checks", [])}
stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%MZ")
latest_sec = len(chron) if chron else 0

tasks = [
    (1, "等待首班 weekly-stress 实敲", f".github/workflows/weekly-stress.yml 已合入{'✓' if audit.get('weekly-stress-merged') == 'merged' else '✗'}；首班 = 合入后下一个周一 03:00 UTC（cron）。**不阻吞吐、不红旗；artifact 到手后人工决定是否入库**。"),
    (2, "真·fleet 遥测仍欠真人签字", f"OBSERVABILITY.md 签字 = **{audit.get('observability-signature', 'awaiting-signature')}**。需要人类（不是人类的它那边）；签完 audit_unsigned.py 自动转玉绿。"),
    (3, "重敲一笔 evidence 对最早一篇核 Δ", f"目前 {evidence.get('files_count', 0)} 件落库；latest `{latest.get('file', '?')}` worst p99 {round(latest.get('worst_p99_ms', 0), 1) if latest else '?'}ms、verdict {latest.get('verdict', '?') if latest else '?'}。Δ 只有两件以后才有意义。"),
    (4, "PORTFOLIO_TOKEN（若你要让个人主页知道）", "Settings → Secrets → `PORTFOLIO_TOKEN`（Contents: read+write，xiaodernan/xiaodernan.github.io）；没配 = 工作流绿但永不推送，不红旗。"),
    (5, "已确认：24 件 hash-named 文件＝SWE-bench eval 证据（非 scratch、非垃圾）",
     "`scripts/audit_scratch_residue.py` 逐件定性：docs/eval/swebench-logs/*/craft/backup/*.<timestamp>.<6-hex> — SWE-bench runner 对源码快照的内容寻址备份，11 件 git-tracked、91,524 字节、全部位于 eval 日志目录——**不删除、不动它们、不算 scratch**；md 文件里早先‘可疑约 1000 件 542-byte hash 残片’的猜测已被此次审计否证并入账。"),
    (6, "新增卷继续随本体入账", f"编年 {latest_sec:,} 节；每本书都 atomic 入账，数量漂了就要重跑 build_chronicle.py。"),
    (7, "LLM 账本 live lane", "engineer lane = aizzz/gpt-6.1-terra · responses · stream+include_usage；每次 live_lane_probe 敲回 cached_tokens=4,224；两次不同前缀 probe 命中 0/0（R16）。它不是 SLO，也不许被写成 SLO；要提升命中 = 稳 prompt · 稳 ordering · 全车道 stream（本仓库已全车道 stream+include_usage）。"),
    (8, "tests/unit 既存红门登记册（#1943 入册 · #2082 归零设计系统五门）",
     "stash-parity 复核把「本夜引入」与「历史红」完全分开。①**设计系统是五道门**（4 px grid / theme-blind colours / radius ladder / shadows / **字阶 scale**——本条原文只点了四个名字却记了五个数，那个 406 是字阶，它从未被点名），在 #2082 **全部归零**：PRE-FIX 实测 **57/79/10/5/42 → 0/0/0/0/0**，签名落在专门分支 `fix/design-system-remediation`（**尚未并入 master**），并新增「每个 var() 必须指向已声明或已注入的属性」的门——原有 **51** 处空洞（其中 25 处无 fallback，浏览器直接丢弃整条声明）→ 0。②`test_the_payload_the_frontend_declares_is_the_payload_a_route_publishes`（24 红）与审计处置签名标签族（16 红）绑定晚中快照体系，**仍红**；③`verdict_channel_parity`（2 红）fail 在 HEAD 同位置，**仍红**。②③ 仍欠一个 remediation batch——**签名要落在专门的分支上、按审计正确走，不在补丁里封堵**。修复之后，gate 计数必须精确归零（不允许部分涂绿）。"),
]

lines = [
    "# ROADMAP · LIVE — SpecProof",
    "",
    f"> 自动生成·{stamp}（scripts/build_roadmap_live.py）·下次 chronicle 重推会变灯花。",
    "> **不含任何承诺** — 每一条都是「门下一要敲什么 + 谁来敲（机器 / 人类）」的清单。",
    "",
    "| # | 件 | 谁来敲 / 阻塞 |",
    "|---|---|---|",
]
for i, title, body in tasks:
    lines.append(f"| {i} | {title} | {body} |")
lines += [
    "",
    "## 出厂事实（build 时快照）",
    "",
    f"- commits **{stats['git_commit_count']:,}** · ledger **{stats['ledger_sections']:,}** · worldbook **{len(world_volumes := json.loads((PAGES / 'worldbook.json').read_text(encoding='utf-8'))['locales']['zh']['volumes'])}** ·",
    f"- engineer lane aizzz/gpt-6.1-terra · responses · stream+include_usage · cached_tokens {engine.get('cached_tokens', 0):,}（live_lane_probe 每次敲回 ~4224；R16）·",
    f"- 端口 8000 归属：{audit.get('port-8000-answers', 'port-free')} · 外网搜索：HTTP 402 · court 永不缓存",
    "",
    "## 字典",
    "",
    "- **不是 SLO、不是 SLA、不是签名**——记账；",
    "- **欠债画红绿灯，不画口号**——`python scripts/audit_unsigned.py`  10ms 一次；",
    "- **git 只收人类确证的证据**——weekly-stress.yml 的 artifact 不自动并入 repo；",
    "",
]
(ROOT / "docs" / "ROADMAP-LIVE.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
print(f"wrote docs/ROADMAP-LIVE.md ({len(lines)} lines, {latest_sec}th chronicle)")
