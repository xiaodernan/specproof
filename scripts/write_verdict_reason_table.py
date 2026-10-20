"""Write the verdict reason table as a human-readable document.

`evidence/verdict.py::REASON_TABLE` is the authority: every reason the
acceptance policy can produce, with the words it is spelled with and the
side of the table it sits on. This script exports it so a reader who does
not read Python can still see the whole vocabulary — and the gate
(`tests/unit/test_verdict_reason_table.py`) checks the document still
matches the code, so the two cannot drift.

    python scripts/write_verdict_reason_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from evidence.verdict import (  # noqa: E402
    REASON_BLOCKING,
    REASON_GAP,
    REASON_TABLE,
)

DOC = REPO_ROOT / "docs" / "architecture" / "VERDICT_REASON_TABLE.md"

KIND_LABEL = {
    REASON_BLOCKING: "阻断（确有问题）",
    REASON_GAP: "缺口（证据不足）",
}


def main() -> int:
    lines = [
        "# 验收判定理由表 (verdict reason table)",
        "",
        "由 `scripts/write_verdict_reason_table.py` 从 "
        "`evidence/verdict.py::REASON_TABLE` 生成；",
        "`tests/unit/test_verdict_reason_table.py` 校验它与代码一致——",
        "**这份文档不是第二份真源，是真源的投影**。",
        "",
        "每一条理由都落在**两栏**的一栏：",
        "",
        "- **阻断（确有问题）**：查出了问题，或记录**自相矛盾**。"
        "读者该去改代码/改记录。",
        "- **缺口（证据不足）**：证据**取不到、归不了、判不了**。"
        "读者该去补证据。两者都 fail-closed，区别在**该谁行动**。",
        "",
        "判定词由**在场的理由种类**推出：有阻断 → BLOCKED；只有缺口 → "
        "NEEDS_REVIEW；有 error → FAILED。",
        "",
        "| 理由 key | 对外措辞 | 归属 |",
        "|---|---|---|",
    ]
    for key, (template, kind) in REASON_TABLE.items():
        lines.append(
            f"| `{key}` | {template} | {KIND_LABEL[kind]} |"
        )
    blocking = sum(1 for _t, k in REASON_TABLE.values() if k == REASON_BLOCKING)
    gaps = sum(1 for _t, k in REASON_TABLE.values() if k == REASON_GAP)
    lines += [
        "",
        f"共 {len(REASON_TABLE)} 条：阻断 {blocking} 条、缺口 {gaps} 条。",
        "",
        "## 行的理由（矩阵行 → 对外措辞）",
        "",
        "矩阵行可以带一个**受控代码**说明自己为什么没结论；判定层"
        "**拥有对外措辞**，节点的自由散文**不会被引用**（那是行级视图的事）。",
        "判定层**算得出**的事实（契约是否获批、这一行是否跑过实验）"
        "**优先于**节点写的标签。",
        "",
        "| 行代码 | 对外措辞 |",
        "|---|---|",
        "| `no_experiment` | 该契约没有任何实验产出结果; 禁止臆造 PASS/FAIL |",
        "| `inconclusive` | 实验已运行但未得到可判定证据, 保持 UNVERIFIED |",
        "| `contract_not_approved` | 契约未获批准: 需人工批准后方可作为验收依据 |",
        "",
        "（这三句由 `evidence/verdict.py::_ROW_REASON_TEXT` 拥有；"
        "上表是它的投影。）",
    ]

    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {DOC.relative_to(REPO_ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
