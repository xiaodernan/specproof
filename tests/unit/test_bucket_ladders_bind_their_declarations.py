"""#215 ladder census: every remaining histogram-ladder claim that names a
number is bound to its DECLARING artifact — the deployed alert thresholds in
infra/prometheus/alerts-slo.yml (parsed as YAML) or the same module's
constants — instead of a hand-typed copy.

The #213/#214 arc bound three ladders to their producer declarations by AST
(ES vs request_timeout, redis vs socket_timeout, tool vs the Param cap).
This file completes the census for the families whose claims name a
threshold:

- stage ladder top vs the DEEP p95 alert threshold (#167's claim "stays
  above the DEEP job-level p95 target (1500s)");
- webhook ladder top vs its 1s p95 alert threshold (#162);
- progress-lag ladder: the 2s SLO bound is an exact rung AND a boundary
  above it exists (#164's "the 2s SLO bound sits inside the ladder, so a
  p95 breach is resolvable");
- the default job-duration ladder carries the p95 alert thresholds as rungs
  (metrics.py's "对齐 §14 性能目标" must move together with the alert file);
- the recovery clocks vs the same module's constants (#163): the tick
  interval is a rung of the recovery-lag ladder, and the sweep lock
  outlives a pass at the pass-ladder top.

The LLM ladder's strict-clear clause lives with its family test
(test_provider_request_metrics_are_observable.py, repaired to strict `>` in
#215 — a call cut off AT the deadline measures slightly over it).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _alert_thresholds() -> dict[str, float]:
    """Every `> N` threshold in the deployed alert rules, keyed by alert.

    The parse is floored: an empty or all-unmatched walk raises instead of
    silently testing a smaller population (a regex that matches nothing
    must never pass an absence claim).
    """
    data = yaml.safe_load(
        (ROOT / "infra" / "prometheus" / "alerts-slo.yml").read_text(
            encoding="utf-8"
        )
    )
    out: dict[str, float] = {}
    for group in data["groups"]:
        for rule in group["rules"]:
            alert = rule.get("alert")
            match = re.search(r">\s*([0-9]+(?:\.[0-9]+)?)", str(rule.get("expr", "")))
            if alert and match:
                out[alert] = float(match.group(1))
    assert len(out) >= 5, f"alert-threshold parse found only {out!r} — shape changed"
    return out


def test_stage_ladder_clears_the_deep_p95_alert_threshold() -> None:
    """#167's claim must hold against the DEPLOYED threshold — the alert
    expr in alerts-slo.yml — not against a comment or a copied number.
    Retuning the alert without the ladder (or vice versa) reddens here."""
    from agent.worker import _STAGE_BUCKETS
    from observability.metrics import _HISTOGRAM_BUCKETS

    target = _alert_thresholds()["SpecproofJobDurationP95DeepHigh"]
    assert _STAGE_BUCKETS[0] < _HISTOGRAM_BUCKETS[0], (
        "the stage ladder must be custom, not the 60s-first default"
    )
    assert _STAGE_BUCKETS[-1] > target, (
        f"stage ladder top {_STAGE_BUCKETS[-1]}s must clear the DEEP p95 "
        f"alert threshold {target}s — a stage quantile at the threshold "
        f"would fall into +Inf"
    )


def test_webhook_ladder_clears_its_p95_alert_threshold() -> None:
    """#162: the webhook histogram is read against a 1s p95 alert; the
    custom sub-second ladder's top must clear that DEPLOYED threshold."""
    from api.server import _WEBHOOK_BUCKETS
    from observability.metrics import _HISTOGRAM_BUCKETS

    target = _alert_thresholds()["SpecproofWebhookDurationP95High"]
    assert _WEBHOOK_BUCKETS[0] < _HISTOGRAM_BUCKETS[0], (
        "the webhook ladder must be custom, not the 60s-first default"
    )
    assert _WEBHOOK_BUCKETS[-1] > target, (
        f"webhook ladder top {_WEBHOOK_BUCKETS[-1]}s must clear its p95 "
        f"alert threshold {target}s — a breach at the threshold must stay "
        f"resolvable"
    )


def test_progress_lag_ladder_contains_the_slo_bound() -> None:
    """#164: "The 2s SLO bound sits inside the ladder" — the bound must be
    an actual rung (exact le=2 readout against the deployed threshold), and
    a boundary above it must exist so a p95 breach stays resolvable."""
    from api.routes.jobs import _PROGRESS_LAG_BUCKETS
    from observability.metrics import _HISTOGRAM_BUCKETS

    target = _alert_thresholds()["SpecproofDashboardProgressLagHigh"]
    assert _PROGRESS_LAG_BUCKETS[0] < _HISTOGRAM_BUCKETS[0], (
        "the progress-lag ladder must be custom, not the 60s-first default"
    )
    assert target in _PROGRESS_LAG_BUCKETS, (
        f"the SLO bound {target}s must be a rung of "
        f"{_PROGRESS_LAG_BUCKETS} for an exact readout"
    )
    assert _PROGRESS_LAG_BUCKETS[-1] > target, (
        f"a boundary above {target}s must exist — a breach must not "
        f"collapse into +Inf"
    )


def test_default_ladder_carries_the_p95_alert_thresholds_as_rungs() -> None:
    """metrics.py says the default ladder is aligned with the §14 targets
    and the job-duration alerts fire ON those numbers; the thresholds read
    from the deployed alert file must be rungs of the default ladder, so
    retuning one artifact without the other reddens."""
    from observability.metrics import _HISTOGRAM_BUCKETS

    thresholds = _alert_thresholds()
    rungs = set(_HISTOGRAM_BUCKETS)
    for alert in (
        "SpecproofJobDurationP95FastHigh",
        "SpecproofJobDurationP95DeepHigh",
    ):
        assert thresholds[alert] in rungs, (
            f"{alert} fires at {thresholds[alert]}s but that number is not "
            f"a rung of the default ladder {sorted(rungs)}"
        )


def test_recovery_clocks_bind_the_tick_and_lock_constants() -> None:
    """#163: the recovery-lag ladder is "按 tick 周期 300s 定" and the sweep
    lock "outlives a healthy pass but not the next interval" — both
    relations against the SAME module's constants, so retuning the tick or
    the TTL pulls the ladder gates with it."""
    from agent.worker import (
        _RECLAIM_PASS_BUCKETS,
        _RECOVERY_LAG_BUCKETS,
        DEFAULT_RECLAIM_INTERVAL_SECONDS,
        RECLAIM_LOCK_TTL_SECONDS,
    )

    interval = float(DEFAULT_RECLAIM_INTERVAL_SECONDS)
    assert interval in _RECOVERY_LAG_BUCKETS, (
        f"the tick interval {interval}s must be a rung — the death-to-reclaim "
        f"wait is read against the tick scale"
    )
    assert _RECOVERY_LAG_BUCKETS[-1] > interval, (
        f"recovery-lag top {_RECOVERY_LAG_BUCKETS[-1]}s must clear one tick "
        f"({interval}s)"
    )
    assert _RECLAIM_PASS_BUCKETS[-1] < RECLAIM_LOCK_TTL_SECONDS, (
        f"a pass at the pass-ladder top {_RECLAIM_PASS_BUCKETS[-1]}s must "
        f"still finish inside the sweep lock TTL {RECLAIM_LOCK_TTL_SECONDS}s"
    )
