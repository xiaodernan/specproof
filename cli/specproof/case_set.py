"""Which golden cases a measurement run actually evaluated.

``agent/holdout.py`` owns the declaration (which cases are held out); this
module owns the only consumer decision that declaration can drive: which
directories a ``specproof eval`` / ``specproof baseline`` run keeps. Both
commands go through ``plan_case_dirs`` so the two sides of a comparison are
produced by one policy — a delta between a 90-case pool and a 100-case pool
would otherwise be reported as a model gain (#77, #78).

Honesty contract, carried in the plan and printed by every caller:

- isolation is ON by default; a declared holdout case does not sit in the
  tuning pool, and a run that ignores the manifest is labelled
  ``all_not_isolated`` rather than silently merged;
- a manifest that will not load is never read as "nothing is held out";
- declared cases that are absent from the directory are reported, because
  "excluded" and "was never here" are different facts;
- every run records its pool in the machine-readable sidecar, so a stored
  number cannot be diffed against a number from another pool without the
  mismatch being visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from agent.holdout import HoldoutError, HoldoutRegistry

#: Case-set modes. The value is what lands in a sidecar, so it is part of the
#: artifact's vocabulary and must not be reworded casually.
CASE_SET_TUNING = "tuning"
CASE_SET_ALL = "all_not_isolated"
CASE_SET_HOLDOUT = "holdout_only"


@dataclass
class CasePlan:
    """The case set for one run, plus what the manifest hid or lost."""

    kept: list[Path]
    mode: str
    excluded: list[str]
    unknown_declared: list[str]
    manifest_path: str
    note: str

    def header_lines(self) -> list[str]:
        lines = [
            f"案例集: {self.mode} — {len(self.kept)} 个案例参与本轮评测"
            + (f"，排除 {len(self.excluded)} 个" if self.excluded else ""),
        ]
        if self.mode == CASE_SET_ALL:
            lines.append(
                "  ! 本轮未做 holdout 隔离（--include-holdout）："
                "这些数字不是未见过案例上的指标。"
            )
        if self.unknown_declared:
            lines.append(
                f"  ! manifest 声明的 {len(self.unknown_declared)} 个案例不在本 "
                "--cases 目录里，所以本轮既没跑它们也没排除它们: "
                + " ".join(sorted(self.unknown_declared))
            )
        if self.note:
            lines.append(f"  manifest note: {self.note}")
        return lines

    def as_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "manifest_path": self.manifest_path,
            "excluded_holdout_cases": sorted(self.excluded),
            "declared_but_absent": sorted(self.unknown_declared),
            "manifest_note": self.note,
        }


def plan_case_dirs(
    case_dirs: list[Path],
    *,
    include_holdout: bool,
    only_holdout: bool,
    manifest_path: str | None,
) -> CasePlan:
    """Split discovered cases against the declared holdout manifest.

    No flag = isolation on: the cases declared off-limits leave the tuning
    pool. ``--only-holdout`` runs just them, which is the only way to report a
    held-out number at all. ``--include-holdout`` restores the pre-#77 merged
    pool and says so on the header.

    A manifest that will not load is never read as "nothing is held out". When
    isolation was asked for that is a hard error: silently keeping the hidden
    cases in the pool is the exact leak the manifest exists to stop.
    """
    try:
        registry = HoldoutRegistry.load(manifest_path)
    except HoldoutError as exc:
        if include_holdout:
            # Nothing is being held out, so the unreadable manifest cannot
            # invalidate the run — but the operator still has to hear that the
            # holdout bookkeeping is missing.
            click.echo(
                f"  ! holdout manifest 不可读（{exc}）：本轮按全部案例跑，"
                "无法标注哪些案例属于隐藏集",
                err=True,
            )
            return CasePlan(
                kept=list(case_dirs),
                mode=CASE_SET_ALL,
                excluded=[],
                unknown_declared=[],
                manifest_path=str(manifest_path or ""),
                note="",
            )
        raise click.ClickException(
            f"holdout manifest 无法读取，隔离无法判定（{exc}）—— 不会把隐藏案例"
            "静默留在调参池里。确认要合并运行请显式传 --include-holdout"
        ) from exc

    present = {d.name for d in case_dirs}
    is_holdout = {d.name: registry.is_holdout(d.name) for d in case_dirs}
    unknown = sorted(
        e.case_id for e in registry.cases() if e.case_id not in present
    )

    if include_holdout:
        kept, mode, excluded = list(case_dirs), CASE_SET_ALL, []
    elif only_holdout:
        kept = [d for d in case_dirs if is_holdout[d.name]]
        mode = CASE_SET_HOLDOUT
        excluded = [d.name for d in case_dirs if not is_holdout[d.name]]
    else:
        kept = [d for d in case_dirs if not is_holdout[d.name]]
        mode = CASE_SET_TUNING
        excluded = [d.name for d in case_dirs if is_holdout[d.name]]

    return CasePlan(
        kept=kept,
        mode=mode,
        excluded=excluded,
        unknown_declared=unknown,
        manifest_path=registry.manifest_path,
        note=registry.note,
    )


def empty_pool_message(discovered: int, plan: CasePlan, cases_path: Path) -> str:
    """Say which decision emptied the pool, not that the directory is empty.

    ``0 cases`` produced by isolation is a manifest outcome; ``no case
    directories`` is a wrong path. Collapsing the two blames the directory for
    a policy, and exiting 0 would claim a verdict from nothing measured.
    """
    if discovered:
        return (
            f"本轮没有可跑案例：{discovered} 个案例在 {cases_path} 目录下，"
            f"被案例集选择（模式 {plan.mode}）全部排除。"
            "要跑全部案例请显式传 --include-holdout。"
        )
    return f"No case directories found in {cases_path}"


def pool_mismatch(
    baseline_label: dict[str, Any] | None,
    other_label: dict[str, Any] | None,
) -> str | None:
    """Why two stored measurement pools cannot be subtracted, or None.

    Used by ``specproof baseline`` before it prints a Go/No-Go gain: a delta
    between different case sets is not a model regression or improvement, it is
    an arithmetic accident. An unlabelled sidecar (written before #77) is
    reported as unknown rather than assumed to match.
    """
    if other_label is None:
        return (
            "对方结果没有 case_set 标签（#77 之前产出的 sidecar）"
            "—— 无法确认两边是同一案例池。"
        )
    mine = (baseline_label or {}).get("mode")
    theirs = other_label.get("mode")
    if mine != theirs:
        return f"案例池模式不同：基线 {mine} vs SpecProof {theirs}。"
    my_excluded = set((baseline_label or {}).get("excluded_holdout_cases") or [])
    their_excluded = set(other_label.get("excluded_holdout_cases") or [])
    if my_excluded != their_excluded:
        diff = ", ".join(sorted(my_excluded ^ their_excluded))
        return f"两边排除的 holdout 案例不一致: {diff}"
    return None


__all__ = [
    "CASE_SET_ALL",
    "CASE_SET_HOLDOUT",
    "CASE_SET_TUNING",
    "CasePlan",
    "empty_pool_message",
    "plan_case_dirs",
    "pool_mismatch",
]
