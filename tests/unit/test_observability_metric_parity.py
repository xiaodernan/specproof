"""Parity gate: every metric name referenced by alerts/dashboards must trace
to a real emission site (#161).

This project's metrics registry has NO static table — a name appears on
/metrics only after its first emission (docs/operations/OBSERVABILITY.md,
section "已接线指标名", documents the reproducible reconciliation method:
take the incr/set_gauge/observe_duration call sites and resolve constants to
literals). That made stale references invisible: the duration alert kept
querying ``specproof_jobs_duration_seconds_bucket`` after #161 split the
histogram into a ``_fast/_deep`` family, and prometheus.yml's comment claimed
the outbox-relay service "尚未进入 compose.production.yml" long after it did.

This test turns that class of drift red: every ``specproof_*`` name referenced
by alerts-slo.yml, prometheus.yml or the Grafana SLO dashboard must either be
emitted by a scanned call site or match one of the hand-registered
concatenated families (names the code builds at runtime — those cannot be
listed exhaustively, only pattern-matched).

Scope note: the source scan covers the four trees that own emission sites
(agent/, api/, storage/, observability/). Emissions elsewhere would still
work at runtime; they are simply not part of this gate's inventory until they
appear here — which is the same honesty rule OBSERVABILITY.md applies.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

#: Trees scanned for emission sites (mirrors OBSERVABILITY.md's method note).
#: providers/ joined in #168: the LLM token/charge meters live in
#: providers/budget.py (TokenBudget.record), the same choke point the
#: billing listener reads.
EMIT_DIRS = ("agent", "api", "storage", "observability", "providers")

#: Reference surfaces: the two Prometheus files (plain text — comments are
#: prose but a comment naming a dead metric misleads the same way) and every
#: string inside the Grafana dashboard JSON (exprs, legends, descriptions).
REFERENCE_FILES = (
    Path("infra/prometheus/alerts-slo.yml"),
    Path("infra/prometheus/prometheus.yml"),
    Path("infra/grafana/dashboards/specproof-slo.json"),
)

#: First-arg literal (``incr("x")``) or module constant (``incr(METRIC_X)``).
_EMIT_CALL = re.compile(
    r"\b(?:incr|set_gauge|observe_duration)\(\s*"
    r"(?:['\"]([a-z0-9_]+)['\"]|([A-Z][A-Z0-9_]*))"
)
#: Module-level string constant usable as a metric name.
_MODULE_CONST = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*['\"]([a-z0-9_]+)['\"]", re.M)
_REFERENCE = re.compile(r"specproof_([a-z0-9_]+)")
#: Histogram exposition adds these to the base name; queries must be reduced
#: back to the base before matching (e.g. ..._fast_bucket → ..._fast).
_HISTOGRAM_SUFFIXES = ("_bucket", "_sum", "_count")

#: Names the code concatenates at runtime — unlistable, so pattern-matched.
#: Each entry carries its emission-site pointer so a failing match can be
#: traced by hand (same discipline as OBSERVABILITY.md's inventory). The
#: vocabularies themselves are NOT hand-copied here:
#: test_concatenated_families_track_their_vocabularies derives them from the
#: product sources, so a new word fails (or extends) the gate together with
#: the code instead of drifting apart from a copy.
CONCATENATED_FAMILIES: dict[str, tuple[re.Pattern[str], str]] = {
    "verdict": (
        re.compile(r"^jobs_[a-z]+_total$"),
        "agent/worker.py: incr(\"jobs_\" + verdict.lower() + \"_total\") — "
        "verdict words are single lowercase tokens",
    ),
    "stage": (
        re.compile(r"^worker_stage_duration_seconds_[a-z0-9_]+$"),
        "agent/worker.py: \"worker_stage_duration_seconds_\" + str(stage) — "
        "graph node names are Python identifiers",
    ),
    "depth": (
        re.compile(r"^jobs_duration_seconds_(fast|deep|release)$"),
        "agent/worker.py #161: \"jobs_duration_seconds_\" + depth.lower() — "
        "word list derived from the shipped CLI choice in the derivation test",
    ),
    "notify": (
        re.compile(r"^notify_(sent|disabled|failed)_total$"),
        "agent/worker.py: incr(\"notify_\" + status.value + \"_total\") — "
        "SendStatus members; skipped/error are worker literals instead",
    ),
    "es_op": (
        re.compile(
            r"^es_request_seconds_"
            r"(bulk|count|delete_by_query|index|indices|ping|search)$"
        ),
        "storage/elasticsearch.py #169: _timed_es(\"<op>\") — op words are "
        "the Elasticsearch client methods the store calls; the vocabulary "
        "is derived from the self.client.<op> call sites by the derivation "
        "test, so a new ES op forces this gate and the family to move "
        "together",
    ),
}


def _walk_strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _walk_strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _walk_strings(item)]
    return []


def _referenced_names() -> set[str]:
    names: set[str] = set()
    for rel in REFERENCE_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if rel.suffix == ".json":
            # Scan every string in the document: exprs, legends and the prose
            # descriptions all quote metric names, and a stale name in prose
            # misleads exactly like a stale one in an expr.
            text = " ".join(_walk_strings(json.loads(text)))
        for match in _REFERENCE.finditer(text):
            names.add(match.group(1))
    # Prose placeholders like jobs_duration_seconds_<depth> capture as a name
    # ending in "_". A real metric never does, and the placeholder names a
    # documented family — drop them rather than widening the families.
    return {n for n in names if not n.endswith("_")}


def _emitted_names() -> set[str]:
    names = {"up"}  # observability/metrics.py::render_text, unconditional
    for emit_dir in EMIT_DIRS:
        for path in sorted((ROOT / emit_dir).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            constants = dict(_MODULE_CONST.findall(text))
            for literal, const in _EMIT_CALL.findall(text):
                if literal:
                    names.add(literal)
                elif const in constants:
                    names.add(constants[const])
    return names


def test_every_referenced_metric_name_traces_to_an_emission_site() -> None:
    referenced = _referenced_names()
    emitted = _emitted_names()

    unaccounted: list[str] = []
    for name in sorted(referenced):
        base = name
        for suffix in _HISTOGRAM_SUFFIXES:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
        if base in emitted:
            continue
        if any(
            pattern.match(base) for pattern, _ in CONCATENATED_FAMILIES.values()
        ):
            continue
        unaccounted.append(name)

    assert not unaccounted, (
        "alerts/dashboards reference metric names with no emission site "
        f"(OBSERVABILITY.md '已接线指标名' is the inventory method): {unaccounted}. "
        "Either the reference is stale (fix the alert/dashboard), or the name "
        "is a new concatenated family (register it in CONCATENATED_FAMILIES "
        "with its emission-site pointer and vocabulary derivation)."
    )


def _alternation_branches(pattern: re.Pattern[str]) -> list[str]:
    """The inside of the family's single (...) group, split on '|'."""
    inside = re.search(r"\(([^()]+)\)", pattern.pattern)
    assert inside is not None, f"family pattern has no (...) group: {pattern.pattern}"
    return inside.group(1).split("|")


def test_concatenated_families_track_their_vocabularies() -> None:
    """Family wildcards must derive from the real vocabulary sources."""

    # notify == SendStatus members (integrations/notify/protocol.py). Derive
    # the expected alternation from the enum so a new member forces this gate
    # and the family to move together.
    from integrations.notify.protocol import SendStatus

    notify_pattern, _ = CONCATENATED_FAMILIES["notify"]
    expected = "^notify_(" + "|".join(m.value for m in SendStatus) + ")_total$"
    assert notify_pattern.pattern == expected, (
        "notify family drifted from SendStatus: "
        f"{notify_pattern.pattern} != {expected}"
    )

    # depth == the shipped CLI choice (the WIDEST enqueue/exec vocabulary:
    # POST /jobs and MCP are currently narrower, and webhook hard-codes FAST —
    # the family must cover what the product can name, not what one gate takes).
    cli_text = (ROOT / "cli" / "specproof" / "commands" / "verify.py").read_text(
        encoding="utf-8"
    )
    choice_match = re.search(r"click\.Choice\(\[([^\]]*)\]\)", cli_text)
    assert choice_match is not None, "CLI verify --depth choice not found"
    depths = [d.lower() for d in re.findall(r'"([A-Z]+)"', choice_match.group(1))]
    depth_pattern, _ = CONCATENATED_FAMILIES["depth"]
    assert sorted(_alternation_branches(depth_pattern)) == sorted(depths), (
        f"depth family {depth_pattern.pattern} != CLI choice {depths}"
    )
    for depth in depths:
        assert depth_pattern.match(f"jobs_duration_seconds_{depth}"), (
            f"family rejects shipped depth {depth}"
        )

    # verdict / stage stay anchored single-token wildcards (their vocabularies
    # are Python-identifier-shaped and enumerated elsewhere); assert the
    # anchoring that keeps them from becoming catch-alls.
    for key in ("verdict", "stage"):
        pattern, _ = CONCATENATED_FAMILIES[key]
        assert pattern.pattern.startswith("^") and pattern.pattern.endswith("$")
        assert "(...)" not in pattern.pattern

    # es_op == the Elasticsearch client methods the store actually calls.
    # Derived from the self.client.<word> call sites in the emission file
    # itself: a new ES client op fails this gate until the family (and the
    # dashboard regex, if the panel is extended) moves with it.
    es_text = (ROOT / "storage" / "elasticsearch.py").read_text(encoding="utf-8")
    es_ops = sorted(set(re.findall(r"self\.client\.(\w+)", es_text)))
    assert es_ops, "no Elasticsearch client call sites found"
    es_pattern, _ = CONCATENATED_FAMILIES["es_op"]
    expected_es = "^es_request_seconds_(" + "|".join(es_ops) + ")$"
    assert es_pattern.pattern == expected_es, (
        f"es_op family {es_pattern.pattern} != client call sites {es_ops}"
    )
    for op in es_ops:
        assert es_pattern.match(f"es_request_seconds_{op}"), (
            f"family rejects shipped es op {op}"
        )


def test_rabbitmq_scrape_stays_paired_with_broker_side_alerts() -> None:
    """The #165 broker-side alerts consume rabbitmq_* series that only the
    rabbitmq scrape job provides — and only in its per-object rendering.

    A revert of the scrape job, or a metrics_path back to the aggregate
    /metrics (which has no per-queue series — verified live against the
    container's own endpoint in #165), leaves the queue/DLQ selectors
    matching nothing: absent series never fire, so the rule files stay
    valid and every broker-side signal goes dark silently. The parity gate
    cannot see this drift (its regex only covers specproof_* names), so
    this test pins the pairing at the text level.
    """
    prom = (ROOT / "infra" / "prometheus" / "prometheus.yml").read_text(
        encoding="utf-8"
    )
    alerts = (ROOT / "infra" / "prometheus" / "alerts-slo.yml").read_text(
        encoding="utf-8"
    )

    # The scrape job must exist, on the per-object path, against the plugin
    # port (rabbitmq_prometheus ships enabled in the management image).
    assert "- job_name: rabbitmq" in prom
    assert "metrics_path: /metrics/per-object" in prom
    assert 'targets: ["rabbitmq:15692"]' in prom

    # Both alerts must still reference the plugin's series.
    assert "alert: SpecproofVerifyQueueBacklogHigh" in alerts
    assert "rabbitmq_queue_messages_ready" in alerts
    assert "alert: SpecproofVerifyDlqNonEmpty" in alerts
    # The DLQ selector derives its shape from storage/rabbitmq.py's
    # dlq_suffix='.dlq' rule. Escaping is double: PromQL string literals
    # reject `\.` (promtool: "unknown escape sequence"), so the regex needs
    # `\\.` inside the PromQL source, and the single-quoted YAML passes it
    # through verbatim — a de-escaped variant fails promtool AND matches
    # garbage names.
    assert 'queue=~"q\\\\..+\\\\.dlq"' in alerts

    # The dashboard panels carry the same double-escaped PromQL. No config
    # gate validates Grafana JSON exprs, so a single-backslash literal there
    # fails only at query time (same silent dark). Compare against the
    # JSON-parsed form: json.load unescapes once, leaving the two-backslash
    # PromQL source.
    dashboard = json.loads(
        (ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json")
        .read_text(encoding="utf-8")
    )
    rabbit_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "rabbitmq_queue" in target.get("expr", "")
    ]
    assert len(rabbit_exprs) == 3, f"expected 3 rabbitmq panel exprs, got {rabbit_exprs}"
    assert any('queue=~"q\\\\..+"' in expr for expr in rabbit_exprs)
    assert any('queue=~"q\\\\..+\\\\.dlq"' in expr for expr in rabbit_exprs)


def test_stage_duration_panel_selector_tracks_the_stage_family() -> None:
    """#166: the per-stage panel selects the concatenated stage family via a
    __name__ regex. The parity gate drops that reference as a prose
    placeholder (the captured name ends in '_'), so a typo'd family name in
    the selector would go unnoticed and the panel would be silently empty —
    pin the exact selector and the two quantiles instead.
    """
    dashboard = json.loads(
        (ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json")
        .read_text(encoding="utf-8")
    )
    stage_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "worker_stage_duration_seconds_" in target.get("expr", "")
    ]
    assert len(stage_exprs) == 2, f"expected p50+p95 stage exprs, got {stage_exprs}"
    expected_selector = (
        '__name__=~"specproof_worker_stage_duration_seconds_[a-z0-9_]+_bucket"'
    )
    for expr in stage_exprs:
        assert expected_selector in expr, expr
    assert any("histogram_quantile(0.95" in expr for expr in stage_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in stage_exprs)

    # Same drift shape for the ES latency panel (#169): the family is
    # concatenated at runtime, the reference regex captures a trailing-
    # underscore placeholder the gate drops, so the exact selector and
    # quantiles are pinned at text level.
    es_exprs = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
        if "es_request_seconds_" in target.get("expr", "")
    ]
    assert len(es_exprs) == 2, f"expected p50+p95 es exprs, got {es_exprs}"
    expected_es_selector = (
        '__name__=~"specproof_es_request_seconds_[a-z_]+_bucket"'
    )
    for expr in es_exprs:
        assert expected_es_selector in expr, expr
    assert any("histogram_quantile(0.95" in expr for expr in es_exprs)
    assert any("histogram_quantile(0.50" in expr for expr in es_exprs)
