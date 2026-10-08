"""#219: infra/prometheus/alerts-slo.yml keeps THREE copies of every SLO
threshold inside one file — the THRESHOLDS row in the header comment, the
literal in the rule's expr, and the (VAR=value) slot in the rule's summary —
and its own preamble claimed the opposite ("调整只需改对应规则的 expr/for
(单一修改点)"), which is false on its face: retuning a number here means
changing the table row, the expr and the annotation, plus the OBS §5 row
(#216) and the dashboard's drawn figures (#218). The false claim is corrected
in the same commit as the gate that makes it checkable.

Measured before writing (probe_219.py / probe219b/c/d):

- 12 header vars, 15 deployed rules. 3 rules are ``up{job=...} == 0``
  liveness rules carrying no threshold, so the remaining 12 must pair off
  with the 12 vars exactly. They did not: SpecproofVerifyDlqNonEmpty's
  summary said "(DLQ)" and named NO variable, while the OBS §5 row and the
  header table both already name VERIFY_DLQ_THRESHOLD=0 — the deployed rule
  was the odd copy out, carrying a threshold with no declared owner. Fixed.
- SpecproofNoEvidenceSevereComment spelled its slot "(阈值 VAR=0)" while the
  other eleven use "(VAR=0)": two shapes for one mechanism. Normalised.
- The header advertises two custom bucket ladders by range. Both ranges were
  correct against the code (webhook 0.05..2.5, progress-lag 0.05..5.0), but
  nothing read them: #215 binds those two ladders' constants to the alert
  thresholds, so retuning a ladder would have left the prose quoting a range
  the histogram no longer builds. Each quote is now bound to its declaring
  constant's first and last rung.
- The header's §14 citations come in three kinds and the distinction is
  load-bearing. JOB_P95_FAST_SECONDS=480 IS "p95 <= 8 分钟" converted; but
  API_5XX_RATE_THRESHOLD=0.05 is NOT 1-0.995 (that would be 0.005) and
  WORKER_FAIL_RATE_THRESHOLD=0.30 is not 1-0.90 nor 1-0.95 either — those two
  cite a §14 goal as a PRECONDITION, not as an identity. Calling every
  citation "derived from §14" would be a lie; calling every citation a
  precondition would be a free pass. The gate therefore computes the kind
  from the arithmetic and requires it to land on the declared set.

What is deliberately NOT in here: the histogram bucket ladders themselves
(#215 binds them to their declaring constants and to the alert thresholds),
the OBS §5 table (#216), and the Grafana dashboard (#218). This file only
reads alerts-slo.yml, §14, and the three constants its own prose cites
numbers from — including the two ladder ranges the header advertises
("亚秒桶梯度 0.05..2.5", "亚秒首格梯度 0.05..5"), which were true but bound to
nothing: #215 checks the constants against the thresholds, so a retuned
ladder top would have left this file's prose quoting a range the code no
longer builds. Chinese-numeral prose ("一轮", "两侧", "四词") is outside this
gate's alphabet — it accounts for ASCII digit runs, and says so rather than
pretending to read everything.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
YML = ROOT / "infra" / "prometheus" / "alerts-slo.yml"
SPEC = ROOT / "docs" / "PRODUCTION_SPEC.txt"

#: Rules that carry no threshold: liveness probes, asserted by name so a new
#: unattributed rule cannot hide in this exemption.
_LIVENESS_RULES = {
    "SpecproofApiDown",
    "SpecproofWorkerDown",
    "SpecproofOutboxRelayDown",
}

#: Rules whose expr fires on the FAILURE share: the declared SLO figure is the
#: complement of the threshold (1 - success rate).
_COMPLEMENT_RULES = {"SpecproofCapsuleReplayRateLow"}

#: The §14 text each header row cites. Each entry must occur (modulo spacing /
#: full-width punctuation / "s" vs "秒") inside ONE §14 line.
_SLO_CITATIONS: dict[str, tuple[str, ...]] = {
    "OUTBOX_PENDING_THRESHOLD": ("Job 不丢失: Outbox + MQ + 幂等",),
    "API_5XX_RATE_THRESHOLD": ("Control Plane 月可用性 99.5%",),
    "WORKER_FAIL_RATE_THRESHOLD": (
        "BLOCKER/MAJOR Precision >= 90%",
        "Capsule Replay >= 95%",
    ),
    "JOB_P95_FAST_SECONDS": ("FAST 小 PR p95 <= 8 分钟",),
    "JOB_P95_DEEP_SECONDS": ("DEEP 小 PR p95 <= 25 分钟",),
    "WEBHOOK_P95_SECONDS": ("GitHub Webhook 响应: p95 <= 1 秒",),
    "RECLAIM_TICK_STALE_SECONDS": ("Worker 崩溃后可恢复",),
    "DASHBOARD_PROGRESS_P95_SECONDS": ("Dashboard 进度延迟 <= 2s",),
    "VERIFY_QUEUE_BACKLOG_THRESHOLD": ("Job 不丢失",),
    "VERIFY_DLQ_THRESHOLD": ("Job 不丢失",),
    "NO_EVIDENCE_SEVERE_COMMENT_THRESHOLD": ("无证据严重评论 = 0",),
    "REPLAY_RATE_THRESHOLD": ("Capsule Replay >= 95%",),
}

#: Declared kinds of the citations above; the gate computes the kind from the
#: arithmetic and requires agreement in both directions.
_IDENTITY_CITATIONS = {
    "JOB_P95_FAST_SECONDS",
    "JOB_P95_DEEP_SECONDS",
    "WEBHOOK_P95_SECONDS",
    "DASHBOARD_PROGRESS_P95_SECONDS",
    "REPLAY_RATE_THRESHOLD",
    "NO_EVIDENCE_SEVERE_COMMENT_THRESHOLD",
}
_MOTIVATION_CITATIONS = {"API_5XX_RATE_THRESHOLD", "WORKER_FAIL_RATE_THRESHOLD"}
_GOAL_ONLY_CITATIONS = {
    "OUTBOX_PENDING_THRESHOLD",
    "RECLAIM_TICK_STALE_SECONDS",
    "VERIFY_QUEUE_BACKLOG_THRESHOLD",
    "VERIFY_DLQ_THRESHOLD",
}

#: How a cited figure's unit turns into the same scale as the threshold.
_UNIT_SECONDS = {"分钟": 60.0, "秒": 1.0, "s": 1.0}

#: The block's own prose restating its threshold (a third place the number
#: lives, inside the same comment row that documents it).
_PROSE_THRESHOLDS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("积压条数", re.compile(r"积压 (\d+) 条"), 1.0),
    ("5xx 占比", re.compile(r"占比 > (\d+(?:\.\d+)?)%"), 0.01),
    ("失败率", re.compile(r"失败率 > (\d+(?:\.\d+)?)%"), 0.01),
    ("ready 深度", re.compile(r"深度合计 > (\d+)"), 1.0),
    ("内联阈值", re.compile(r"> (\d+) for \d+[smh]"), 1.0),
    ("成功率", re.compile(r"成功率 < (\d+(?:\.\d+)?)%"), 0.01),
)

#: The block's own prose about clocks, and which rule field it must match.
_WINDOW_CLAIMS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("for 时长", re.compile(r"for (\d+[smh])"), "for"),
    ("分钟窗口", re.compile(r"(\d+) 分钟窗口"), "window-minutes"),
    ("窗口时长", re.compile(r"(\d+[smh]) 窗口"), "window"),
    ("持续时间", re.compile(r"持续 (\d+[smh])"), "for"),
)

_LADDER_CLAIM = re.compile(r"梯度 ([\d.]+)\.\.([\d.]+)")
#: Header rows that advertise a CUSTOM ladder quote it as a range, which is a
#: claim about the declaring constant's first and last rung — #215 binds those
#: ladders to the alert thresholds, but only this file reads the prose that
#: quotes them, so the quote binds to the declaration here.
_QUOTED_LADDERS: dict[str, tuple[str, str]] = {
    "WEBHOOK_P95_SECONDS": ("api.server", "_WEBHOOK_BUCKETS"),
    "DASHBOARD_PROGRESS_P95_SECONDS": ("api.routes.jobs", "_PROGRESS_LAG_BUCKETS"),
}
_DEFAULT_FIRST_RUNG = re.compile(r"默认梯度首格 (\d+(?:\.\d+)?)s")
_RESOLUTION_CLAIM = re.compile(r"对 ([\d.]+)s 分位数")
_BOUND_CLAIM = re.compile(r"([\d.]+)s 上界")
_TICK_CLAIM = re.compile(r"(\d+) 个默认周期 \((\d+)×(\d+)s\)")

_SLOT = re.compile(r"\(([A-Z][A-Z0-9_]{4,})=([0-9]+(?:\.[0-9]+)?)\)")
_BLOCK_START = re.compile(r"^#\s{2,}(?=[A-Z][A-Z0-9_]{4,}\s*=)", re.M)
_ROW = re.compile(r"^([A-Z][A-Z0-9_]{4,})\s*=\s*([0-9]+(?:\.[0-9]+)?)")
_COMPARISON = re.compile(r"(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+)?)")
_RATE_WINDOW = re.compile(r"\[(\d+)([smh])\]")
_QUANTILE = re.compile(r"histogram_quantile\(\s*([0-9.]+)")
_DIGIT_RUN = re.compile(r"\d+(?:\.\d+)?")
_CITED_FIGURE = re.compile(r"([0-9]+(?:\.[0-9]+)?) ?(%|分钟|秒|s)")


def _raw() -> str:
    return YML.read_text(encoding="utf-8")


def _blocks() -> tuple[str, dict[str, str]]:
    """(preamble, var -> its whole header row block) with a floored parse."""
    header = _raw().split("groups:", 1)[0]
    assert len(header) > 1000, f"header parse collapsed: {len(header)} chars"
    parts = _BLOCK_START.split(header)
    preamble, blocks = parts[0], {}
    for part in parts[1:]:
        row = _ROW.match(part)
        assert row is not None, f"block does not start with NAME = value: {part[:60]!r}"
        name = row.group(1)
        assert name not in blocks, f"duplicate THRESHOLDS row for {name}"
        blocks[name] = part
    assert len(blocks) >= 12, f"THRESHOLDS parse collapsed: {len(blocks)} rows"
    return preamble, blocks


def _values() -> dict[str, float]:
    out: dict[str, float] = {}
    for name, block in _blocks()[1].items():
        row = _ROW.match(block)
        assert row is not None, f"THRESHOLDS row for {name} has no `NAME = value` head"
        out[name] = float(row.group(2))
    assert len(out) >= 12, "no threshold values parsed"
    return out


def _prose(block: str) -> str:
    return "\n".join(
        line.lstrip("#").strip() for line in block.splitlines()[1:] if line.strip()
    )


def _rules() -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(_raw())
    out = {
        rule["alert"]: rule
        for group in data["groups"]
        for rule in group["rules"]
        if rule.get("alert")
    }
    assert len(out) >= 15, f"rule parse collapsed: {len(out)} rules"
    return out


def _annotation_text(rule: dict[str, Any]) -> str:
    return " ".join(str(v) for v in rule.get("annotations", {}).values())


def _expr(rule: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(rule["expr"])).strip()


def _owners() -> dict[str, str]:
    """var -> the single rule whose annotation names it.

    The floor is the pairing itself, asserted against the header table, so a
    lost (VAR=value) slot reddens every case that pairs through here with the
    message that NAMES the orphaned variable — a bare count floor would let
    the cases below the first red silently skip the var instead.
    """
    owners: dict[str, str] = {}
    for name, rule in _rules().items():
        for var, _value in _SLOT.findall(_annotation_text(rule)):
            assert var not in owners, f"{var} is claimed by both {owners[var]} and {name}"
            owners[var] = name
    values = _values()
    assert len(owners) >= 12, f"annotation-slot parse collapsed: {owners!r}"
    assert set(owners) == set(values), (
        f"THRESHOLDS rows vs annotated rules diverge: annotated only "
        f"{sorted(set(owners) - set(values))}, table only "
        f"{sorted(set(values) - set(owners))}"
    )
    return owners


def _section14() -> list[str]:
    spec = SPEC.read_text(encoding="utf-8")
    start, stop = spec.index("14. SLO"), spec.index("15. 产品界面")
    lines = [ln.strip() for ln in spec[start:stop].splitlines() if ln.strip()]
    assert len(lines) >= 10, f"§14 parse collapsed: {len(lines)} lines"
    return lines


def _normalise(text: str) -> str:
    out = text
    for src, dst in (("：", ":"), ("，", ","), ("（", "("), ("）", ")"), ("“", '"'), ("”", '"')):
        out = out.replace(src, dst)
    out = re.sub(r"([0-9])s\b", r"\1秒", out)
    return re.sub(r"""[\s,/:."'*|`_\-—]+""", "", out)


def _is_subsequence(needle: str, hay: str) -> bool:
    stream = iter(hay)
    return all(ch in stream for ch in needle)


def _citation_figures(citation: str) -> list[tuple[float, float]]:
    """(figure, threshold-scale value) for every unit-bearing figure cited."""
    out = [(float(num), float(num) * (0.01 if unit == "%" else _UNIT_SECONDS.get(unit, 1.0)))
           for num, unit in _CITED_FIGURE.findall(citation)]
    trailing = re.search(r"=\s*([0-9]+(?:\.[0-9]+)?)\s*$", citation)
    if trailing is not None and not out:
        out.append((float(trailing.group(1)), float(trailing.group(1))))
    return out


def test_threshold_table_and_rules_pair_off() -> None:
    """Every THRESHOLDS row is named by exactly one rule's annotation (the
    pairing itself is asserted in `_owners()`, so every case that pairs
    through it names an orphaned variable instead of skipping it), every
    thresholded rule names exactly one row, and the only rules naming nothing
    are the three declared liveness probes."""
    values = _values()
    rules = _rules()
    owners = _owners()
    thresholded = set(rules) - _LIVENESS_RULES
    assert len(thresholded) == len(values), (
        f"{len(thresholded)} thresholded rules but {len(values)} THRESHOLDS rows"
    )
    unattributed = {
        name
        for name, rule in rules.items()
        if not _SLOT.findall(_annotation_text(rule))
    }
    assert unattributed == _LIVENESS_RULES, (
        f"rules carrying no (VAR=value) slot must be exactly the declared "
        f"liveness probes: {sorted(unattributed ^ _LIVENESS_RULES)}"
    )
    for name in _LIVENESS_RULES:
        assert re.fullmatch(r'up\{job="[^"]+"\} == 0', _expr(rules[name])), (
            f"{name} is exempted as a liveness probe but its expr is not "
            f"`up{{job=...}} == 0`: {_expr(rules[name])}"
        )
    for var, rule_name in owners.items():
        assert rule_name in thresholded, f"{var} is named by the liveness rule {rule_name}"


def test_the_three_copies_of_a_threshold_agree() -> None:
    """header row == annotation slot == expr literal, for every rule."""
    values, owners, rules = _values(), _owners(), _rules()
    direct = 0
    for var, rule_name in owners.items():
        rule = rules[rule_name]
        slot = _SLOT.findall(_annotation_text(rule))
        assert len(slot) == 1, f"{rule_name} must carry exactly one slot, got {slot}"
        assert float(slot[0][1]) == values[var], (
            f"{var}: the header row says {values[var]} but {rule_name}'s "
            f"annotation says {slot[0][1]}"
        )
        numbers = [float(num) for _op, num in _COMPARISON.findall(_expr(rule))]
        assert numbers, f"{rule_name}'s expr carries no compared threshold"
        if values[var] in numbers:
            direct += 1
            continue
        flipped = round(1.0 - values[var], 10)
        assert flipped in numbers, (
            f"{var}: the header says {values[var]}, {rule_name}'s expr fires "
            f"at {numbers} — neither the value nor its complement"
        )
    assert direct >= 11, f"only {direct} rules fire at their declared figure"


def test_complement_declaration_is_exercised() -> None:
    """Which rules fire on the COMPLEMENT of their declared figure is derived
    from the deployed arithmetic, not trusted from this file's docstring.

    The derivation is positive — `1 - value` occurs in the expr — because the
    first draft asked the negative question ("the value is absent from the
    expr"), which is a disagreement detector wearing a complement label: arms
    A1/A2/A8 each moved one copy of an unrelated threshold and every moved var
    piled up here instead of in `test_the_three_copies_of_a_threshold_agree`.
    """
    owners, values, rules = _owners(), _values(), _rules()
    compared = {
        var: [float(n) for _op, n in _COMPARISON.findall(_expr(rules[owners[var]]))]
        for var in owners
    }
    derived = {
        owners[var] for var in owners if round(1.0 - values[var], 10) in compared[var]
    }
    assert derived == _COMPLEMENT_RULES, (
        f"rules firing on the complement of their declared figure: "
        f"{sorted(derived)} but the file declares {sorted(_COMPLEMENT_RULES)}"
    )
    for name in _COMPLEMENT_RULES:
        var = next(var for var, rule_name in owners.items() if rule_name == name)
        rate = values[var]
        assert round(1.0 - rate, 10) in compared[var], (
            f"{name} is declared a complement but does not fire at 1 - {rate}: "
            f"{compared[var]}"
        )
        assert rate not in compared[var], (
            f"{name} fires at its own figure {rate}, so it is a direct copy, "
            "not a complement"
        )


def test_header_citations_quote_a_real_section_14_line() -> None:
    """Each THRESHOLDS row's §14 citation must be findable inside ONE §14
    line — the header may not paraphrase a target that the spec never sets."""
    declared = set(_SLO_CITATIONS)
    values = _values()
    assert declared == set(values), (
        f"citation table vs THRESHOLDS rows diverge: {sorted(declared ^ set(values))}"
    )
    _preamble, blocks = _blocks()
    slo_lines = [_normalise(ln) for ln in _section14() if ln.startswith("- ")]
    assert len(slo_lines) >= 8, f"§14 bullet parse collapsed: {len(slo_lines)} lines"
    for var, citations in _SLO_CITATIONS.items():
        for citation in citations:
            assert citation in blocks[var], (
                f"{var}: the header row no longer carries {citation!r} "
                "verbatim — this gate's quotation table has drifted from the "
                "file it audits, so the §14 check below grades a copy"
            )
            needle = _normalise(citation)
            assert any(_is_subsequence(needle, line) for line in slo_lines), (
                f"{var} cites {citation!r} — no single §14 line contains it"
            )


def test_citation_kinds_land_where_declared() -> None:
    """identity / precondition / goal-only is computed from the arithmetic and
    must agree with the declaration in both directions."""
    computed_identity: set[str] = set()
    computed_motivation: set[str] = set()
    computed_goal_only: set[str] = set()
    values = _values()
    for var, citations in _SLO_CITATIONS.items():
        figures = [pair for citation in citations for pair in _citation_figures(citation)]
        if not figures:
            computed_goal_only.add(var)
            continue
        if any(abs(value - values[var]) < 1e-9 for _fig, value in figures):
            computed_identity.add(var)
        else:
            computed_motivation.add(var)
    assert computed_identity == _IDENTITY_CITATIONS, (
        f"citations that do arithmetically equal their threshold: "
        f"{sorted(computed_identity)} vs declared {sorted(_IDENTITY_CITATIONS)}"
    )
    assert computed_motivation == _MOTIVATION_CITATIONS, (
        f"citations that name a §14 goal without equaling it: "
        f"{sorted(computed_motivation)} vs declared {sorted(_MOTIVATION_CITATIONS)}"
    )
    assert computed_goal_only == _GOAL_ONLY_CITATIONS, (
        f"citations carrying no figure: {sorted(computed_goal_only)} vs "
        f"declared {sorted(_GOAL_ONLY_CITATIONS)}"
    )
    # The precondition declaration must stay a precondition: if someone
    # "derives" 0.05 from 99.5% availability, that is a different number and
    # the file would start lying about §14.
    assert abs((1.0 - 0.995) - values["API_5XX_RATE_THRESHOLD"]) > 1e-9, (
        "API_5XX_RATE_THRESHOLD is declared as a precondition of 99.5% "
        "availability, not as 1 - 0.995"
    )
    assert all(
        abs((1.0 - goal / 100) - values["WORKER_FAIL_RATE_THRESHOLD"]) > 1e-9
        for goal in (90.0, 95.0)
    ), "WORKER_FAIL_RATE_THRESHOLD is a precondition, not a complement of §14"
    assert len(_IDENTITY_CITATIONS) >= 6 and len(_MOTIVATION_CITATIONS) >= 2


def test_prose_restates_its_own_threshold() -> None:
    """The comment row that documents a threshold also states it in prose
    ("积压 50 条", "占比 > 5%", "成功率 < 95%"); that fourth mention must agree
    with the row, the annotation and the expr."""
    values, owners = _values(), _owners()
    blocks = _blocks()[1]
    claimed: dict[str, list[str]] = {}
    for var, block in blocks.items():
        prose = _prose(block)
        hits: list[str] = []
        for label, pattern, scale in _PROSE_THRESHOLDS:
            for found in pattern.findall(prose):
                assert abs(float(found) * scale - values[var]) < 1e-9, (
                    f"{var}: its row's prose {label} says {found} but the "
                    f"threshold is {values[var]}"
                )
                hits.append(label)
        if hits:
            claimed[var] = hits
    assert len(claimed) >= 7, f"prose-threshold scan found only {sorted(claimed)}"
    for var in claimed:
        assert var in owners, f"{var} states a prose threshold but no rule names it"


def _clock_seconds(token: str) -> float:
    """A `5m` / `10s` / `1h` clock literal in seconds."""
    unit = re.fullmatch(r"(\d+)([smh])", token)
    assert unit is not None, f"not a clock literal: {token!r}"
    return float(unit.group(1)) * {"s": 1.0, "m": 60.0, "h": 3600.0}[unit.group(2)]


def test_prose_clocks_match_the_deployed_timers() -> None:
    """`for 5m` / `15 分钟窗口` / `持续 10m` in a THRESHOLDS row are claims
    about that rule's own `for:` and rate-window selectors."""
    owners, blocks, rules = _owners(), _blocks()[1], _rules()
    claims = 0
    for var, block in blocks.items():
        prose = _prose(block)
        assert var in owners, f"{var} claims clocks but no rule names it: {sorted(owners)}"
        rule = rules[owners[var]]
        windows = [
            _clock_seconds(f"{num}{unit}")
            for num, unit in _RATE_WINDOW.findall(_expr(rule))
        ]
        for label, pattern, field in _WINDOW_CLAIMS:
            for token in pattern.findall(prose):
                claims += 1
                if field == "for":
                    assert token == str(rule.get("for")), (
                        f"{var}: the row says {label} {token} but the "
                        f"deployed rule waits for {rule.get('for')}"
                    )
                    continue
                want = _clock_seconds(token) if field == "window" else float(token) * 60.0
                assert windows, (
                    f"{var}: the row claims a {token} reading window but "
                    f"{owners[var]}'s expr selects over none"
                )
                assert all(want == w for w in windows), (
                    f"{var}: the row says {label} {token} but the expr "
                    f"reads over {windows}s"
                )
    assert claims >= 7, f"clock-claim scan found only {claims}"


def test_ladder_and_tick_prose_claims_are_arithmetic() -> None:
    """The header quotes bucket ladders and tick periods; those figures must
    bracket the threshold they are offered as evidence for, and the quoted
    default rung / tick period must equal the constant in the code."""
    from observability.metrics import _HISTOGRAM_BUCKETS

    values, blocks = _values(), _blocks()[1]
    ladders = ticks = bound = 0
    for var, block in blocks.items():
        prose = _prose(block)
        for low, high in _LADDER_CLAIM.findall(prose):
            assert float(low) <= values[var] <= float(high), (
                f"{var}: the row advertises a {low}..{high} ladder but the "
                f"threshold {values[var]} sits outside it — a breach would "
                f"not be resolvable in that ladder"
            )
            ladders += 1
            owner = _QUOTED_LADDERS.get(var)
            assert owner is not None, (
                f"{var}: quotes a {low}..{high} ladder that this gate does "
                f"not bind to a declaring constant"
            )
            module_name, attribute = owner
            declared = getattr(importlib.import_module(module_name), attribute)
            assert (float(declared[0]), float(declared[-1])) == (float(low), float(high)), (
                f"{var}: the row quotes a {low}..{high} ladder but "
                f"{module_name}.{attribute} runs {declared[0]}..{declared[-1]}"
            )
            bound += 1
        for claim in (_RESOLUTION_CLAIM, _BOUND_CLAIM):
            for found in claim.findall(prose):
                assert float(found) == values[var], (
                    f"{var}: the row reasons about a {found}s quantile while "
                    f"the threshold is {values[var]}"
                )
        for first in _DEFAULT_FIRST_RUNG.findall(prose):
            assert float(first) == _HISTOGRAM_BUCKETS[0], (
                f"{var}: the row says the default ladder starts at {first}s "
                f"but it starts at {_HISTOGRAM_BUCKETS[0]}s"
            )
        tick = _TICK_CLAIM.search(prose)
        if tick is not None:
            from agent.worker import DEFAULT_RECLAIM_INTERVAL_SECONDS

            count, multiple, period = tick.group(1), tick.group(2), tick.group(3)
            ticks += 1
            assert int(multiple) * int(period) == values[var], (
                f"{var}: the row claims {multiple}×{period}s = the threshold "
                f"but it is {values[var]}"
            )
            assert int(count) == int(multiple), (
                f"{var}: the row says {count} periods then multiplies by {multiple}"
            )
            assert int(period) == int(DEFAULT_RECLAIM_INTERVAL_SECONDS), (
                f"{var}: the row's period {period}s is no longer the tick "
                f"interval {DEFAULT_RECLAIM_INTERVAL_SECONDS}s"
            )
    assert ladders >= 2 and bound == ladders, (
        f"ladder claims {ladders}, bound to a declaration {bound}"
    )
    assert ticks == 1, f"tick claims {ticks}"


def test_p95_in_the_name_binds_histogram_quantile_in_the_expr() -> None:
    """A row named *_P95_* promises a p95 alert; the rule that carries it must
    actually compute the 0.95 quantile, and no unnamed rule may sneak one in."""
    owners, blocks, rules = _owners(), _blocks()[1], _rules()
    named = {var for var in blocks if "_P95_" in var or var.endswith("P95_SECONDS")}
    quoted_p95 = {var for var, block in blocks.items() if re.search(r"[Pp]95", block)}
    assert named == quoted_p95, (
        f"every row quoting p95 must be a *_P95_* row (and vice versa): "
        f"{sorted(named ^ quoted_p95)}"
    )
    quantile_rules = {
        name
        for name, rule in rules.items()
        if _QUANTILE.search(_expr(rule)) is not None
    }
    assert quantile_rules == {owners[var] for var in named}, (
        f"rules computing a quantile: {sorted(quantile_rules)} vs the p95 "
        f"rows' rules {sorted(owners[var] for var in named)}"
    )
    for var in named:
        expr = _expr(rules[owners[var]])
        assert _QUANTILE.findall(expr) == ["0.95"], (
            f"{var} promises a p95 alert but {owners[var]} computes "
            f"{_QUANTILE.findall(expr)}"
        )
    assert len(named) >= 4, f"p95 rows collapsed: {sorted(named)}"


def test_metric_class_tokens_name_a_real_series() -> None:
    """The header prose says "5xx 占比"; the rule it documents must read a
    series carrying that class, so the words describe the query."""
    blocks, owners, rules = _blocks()[1], _owners(), _rules()
    hits = 0
    for var, block in blocks.items():
        prose = _prose(block)
        for token in set(re.findall(r"(\d+xx)", prose)):
            expr = _expr(rules[owners[var]])
            assert token in expr, (
                f"{var}: the row talks about {token} but the expr reads {expr}"
            )
            hits += 1
    assert hits >= 1, f"metric-class token scan found nothing: {hits}"


def test_the_dlq_queue_pattern_cites_its_defining_constant() -> None:
    """The DLQ rule matches queues by suffix; its description names the
    artifact that defines that suffix, so a suffix change cannot leave the
    alert pointing at queues that never exist."""
    from storage.rabbitmq import QueuePolicy

    description = str(_rules()["SpecproofVerifyDlqNonEmpty"]["annotations"]["description"])
    cited = re.search(r"dlq_suffix='([^']+)'", description)
    assert cited is not None, (
        f"the DLQ description no longer names the defining suffix constant: {description[:120]}"
    )
    assert cited.group(1) == QueuePolicy().dlq_suffix, (
        f"the alert cites suffix {cited.group(1)!r} but QueuePolicy uses "
        f"{QueuePolicy().dlq_suffix!r}"
    )
    assert cited.group(1) in _expr(_rules()["SpecproofVerifyDlqNonEmpty"]), (
        "the rule's own queue regex must carry the cited suffix"
    )


def test_every_number_in_the_header_is_claimed_by_a_relation() -> None:
    """The accounting case: no digit run may sit in the THRESHOLDS header
    without being a figure one of the cases above checks — a §-marker or an
    issue reference excepted, since those cite history rather than a number.
    A collapsed family would leave runs unclaimed, so this case reddens when
    one of the scans above stops matching what it says it matches."""
    preamble, blocks = _blocks()
    checked: list[re.Pattern[str]] = [
        re.compile(r"^[A-Z][A-Z0-9_]{4,}\s*=\s*[0-9.]+", re.M),
        *[pattern for _label, pattern, _scale in _PROSE_THRESHOLDS],
        *[pattern for _label, pattern, _field in _WINDOW_CLAIMS],
        _LADDER_CLAIM,
        _DEFAULT_FIRST_RUNG,
        _RESOLUTION_CLAIM,
        _BOUND_CLAIM,
        _TICK_CLAIM,
        re.compile(r"[Pp]95|[Pp]50"),
        re.compile(r"\d+xx"),
    ]
    exempt = [re.compile(r"§[0-9]+"), re.compile(r"#[0-9]+")]
    unclaimed: list[str] = []
    checked_runs = markers = 0
    for var, text in {"<preamble>": preamble, **blocks}.items():
        checked_spans = [
            (m.start(), m.end()) for pattern in checked for m in pattern.finditer(text)
        ]
        for citation in _SLO_CITATIONS.get(var, ()):
            start = text.find(citation)
            assert start >= 0, f"{var} declares the citation {citation!r}, its row lacks it"
            checked_spans.append((start, start + len(citation)))
        exempt_spans = [(m.start(), m.end()) for pattern in exempt for m in pattern.finditer(text)]
        markers += len(exempt_spans)
        for run in _DIGIT_RUN.finditer(text):
            in_checked = any(lo <= run.start() < hi for lo, hi in checked_spans)
            in_exempt = any(lo <= run.start() < hi for lo, hi in exempt_spans)
            checked_runs += int(in_checked)
            if not (in_checked or in_exempt):
                context = text[max(0, run.start() - 40):run.end() + 24].replace("\n", " ")
                unclaimed.append(f"{var}: {run.group(0)} in …{context}…")
    assert not unclaimed, "unexplained numbers in the header:\n" + "\n".join(unclaimed)
    assert checked_runs >= 40, f"only {checked_runs} header numbers bound by a relation"
    assert markers >= 20, f"citation markers collapsed: {markers}"
