"""#216: the §5 alert table in docs/operations/OBSERVABILITY.md and the
deployed rules in infra/prometheus/alerts-slo.yml are two hand-maintained
copies of the same rules. The table had already drifted — two alerts
(SpecproofNoEvidenceSevereComment, SpecproofCapsuleReplayRateLow) were
missing and the ops-checklist prose still said "13 条" while 15 rules were
deployed. This gate makes the pair move together:

- the §5 table lists every deployed alert and nothing else;
- the ops-checklist prose count ("可见 N 条 specproof-slo 规则") equals the
  deployed rule count;
- every row's `for` cell matches the rule's `for`;
- every row's threshold variable matches the rule's expr threshold — the
  replay-rate rule alerts on the FAILURE share (1 - success rate), so its
  row's 0.95 is compared as the complement;
- the tick-stale threshold is 3 default tick periods — the multiple is
  claimed in BOTH the yml THRESHOLDS header ("3×300s") and the §5 row
  ("3×默认 tick 300s"); #215 read only the alert's own annotations and
  recorded it as unclaimed, so the correction rides in #216.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OBS = ROOT / "docs" / "operations" / "OBSERVABILITY.md"
YML = ROOT / "infra" / "prometheus" / "alerts-slo.yml"

#: Rules whose expr fires on the FAILURE share: expr threshold is 1 - rate.
_COMPLEMENT_ROWS = {"SpecproofCapsuleReplayRateLow"}


def _deployed() -> dict[str, dict[str, str]]:
    """Deployed alert name -> its expr and for, with a floored parse."""
    data = yaml.safe_load(YML.read_text(encoding="utf-8"))
    out = {
        rule["alert"]: {
            "expr": str(rule.get("expr", "")),
            "for": str(rule.get("for", "")),
        }
        for group in data["groups"]
        for rule in group["rules"]
        if rule.get("alert")
    }
    assert len(out) >= 10, f"deployed-rule parse collapsed: {len(out)} rules"
    return out


def _table_rows() -> dict[str, tuple[str, str]]:
    """§5 rows: alert name -> (for cell, threshold-variable cell)."""
    text = OBS.read_text(encoding="utf-8")
    section = text[text.index("## 5. SLO 告警"):text.index("## 6. SLO 接线状态")]
    rows: dict[str, tuple[str, str]] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 6 and cells[1].startswith("Specproof"):
            rows[cells[1]] = (cells[3], cells[4])
    assert len(rows) >= 10, f"§5 table parse collapsed: {len(rows)} rows"
    return rows


def _expr_threshold(expr: str) -> float | None:
    matches = re.findall(r">\s*([0-9]+(?:\.[0-9]+)?)", expr)
    return float(matches[-1]) if matches else None


def test_alert_table_lists_every_deployed_rule() -> None:
    deployed = _deployed()
    rows = _table_rows()
    assert set(rows) == set(deployed), (
        f"§5 table vs deployed rules diverge: only in the table "
        f"{sorted(set(rows) - set(deployed))}; only deployed "
        f"{sorted(set(deployed) - set(rows))}"
    )
    text = OBS.read_text(encoding="utf-8")
    match = re.search(r"可见 (\d+) 条 specproof-slo 规则", text)
    assert match is not None, "ops-checklist rule-count claim not found"
    assert int(match.group(1)) == len(deployed), (
        f"prose claims {match.group(1)} rules, {len(deployed)} are deployed"
    )


def test_alert_table_thresholds_match_the_deployed_rules() -> None:
    deployed = _deployed()
    for name, (for_cell, var_cell) in _table_rows().items():
        rule = deployed[name]
        assert for_cell == rule["for"], (
            f"{name}: the row says for={for_cell!r}, the deployed rule "
            f"says for={rule['for']!r}"
        )
        threshold = _expr_threshold(rule["expr"])
        if threshold is None:
            assert var_cell == "—", (
                f"{name}: the expr carries no `> N` threshold but the row "
                f"names one: {var_cell!r}"
            )
            continue
        if name in _COMPLEMENT_ROWS:
            threshold = round(1.0 - threshold, 10)
        match = re.search(r"=([0-9]+(?:\.[0-9]+)?)$", var_cell)
        assert match is not None, (
            f"{name}: row has no `NAME=N` threshold cell: {var_cell!r}"
        )
        assert float(match.group(1)) == threshold, (
            f"{name}: the row says {match.group(1)}, the deployed expr "
            f"fires at {threshold}"
        )


def test_tick_stale_threshold_is_three_tick_periods() -> None:
    from agent.worker import DEFAULT_RECLAIM_INTERVAL_SECONDS

    threshold = _expr_threshold(
        _deployed()["SpecproofWorkerReclaimTickStale"]["expr"]
    )
    assert threshold == 3.0 * float(DEFAULT_RECLAIM_INTERVAL_SECONDS), (
        f"tick-stale fires at {threshold}s but both the yml THRESHOLDS "
        f"header and the §5 row claim 3 x "
        f"{DEFAULT_RECLAIM_INTERVAL_SECONDS}s"
    )
