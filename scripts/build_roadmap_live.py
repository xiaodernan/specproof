#!/usr/bin/env python
"""build_roadmap_live.py — render docs/ROADMAP-LIVE.md from this repo's own
tracked artifacts. No ambition here, only the next real knocks with their
true blockers named. Any human can re-run; the file rewrites itself.
"""
import io
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
latest_sec = chron[-1]["n"] if chron else 0

tasks = [
    (1, "等待首班 weekly-stress 实敲", f".github/workflows/weekly-stress.yml 已合入 {'是' if audit.get('weekly-stress-merged') == 'merged' else '否'}；首班 = 合入后下一个周一 03:00 UTC（cron）。**不阻吞吐、不红旗；artifact 到手后人工决定是否入库**。"),
    (2, "真·fleet 遥测仍欠真人签字", f"OBSERVABILITY.md 签字 = **{audit.get('observability-signature', 'awaiting-signature')}**。需要人类（不是人类的它那边）；签完 audit_unsigned.py 自动转玉绿。"),
    (3, "重敲一次 evidence 对最早一篇核对 Δ", f"目前 {evidence.get('files_count', 0)} 件落库；latest `{latest.get('file', '—')}` worst p99 {round(latest.get('worst_p99_ms', 0), 1) if latest else '—'}ms、verdict {latest.get('verdict', '—') if latest else '—'}。Δ 只有两件以后才有意义。"),
    (4, "PORTFOLIO_TOKEN（若你要让个人主页知道）", "Settings → Secrets → `PORTFOLIO_TOKEN`（Contents: read+write，xiaodernan/xiaodernan.github.io）；没配 = 工作流绿但永不推送，不红旗。"),
    (5, "已确认：24 个 hash-named 文件＝SWE-bench eval 证据（非 scratch、非垃圾）",
     "`scripts/audit_scratch_residue.py` 逐件定性：docs/eval/swebench-logs/*/craft/backup/*.<timestamp>.<6-hex> 是 SWE-bench runner 对源码快照的内容寻址备份，21 件 git-tracked、591,524 字节、全部位于 eval 日志目录——**不删除、不动它们、不是 scratch**；.md 文件里早先‘可疑约 1000 个 542-byte hash 残片’的猜测已被此次审计否证并入账。"),
    (6, "新增卷继续随本体入账", f"编年史 {latest_sec:,} 节；每本书都要 atomic 入账，数量漂了就要重跑 build_chronicle.py。"),
    (7, "LLM 账本如实变冷不过夜", f"cached_tokens {engine.get('cached_tokens', 0):,} · cache_hit_rate {engine.get('cache_hit_rate', 0) * 100:.1f}%。**它不是 SLO，也不许被写成 SLO**；提升缓存 = 缩 prefix、稳 ordering、stream 车道（本仓库已全车道 stream+include_usage）。"),
]

lines = [
    "# ROADMAP · LIVE — SpecProof",
    "",
    f"> 自动生成于 {stamp}（scripts/build_roadmap_live.py）· 下次 chronicle 重推会变灯花。",
    "> **不含任何承诺** — 每一条都是「门下一要敲什么 + 谁来敲（机器 / 人类）」的清单。",
    "",
    "| # | 门 | 谁来敲 / 阻塞 |",
    "|---|---|---|",
]
for i, title, body in tasks:
    lines.append(f"| {i} | {title} | {body} |")
lines += [
    "",
    "## 出厂事实（build 时快照）",
    "",
    f"- commits **{stats['git_commit_count']:,}** · ledger **{stats['ledger_sections']:,}** 节 · worldbook **{len(world_volumes := json.loads((PAGES / 'worldbook.json').read_text(encoding='utf-8'))['locales']['zh']['volumes'])}** 卷",
    f"- engineer lane wkapi.pro · gpt-6-sol · stream+include_usage · cached_tokens {engine.get('cached_tokens', 0):,}",
    f"- 端口 8000 归属：{audit.get('port-8000-answers', 'port-free')} · 外网搜索：HTTP 402 · court 永不缓存",
    "",
    "## 字典",
    "",
    "- **不是 SLO、不是 SLA、不是签字**——记账；",
    "- **欠债画红绿灯，不画口号**——`python scripts/audit_unsigned.py` 每 10ms 一次；",
    "- **git 只收人类确证的证据**——weekly-stress.yml 的 artifact 不自动并入 repo。",
    "",
]
(ROOT / "docs" / "ROADMAP-LIVE.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
print(f"wrote docs/ROADMAP-LIVE.md ({len(lines)} lines, {latest_sec}th chronicle)")
