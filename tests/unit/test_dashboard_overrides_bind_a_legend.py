"""#672 — every ``byName`` override must name a legend its own panel renders.

A Grafana ``byName`` override matches a field by its DISPLAY NAME, which for a
timeseries target is the interpolated ``legendFormat``. An override that names
no legend the panel renders styles nothing — the unit/axis settings it carries
are silently dropped — and the shape is easy to produce: rename a legend and
the override beside it keeps the old name, no error anywhere.

The dashboard ships one such override today (the outbox age's seconds axis).
``tests/unit/test_outbox_relay_loop_leg.py`` L18 pins that instance by reading
the panel and matching the two strings; it pins the PANEL, not the invariant,
so a new ``byName`` override on any other panel is invisible to it. This gate
reads every dashboard JSON under ``infra/grafana/dashboards/`` and joins each
override to the legends of its own panel.

Measured 2026-11-06 (``.scratch/m672_probe.py``, output
``D:/面试项目/_p548/ledger_repair/probe_672.txt``): 1 dashboard, 51 panels
(3 rows + 48 data panels), 151 legendFormats of which 14 are templated
(``{{job}}`` …), 1 ``byName`` override and it matches a literal legend.

Grafana writes an override in two spellings — the older
``{"id": "byName", "options": ...}`` and the newer
``{"matcher": {"id": "byName", "options": ...}}``. The shipped file uses the
older one; the extractor reads both, and a witness below runs it on synthetic
panels of each spelling so a narrower extractor cannot pass on this file alone.

Honest boundaries. (1) Only ``byName`` is judged; ``byRegexp`` and
``byFrameRefID`` overrides select fields by rules this gate does not evaluate.
(2) A literal legend is compared as text: a byName override whose options equal
a literal legendFormat is accepted, whatever Grafana's own interpolation would
do with it. (3) A templated legend cannot be checked at all — the rendered name
depends on label values at scrape time — so naming one (by its raw ``{{…}}``
text, which can never be a rendered name) is refused, and a byName override on
a panel whose targets carry no legendFormat is refused too: the gate will not
certify a name it cannot derive. (4) This gate reads the worktree copy of the
dashboard, the same basis as the other dashboard gates (#218, #220).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARDS = ROOT / "infra" / "grafana" / "dashboards"

#: Floors, set below the measurement above so they do not rot with the
#: dashboard, but high enough that a collapsed reading cannot pass as "clean".
MIN_DASHBOARDS = 1
MIN_PANELS = 40
MIN_LEGENDS = 100
MIN_BY_NAME = 1


def _panels(node: object) -> list[dict]:
    """Every panel dict, including panels nested inside rows."""
    found: list[dict] = []
    if isinstance(node, dict):
        children = node.get("panels")
        if isinstance(children, list):
            for panel in children:
                if isinstance(panel, dict):
                    found.append(panel)
                    found.extend(_panels(panel))
        for key, value in node.items():
            if key != "panels":
                found.extend(_panels(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_panels(value))
    return found


def _legends(panel: dict) -> list[str]:
    return [
        str(target["legendFormat"])
        for target in panel.get("targets") or []
        if target.get("legendFormat")
    ]


def _overrides(panel: dict) -> list[tuple[str, str, object]]:
    """``(spelling, matcher kind, options)`` for every override on the panel."""
    rows: list[tuple[str, str, object]] = []
    overrides = (panel.get("fieldConfig") or {}).get("overrides") or []
    for override in overrides:
        if "matcher" in override:
            matcher = override.get("matcher") or {}
            rows.append(("matcher", str(matcher.get("id")), matcher.get("options")))
        else:
            rows.append(("flat", str(override.get("id")), override.get("options")))
    return rows


@dataclass(frozen=True)
class Drawn:
    """One byName override and the legends its own panel actually renders."""

    dashboard: str
    panel: str
    spelling: str
    options: str
    literals: tuple[str, ...]
    templated: tuple[str, ...]


@dataclass(frozen=True)
class Census:
    dashboards: tuple[str, ...]
    panels: int
    legends: int
    drawn: tuple[Drawn, ...]


def _scan(directory: Path = DASHBOARDS) -> Census:
    names = tuple(sorted(p.name for p in directory.glob("*.json")))
    panels = 0
    legends = 0
    drawn: list[Drawn] = []
    for name in names:
        data = json.loads((directory / name).read_text(encoding="utf-8"))
        for panel in _panels(data):
            panels += 1
            own = _legends(panel)
            legends += len(own)
            literal = tuple(legend for legend in own if "{{" not in legend)
            templated = tuple(legend for legend in own if "{{" in legend)
            for spelling, kind, options in _overrides(panel):
                if kind == "byName":
                    drawn.append(
                        Drawn(
                            dashboard=name,
                            panel=str(panel.get("title")),
                            spelling=spelling,
                            options=str(options),
                            literals=literal,
                            templated=templated,
                        )
                    )
    return Census(names, panels, legends, tuple(drawn))


def _refusal(drawn: Drawn) -> str | None:
    """Why this override styles nothing this gate can verify, or ``None``."""
    if drawn.options in drawn.literals:
        return None
    if "{{" in drawn.options:
        return (
            "names a templated legend by its unexpanded text — the matcher sees "
            "the rendered name, never the {{…}} template"
        )
    return "names no legend this panel renders"


def test_the_census_is_populated_and_valid_json() -> None:
    """L1 — a renamed or emptied dashboard directory must refuse, not read clean."""
    census = _scan()
    assert len(census.dashboards) >= MIN_DASHBOARDS, (
        f"no dashboard JSON found under {DASHBOARDS} — a moved or renamed "
        "dashboard would otherwise make this gate green by having nothing to read"
    )
    assert census.panels >= MIN_PANELS, (
        f"only {census.panels} panels across {census.dashboards} (floor {MIN_PANELS})"
    )
    assert census.legends >= MIN_LEGENDS, (
        f"only {census.legends} legendFormats across the dashboard population "
        f"(floor {MIN_LEGENDS}) — the join below needs legends to join against"
    )
    assert len(census.drawn) >= MIN_BY_NAME, (
        f"no byName override found (floor {MIN_BY_NAME}); the one this gate was "
        "written for is gone or its spelling changed"
    )


def test_every_by_name_override_names_a_legend_in_its_own_panel() -> None:
    """L2 — the judgment: a byName override must match a literal legend beside it.

    Each refusal names the dashboard, the panel, the options text and the
    legends the panel does render, so the reader can tell a renamed legend from
    an override that never had a target.
    """
    census = _scan()
    charged = [
        f"{drawn.dashboard} / {drawn.panel!r} ({drawn.spelling}): {drawn.options!r} "
        f"{_refusal(drawn)}; legends here: {list(drawn.literals) + list(drawn.templated)}"
        for drawn in census.drawn
        if _refusal(drawn)
    ]
    assert not charged, "byName overrides styling no verifiable series:\n  " + "\n  ".join(charged)


def test_the_extractor_reads_both_grafana_spellings() -> None:
    """L2w — the extractor is witnessed on both spellings, one of which the real file lacks.

    The shipped dashboard writes the older flat shape only. Without this leg the
    ``matcher`` branch would be dead code nothing exercises, and Grafana's newer
    export could be silently invisible.
    """
    panel = {
        "title": "synthetic",
        "targets": [{"legendFormat": "one"}],
        "fieldConfig": {
            "overrides": [
                {"id": "byName", "options": "one", "properties": []},
                {"matcher": {"id": "byName", "options": "two"}, "properties": []},
            ]
        },
    }
    assert _overrides(panel) == [
        ("flat", "byName", "one"),
        ("matcher", "byName", "two"),
    ]


def test_a_templated_name_is_refused_and_a_literal_one_is_not() -> None:
    """L2w — the templated clause fires on a plane that needs it.

    Measured 2026-11-06 the dashboard carries 14 templated legends; none of them
    is named by an override today, so refusing the raw template text is a
    judgment the shipped bytes never exercise. Run it here: the same override
    text is refused against the template and accepted once the legend is the
    literal it claims to be.
    """
    templated = Drawn("synthetic.json", "synthetic", "flat", "{{job}}", (), ("{{job}}",))
    literal = Drawn("synthetic.json", "synthetic", "flat", "{{job}}", ("{{job}}",), ())
    assert _refusal(templated) is not None
    assert "unexpanded" in _refusal(templated)
    assert _refusal(literal) is None, "a literal legend is the one thing this gate can judge"
