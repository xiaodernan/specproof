"""#218 — every SLO figure the dashboard DRAWS or NAMES traces to a declaration.

The dashboard is the surface on-call actually reads, and it copies SLO figures
by hand in three different mechanisms:

- **guide lines** — a target whose whole expr is a bare number (panel 12 draws
  ``480`` and ``1500``, panel 16 draws ``1``, panel 18 draws ``2``);
- **colour steps** — ``fieldConfig.defaults.thresholds.steps`` values (panel 17
  paints red at 900, panel 18 red at 2, panel 14 yellow 20 / red 50, panel 20
  red 1, panel 2 red 1 as the fallback outside its value mappings);
- **panel titles** — ``(§14: p95 <= 1s)``, ``(§14: FAST p50<=3min/p95<=8min,
  DEEP p50<=10min/p95<=25min)``, ``(§14: >=95%)``, ``(应为 0)``, ``(§14 质量目标: =0)``.

Before this unit nothing read those copies. #216 binds OBSERVABILITY.md §5 to
the deployed rules and #217 binds the metric inventory to emission sites, but
the 7 drawn figures and the 12 title figures in the dashboard were free to
drift away from both their rule (``alerts-slo.yml`` expr) and their origin
(``docs/PRODUCTION_SPEC.txt`` §14). Measured defect this unit found: **panel 14
paints yellow at 20 and the figure 20 exists nowhere else in the repository** —
not in the rule (> 50), not in §5's row (OUTBOX_PENDING_THRESHOLD=50), not in
§14. The band now declares itself on the surface that draws it (panel
description), and this gate re-derives it: the red step must equal the covering
rule's threshold, the warning step must be strictly below it and must equal no
deployed threshold.

Derivation, not literals: the two declaration files are parsed at test time
(pyyaml for the rules — a declared dependency — and a slice of PRODUCTION_SPEC
for §14), and the join between a panel and a rule is the rule's own series
selector meeting the panel's own exprs (histogram ``_bucket`` reduced to the
base name, same convention as the parity gate). No panel id and no threshold
value is hand-copied into this file, so a legal re-tune that moves the rule and
the panel together keeps the gate green (negative control arm A7) while a
one-sided move reddens it.

Honest boundaries: the gate binds a title figure to §14 by VALUE and UNIT, not
by which §14 line it came from — the metric-level binding is the rule join.
Panel *description* prose figures other than the two Outbox bands (window
lengths, ladder ranges, node-count floors) stay unbound here; the ladder ranges
are bound to their declaring constants by #215 and the §5 rule table by #216.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
_DASH = ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json"
_RULES = ROOT / "infra" / "prometheus" / "alerts-slo.yml"
_SPEC = ROOT / "docs" / "PRODUCTION_SPEC.txt"

#: Series selectors: product metrics plus the two exporters the SLO rules also
#: watch (rabbitmq queue depth, Prometheus' own target liveness).
_SERIES = re.compile(r"\b(specproof_[a-z0-9_]+|rabbitmq_[a-z0-9_]+|up)\b")
#: A rule compares its series against exactly one SLO figure.
_COMPARISON = re.compile(r"(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+)?)")
#: A figure in prose: an operator plus a number plus an optional unit, or a
#: bare percentage. Quantile LABELS (p50, p95) carry no operator so they are
#: never picked up as figures; neither are §- or issue references.
_FIGURE = re.compile(
    r"(?P<op>>=|<=|==|!=|>|<|=|应为)\s*(?P<num>[0-9]+(?:\.[0-9]+)?)"
    r"\s*(?P<unit>%|min|分钟|s|秒)?"
    r"|(?P<pct>[0-9]+(?:\.[0-9]+)?)\s*%"
)
_BARE_NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_MINUTES_TO_SECONDS = 60.0

#: Grafana paints a colour step when the value reaches it (>=), so the first
#: painted state of a "> N" rule over an INTEGER count is N+1: painting at N
#: would show red for a state that never alerts, painting later would hide the
#: alerting value. Keyed by alert name — never by panel position — and the gate
#: asserts every entry here is actually exercised, so an entry that stops
#: matching anything cannot rot into a free pass.
_FIRST_PAINTED_STATE = {
    "SpecproofVerifyDlqNonEmpty": (
        "panel 20 (sum of rabbitmq_queue_messages over *.dlq): dead letters are "
        "whole messages, the rule fires at > 0, so the first red integer is 1"
    ),
}

#: Rules whose expr fires on the FAILURE share while the declared SLO figure
#: names the success rate (#216's complement rows, same shape).
_COMPLEMENT_RULES = {
    "SpecproofCapsuleReplayRateLow": (
        "panel 29 titles the §14 target as 成功率 >= 95% while the rule compares "
        "the confirmed-regression share against > 0.05"
    ),
}


def _panels() -> list[dict[str, Any]]:
    panels = json.loads(_DASH.read_text(encoding="utf-8"))["panels"]
    assert isinstance(panels, list) and len(panels) >= 40, "dashboard parse collapsed"
    return panels


def _series_names(text: str) -> set[str]:
    """Series a piece of PromQL touches, histogram exposition folded back."""
    found = set(_SERIES.findall(text))
    return {
        name[: -len("_bucket")] if name.endswith("_bucket") else name
        for name in found
    }


def _expr_text(panel: dict[str, Any]) -> str:
    return " ".join(str(target.get("expr", "")) for target in panel.get("targets", []))


def _deployed_rules() -> dict[str, tuple[str, float, set[str]]]:
    """alert name -> (comparison operator, threshold, series it watches)."""
    rules = yaml.safe_load(_RULES.read_text(encoding="utf-8"))["groups"][0]["rules"]
    out: dict[str, tuple[str, float, set[str]]] = {}
    for rule in rules:
        comparisons = _COMPARISON.findall(str(rule["expr"]))
        assert len(comparisons) == 1, (
            f"{rule['alert']} does not compare against exactly one SLO figure: "
            f"{comparisons}"
        )
        operator, value = comparisons[0]
        out[str(rule["alert"])] = (operator, float(value), _series_names(str(rule["expr"])))
    assert len(out) >= 10, f"rule parse collapsed: {len(out)}"
    return out


def _covering_rules(
    panel: dict[str, Any], rules: dict[str, tuple[str, float, set[str]]]
) -> dict[str, tuple[str, float, set[str]]]:
    series = _series_names(_expr_text(panel))
    return {name: rec for name, rec in rules.items() if rec[2] & series}


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _drawn_figures(panel: dict[str, Any]) -> list[tuple[str, str | None, float]]:
    """The numbers the dashboard itself paints: guide-line targets and colour steps."""
    out: list[tuple[str, str | None, float]] = []
    for target in panel.get("targets", []):
        expr = str(target.get("expr", "")).strip()
        if _BARE_NUMBER.fullmatch(expr):
            out.append(("guide_line", None, float(expr)))
    steps = (
        panel.get("fieldConfig", {})
        .get("defaults", {})
        .get("thresholds", {})
        .get("steps", [])
    )
    for step in steps:
        value = step.get("value")
        if value is not None:
            out.append(("colour_step", str(step.get("color")), float(value)))
    return out


def _title_figures(title: str) -> list[tuple[str | None, float, str | None]]:
    out: list[tuple[str | None, float, str | None]] = []
    for match in _FIGURE.finditer(title):
        if match.group("pct") is not None:
            out.append((None, float(match.group("pct")), "%"))
        else:
            out.append(
                (
                    str(match.group("op")),
                    float(match.group("num")),
                    match.group("unit"),
                )
            )
    return out


def _warning_band_declared(
    panel: dict[str, Any], value: float, covering: dict[str, tuple[str, float, set[str]]]
) -> bool:
    """An early-warning band has no rule, so it must declare itself where it is
    drawn: the panel description names both figures (yellow=<value>, red=<the
    rule's threshold>) and the rule it sits below."""
    firing = [rec[1] for rec in covering.values() if rec[0] in (">", ">=")]
    if not firing or value >= min(firing):
        return False
    description = str(panel.get("description", ""))
    if not any(name in description for name in covering):
        return False
    return (
        f"yellow={_num(value)}" in description
        and f"red={_num(min(firing))}" in description
    )


def _failure_value(covering: dict[str, tuple[str, float, set[str]]]) -> float | None:
    """The liveness value the down-rules declare (``up == 0``); all of them must
    agree or the surface cannot have one colour scheme."""
    downs = {rec[1] for rec in covering.values() if rec[0] == "=="}
    return next(iter(downs)) if len(downs) == 1 else None


# ── case 1: every drawn figure is a deployed threshold, or a declared band ──


def test_every_drawn_dashboard_figure_is_a_deployed_threshold_or_a_declared_band() -> None:
    rules = _deployed_rules()
    unexplained: list[str] = []
    branches: dict[str, int] = {}
    painted_by: set[str] = set()
    drawn = 0
    for panel in _panels():
        figures = _drawn_figures(panel)
        if not figures:
            continue
        covering = _covering_rules(panel, rules)
        failure = _failure_value(covering)
        for kind, color, value in figures:
            drawn += 1
            explained: str | None = None
            if any(rec[1] == value for rec in covering.values()):
                explained = "rule_threshold"
            else:
                for name, rec in covering.items():
                    if (
                        name in _FIRST_PAINTED_STATE
                        and rec[0] in (">", ">=")
                        and value == rec[1] + 1
                    ):
                        explained = "first_painted_state"
                        painted_by.add(name)
                        break
            if (
                explained is None
                and "up" in _series_names(_expr_text(panel))
                and failure is not None
                and value in (failure, failure + 1)
            ):
                explained = "liveness_state"
            if (
                explained is None
                and color == "yellow"
                and _warning_band_declared(panel, value, covering)
            ):
                explained = "declared_warning_band"
            if explained is None:
                unexplained.append(
                    f"panel {panel['id']} ({panel.get('title', '')}) draws {kind}"
                    f"{'' if color is None else f'/{color}'} at {_num(value)} with no "
                    f"declaration; rules watching its series: "
                    f"{ {name: rec[1] for name, rec in covering.items()} }"
                )
            else:
                branches[explained] = branches.get(explained, 0) + 1
    assert not unexplained, "\n".join(unexplained)
    assert drawn >= 7, f"only {drawn} drawn figures found — the scan went blind"
    # every declared relation must earn its place, or it is a free pass
    assert set(branches) == {
        "rule_threshold",
        "first_painted_state",
        "liveness_state",
        "declared_warning_band",
    }, f"branch coverage collapsed: {branches}"
    assert painted_by == set(_FIRST_PAINTED_STATE), (
        f"entries never exercised: {set(_FIRST_PAINTED_STATE) - painted_by}"
    )


# ── case 2: every §14 figure a title names is in §14 ──


def _spec_targets() -> tuple[set[float], set[float], set[float]]:
    """(seconds, percent, plain counts) declared by PRODUCTION_SPEC §14."""
    text = _SPEC.read_text(encoding="utf-8")
    start = text.index("14. SLO 与生产质量")
    end = text.index("15. 产品界面", start)
    section = text[start:end]
    seconds: set[float] = set()
    percent: set[float] = set()
    counts: set[float] = set()
    for _op, value, unit in _title_figures(section):
        if unit in ("min", "分钟"):
            seconds.add(value * _MINUTES_TO_SECONDS)
        elif unit in ("s", "秒"):
            seconds.add(value)
        elif unit == "%":
            percent.add(value)
        else:
            counts.add(value)
    assert len(seconds) >= 6, f"§14 performance parse collapsed: {seconds}"
    assert len(percent) >= 3, f"§14 quality parse collapsed: {percent}"
    assert {480.0, 1500.0} <= seconds, (
        f"§14 must still declare the FAST/DEEP p95 targets the rules mirror: {seconds}"
    )
    return seconds, percent, counts


def test_every_panel_title_slo_figure_is_a_declared_target() -> None:
    seconds, percent, counts = _spec_targets()
    rules = _deployed_rules()
    offenders: list[str] = []
    checked = 0
    for panel in _panels():
        covering = _covering_rules(panel, rules)
        for _op, value, unit in _title_figures(str(panel.get("title", ""))):
            checked += 1
            if unit in ("min", "分钟"):
                ok = value * _MINUTES_TO_SECONDS in seconds
            elif unit in ("s", "秒"):
                ok = value in seconds
            elif unit == "%":
                ok = value in percent
            else:
                ok = value in counts or any(rec[1] == value for rec in covering.values())
            if not ok:
                offenders.append(
                    f"panel {panel['id']} titles figure '{_op or ''}{_num(value)}"
                    f"{unit or ''}' that is neither a §14 target "
                    f"(seconds={sorted(seconds)}, percent={sorted(percent)}, "
                    f"counts={sorted(counts)}) nor a deployed rule threshold "
                    f"({sorted(rec[1] for rec in covering.values())})"
                )
    assert not offenders, "\n".join(offenders)
    assert checked >= 10, f"only {checked} title figures found — the scan went blind"


# ── case 3: title figure, drawn figure and rule threshold are one number ──


def test_title_and_drawn_figures_agree_with_the_same_deployed_rule() -> None:
    rules = _deployed_rules()
    seconds, _percent, _counts = _spec_targets()
    disagreements: list[str] = []
    complement_used: set[str] = set()
    joined = 0
    for panel in _panels():
        covering = _covering_rules(panel, rules)
        figures = _title_figures(str(panel.get("title", "")))
        if not covering or not figures:
            continue
        joined += 1
        thresholds = [rec[1] for rec in covering.values()]
        for _op, value, unit in figures:
            if unit in ("min", "分钟", "s", "秒"):
                observed = value * _MINUTES_TO_SECONDS if unit in ("min", "分钟") else value
                assert observed in seconds, f"{_num(observed)}s is not a §14 target"
            elif unit == "%":
                observed = value / 100.0
            else:
                observed = value
            if observed in thresholds:
                continue
            matched = [
                name
                for name, rec in covering.items()
                if name in _COMPLEMENT_RULES
                and rec[0] in (">", ">=")
                and abs((1.0 - rec[1]) * 100.0 - value) < 1e-9
            ]
            if matched:
                complement_used.update(matched)
                continue
            disagreements.append(
                f"panel {panel['id']} ({panel.get('title', '')}) states "
                f"{_num(value)}{unit or ''} while the rules watching it compare "
                f"against {thresholds}"
            )
    assert not disagreements, "\n".join(disagreements)
    assert joined >= 4, f"only {joined} panels join a title to a rule — check the join"
    assert complement_used == set(_COMPLEMENT_RULES), (
        f"complement entries not exercised: {set(_COMPLEMENT_RULES) - complement_used}"
    )


# ── case 4: the liveness panel colours the value the down-rules call failure ──


def test_up_panel_colour_mappings_match_the_deployed_failure_value() -> None:
    rules = _deployed_rules()
    down = {
        name: rec for name, rec in rules.items() if "up" in rec[2] and rec[0] == "=="
    }
    assert len(down) >= 3, f"expected the scrape-target down rules, got {sorted(down)}"
    failure_values = {rec[1] for rec in down.values()}
    assert len(failure_values) == 1, f"down rules disagree on the failure value: {failure_values}"
    failure = next(iter(failure_values))

    up_panels = [
        panel
        for panel in _panels()
        if "up" in _series_names(_expr_text(panel)) and panel.get("type") != "row"
    ]
    assert len(up_panels) == 1, (
        f"expected exactly one panel over `up`, got {[p['id'] for p in up_panels]} — "
        "this gate colours one panel's mapping and cannot tell what a second one means"
    )
    mappings = up_panels[0].get("fieldConfig", {}).get("defaults", {}).get("mappings", [])
    assert len(mappings) == 1 and mappings[0].get("type") == "value", (
        f"liveness panel does not use a value mapping: {mappings}"
    )
    options = mappings[0]["options"]
    states = {str(key): (str(value.get("color")), str(value.get("text")))
              for key, value in options.items()}
    failure_text = states.get(_num(failure), ("", ""))
    healthy_text = states.get(_num(failure + 1), ("", ""))
    assert failure_text[0] == "red" and "DOWN" in failure_text[1].upper(), (
        f"the value the rules call failure ({_num(failure)}) is not painted down: {states}"
    )
    assert healthy_text[0] == "green" and "UP" in healthy_text[1].upper(), (
        f"the healthy value ({_num(failure + 1)}) is not painted up: {states}"
    )


# ── case 5: the one figure no rule declares must declare itself ──


def test_outbox_panel_declares_its_early_warning_band_below_the_alarm() -> None:
    rules = _deployed_rules()
    panel = next(p for p in _panels() if p["id"] == 14)
    covering = _covering_rules(panel, rules)
    assert covering, "the Outbox panel no longer shares a series with a deployed rule"
    alarm = min(rec[1] for rec in covering.values() if rec[0] in (">", ">="))
    steps = [
        (str(step.get("color")), float(step["value"]))
        for step in panel["fieldConfig"]["defaults"]["thresholds"]["steps"]
        if step.get("value") is not None
    ]
    assert [color for color, _value in steps].count("red") == 1, steps
    assert [color for color, _value in steps].count("yellow") == 1, steps
    red = next(value for color, value in steps if color == "red")
    yellow = next(value for color, value in steps if color == "yellow")
    assert red == alarm, (
        f"the Outbox panel paints red at {_num(red)}, the rule fires at {_num(alarm)}"
    )
    assert yellow < red, f"the early-warning band ({_num(yellow)}) sits at/above the alarm"
    assert yellow not in {rec[1] for rec in rules.values()}, (
        f"the band at {_num(yellow)} is a deployed threshold after all — the panel "
        "description's claim that no rule backs it is now false"
    )
    description = str(panel.get("description", ""))
    assert f"red={_num(alarm)}" in description and f"yellow={_num(yellow)}" in description, (
        f"the panel must state both bands where it draws them: {description}"
    )
    assert any(name in description for name in covering), (
        "the description must name the rule behind the red band"
    )
