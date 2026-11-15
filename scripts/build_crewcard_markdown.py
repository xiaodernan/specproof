#!/usr/bin/env python
"""Build the SpecProof crew card markdown (zh + en) from the same git-tracked
JSON the app imports at build time — so the card lives on GitHub's repo view,
on the print A4, and in the app, all from ONE source.

Reads: apps/web/src/pages/repoStats.json, chronicle.json, evidence.json,
unsigned.json, engine.json, worldbook.json.
Writes: docs/crewcard.md, docs/crewcard-en.md

The card carries only git-tracked facts. No signature is pressed.
"""
import io
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "apps" / "web" / "src" / "pages"

def j(name: str):
    return json.loads((PAGES / name).read_text(encoding="utf-8"))

stats = j("repoStats.json")
chron = j("chronicle.json")
evidence = j("evidence.json")
unsigned = j("unsigned.json")
engine = j("engine.json")
world = j("worldbook.json")

latest = evidence.get("latest") or {}
delta = evidence.get("delta_vs_previous") or None
audit = {c["id"]: c["status"] for c in unsigned.get("checks", [])}
zh_volumes = len(world.get("locales", {}).get("zh", {}).get("volumes", []))
en_volumes = len(world.get("locales", {}).get("en", {}).get("volumes", []))
stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def card(zh: bool) -> str:
    h = ("# SpecProof · 船员卡" if zh else "# SpecProof · FIELD CARD")
    head = (f"> xiaodernan/specproof · {'打印于' if zh else 'generated at'} {stamp}\n> "
            + ("本卡只刻本仓库 git-tracked 的事实；它不是签字、不是验收、不是承诺。"
               if zh else
               "This card prints only git-tracked facts. It is not a signature, not a seal, not a promise."))
    rows1 = [
        ("git 提交" if zh else "commits", f"{stats['git_commit_count']:,}"),
        ("账本节数" if zh else "ledger sections", f"{stats['ledger_sections']:,}"),
        ("世界书卷（zh/en）" if zh else "volumes (zh/en)", f"{zh_volumes} / {en_volumes}"),
        ("源码行数" if zh else "source lines", f"{stats['total_lines_of_source']:,}"),
        ("Python 测试文件" if zh else "Python test files", f"{stats.get('python_test_files', 0):,}"),
        ("前端测试文件" if zh else "web test files", f"{stats.get('web_test_files', 0):,}"),
        ("账本字节 (KB)" if zh else "ledger bytes (KB)", f"{stats.get('ledger_bytes_kB', 0):.1f}"),
        ("编年史最新节" if zh else "latest chronicle", f"#{chron[-1]['n'] if chron else '—'}"),
    ]
    table = "\n".join(f"| {k} | {v} |" for k, v in rows1)
    ev = (
        f"| {'证据件' if zh else 'evidence'} | `{latest.get('file', '—')}` |\n"
        f"| {'worst p99' if zh else 'worst p99'} | {round(latest.get('worst_p99_ms', 0), 1) if latest else '—'} ms |\n"
        f"| {'判定' if zh else 'verdict'} | {latest.get('verdict', '—') if latest else '—'} |\n"
        f"| Δ vs {'上一件' if zh else 'previous'} | {f'{delta["worst_p99_delta_ms"]:+.1f}ms' if delta else '—'} |"
    )
    obs = audit.get("observability-signature", "awaiting-signature")
    wk = audit.get("weekly-stress-merged", "missing")
    port = audit.get("port-8000-answers", "port-free")
    cap = (f"| {'真·fleet 遥测 · OBSERVABILITY.md 签字' if zh else 'real fleet telemetry · sign-off'} | {obs} |\n"
           f"| {'每周一敲门 · weekly-stress.yml' if zh else 'the Monday knock · weekly-stress.yml'} | {wk} |\n"
           f"| {'端口 8000 · 此刻谁在答' if zh else 'port 8000 · who answers right now'} | {port} |")
    verify = (
        "```\ngit log --oneline -1 && python scripts/build_repo_stats.py && python scripts/audit_unsigned.py\n```\n"
        "\n"
        + ("本卡每一个数字都能敲开：chronicle.json · repoStats.json · evidence.json · unsigned.json · engine.json（全部 git-tracked）。\n"
           if zh else
           "Every digit re-opens: chronicle.json · repoStats.json · evidence.json · unsigned.json · engine.json (all git-tracked).\n")
        + ("LLM 账本：openai_compat · wkapi.pro · stream+include_usage 车道；cached_tokens："
           f"{engine.get('cached_tokens', 0):,}（{engine.get('cache_hit_rate', 0) * 100:.1f}% 前缀命中——不是 SLA）\n"
           if zh else
           f"LLM ledger: openai_compat · wkapi.pro · stream+include_usage; cached_tokens {engine.get('cached_tokens', 0):,} "
           f"({engine.get('cache_hit_rate', 0) * 100:.1f}% prefix-hit, not an SLA)\n")
        + (
            "\n> 本卡不含任何密钥、任何 API key、任何签名——本仓库从来不会把 `sk-…` 写进任何 git-tracked 文件。\n"
            if zh else
            "\n> This card carries no keys, no secrets, no signatures — this repository never writes an `sk-…` into any git-tracked file.\n"
        )
    )
    return (
        f"{h}\n\n{head}\n\n## {'数字墙' if zh else 'The wall'}\n\n| | |\n|---|---|\n{table}\n\n"
        f"## {'压测证据' if zh else 'Stress evidence'}\n\n| | |\n|---|---|\n{ev}\n\n"
        f"## {'欠签（live 审计）' if zh else 'Unsigned (live audit)'}\n\n| | |\n|---|---|\n{cap}\n\n"
        f"{verify}\n"
    )

(ROOT / "docs" / "crewcard.md").write_text(card(True), encoding="utf-8")
(ROOT / "docs" / "crewcard-en.md").write_text(card(False), encoding="utf-8")
print("wrote docs/crewcard.md and docs/crewcard-en.md")
print("audit:", audit)
