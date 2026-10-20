"""Write the experiment-class coverage report (docs/eval/…).

The report says, per experiment class, which of the three samples it
has: a POSITIVE (must be caught), a NEGATIVE (must not be flagged) and
a HOLDOUT (reserved for evaluation). A missing one is printed as an
empty cell with a dash — never as a tick, and never silently.

    python scripts/write_experiment_class_coverage.py

`tests/unit/test_experiment_class_samples.py` checks that the committed
report still matches the registry, so the recorded gap cannot rot into
a claim of coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from experiments.experiment_classes import (  # noqa: E402
    EXPERIMENT_CLASSES,
    MECHANISM_DIFFERENTIAL_TEST,
)

REPORT = REPO_ROOT / "docs" / "eval" / "experiment-class-coverage.md"


def _row(key: str, family: str, mechanism: str, samples: dict[str, str]) -> str:
    def mark(role: str) -> str:
        case_id = samples.get(role, "")
        return f"✅ {case_id}" if case_id else "—"

    return (
        f"| {key} | {family} | {mechanism} | "
        f"{mark('positive')} | {mark('negative')} | {mark('holdout')} |"
    )


def main() -> int:
    lines = [
        "# 实验类样本覆盖 (experiment class sample coverage)",
        "",
        "由 `scripts/write_experiment_class_coverage.py` 生成；",
        "`tests/unit/test_experiment_class_samples.py` 校验它与",
        "`experiments/experiment_classes.py` 注册表一致——",
        "**记录下来的缺口不会悄悄变成覆盖率声明**。",
        "",
        "每个实验类需要三个样本：",
        "",
        "- **正样本**（positive）：必须被抓到的缺陷；",
        "- **负样本**（negative）：不得被误报的重构/注释改动；",
        "- **holdout**：留出给评测的案例（调参时不看）。",
        "",
        "holdout 缺失是真的缺口，不是格式问题：一个案例不能既是调参样本又是 holdout。",
        "",
        "| 实验类 | 契约家族 | 机制 | 正样本 | 负样本 | holdout |",
        "|---|---|---|---|---|---|",
    ]
    for entry in EXPERIMENT_CLASSES:
        mechanism = (
            "生成式差分测试"
            if entry.mechanism == MECHANISM_DIFFERENTIAL_TEST
            else "静态检查器"
        )
        lines.append(_row(
            entry.key,
            entry.family,
            mechanism,
            {
                "positive": entry.positive_sample,
                "negative": entry.negative_sample,
                "holdout": entry.holdout_sample,
            },
        ))

    gaps = [
        entry for entry in EXPERIMENT_CLASSES if entry.missing_samples()
    ]
    lines += ["", "## 缺口", ""]
    if not gaps:
        lines.append("无：六类都齐了正样本、负样本与 holdout。")
    else:
        for entry in gaps:
            lines.append(
                f"- **{entry.key}**（{entry.family}）缺："
                + "、".join(entry.missing_samples())
            )
        lines += [
            "",
            "补一个案例需要走 `scripts/build_golden_scenarios.py` 的数据定义"
            "（`_case(...)` 一条），并在 `docs/eval/holdout-manifest.json` 登记"
            "（注意：该清单的 `family` 字段有新旧两套词表并存，见其 `note`）。",
        ]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT.relative_to(REPO_ROOT)} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
