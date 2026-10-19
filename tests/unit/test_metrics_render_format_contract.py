"""`observability/metrics.py` 的 exposition 格式契约栅栏（计数器 / 量规行）。

`render_text` 产出的文本是 Prometheus 抓取端唯一依赖的契约：每一类指标都得带正确的
`# TYPE specproof_<name> <type>` 行，数值按 Prometheus 文本格式输出，指标名里的 `-`/`.`
必须清洗成 `_`（否则会产生非法指标名，抓取端静默丢弃整段）。histogram 路径已由
`test_metrics_http.py` 覆盖，本文件只锁 counter / gauge 这两类未被独立断言的行格式，
防止有人改 `render_text` 时把类型声明或名字清洗悄悄改坏——那会让指标在抓取端「消失」而
不报任何错（典型的「跳过 ≠ 通过」式静默失效）。

注意：`int(value)` 对整数计数（默认 `incr` 步长 1.0、所有真实计数都是整数值）等价于 round，
本测试只在整数路径上钉契约，不把分数截断当成「正确」去锁死。
"""

from __future__ import annotations

from observability import metrics
from observability.metrics import sanitize_metric_name


def test_counter_renders_type_and_integer_value() -> None:
    metrics._counters.clear()
    try:
        metrics.incr("jobs_completed_total", 1)
        metrics.incr("jobs_completed_total", 1)
        text = metrics.render_text()
        assert "# TYPE specproof_jobs_completed_total counter" in text
        # 整数计数必须原样出现，不得被截断/转成浮点
        assert "specproof_jobs_completed_total 2" in text
    finally:
        metrics._counters.clear()


def test_gauge_renders_type_and_value() -> None:
    metrics._gauges.clear()
    try:
        metrics.set_gauge("queue_depth", 3.5)
        text = metrics.render_text()
        assert "# TYPE specproof_queue_depth gauge" in text
        assert "specproof_queue_depth 3.5" in text
    finally:
        metrics._gauges.clear()


def test_metric_name_sanitization_dashes_and_dots() -> None:
    # 名字里的 - 与 . 必须清洗成 _，否则产出非法指标名
    metrics._counters.clear()
    try:
        metrics.incr("webhook-github.handling", 1)
        text = metrics.render_text()
        assert "# TYPE specproof_webhook_github_handling counter" in text
        assert "specproof_webhook_github_handling 1" in text
        # 原始非法名不得残留
        assert "webhook-github" not in text
    finally:
        metrics._counters.clear()


def test_snapshot_structure_is_stable() -> None:
    metrics._counters.clear()
    metrics._gauges.clear()
    metrics._histograms.clear()
    try:
        metrics.incr("a_total", 1)
        metrics.set_gauge("b_gauge", 2.0)
        snap = metrics.snapshot()
        # 三类顶层键必须都在，且 gauge 原值透传（不截断、不字符串化）
        assert set(snap) >= {"counters", "gauges", "histograms", "uptime_seconds"}
        assert snap["counters"] == {"a_total": 1.0}
        assert snap["gauges"] == {"b_gauge": 2.0}
    finally:
        metrics._counters.clear()
        metrics._gauges.clear()
        metrics._histograms.clear()


def test_sanitize_metric_name_collapses_dash_and_dot() -> None:
    # 清洗契约：slug 里的 - 与 . 必须压成 _，否则产出非法指标名、被抓取端静默丢弃
    assert sanitize_metric_name("webhook-github.handling") == "webhook_github_handling"
    assert sanitize_metric_name("foo.bar-baz") == "foo_bar_baz"
    assert sanitize_metric_name("already_clean") == "already_clean"
    # 其余字符透传：若将来出现新的非法字符，应作为真实渲染差异浮出来，而不是被过度替换藏掉
    assert sanitize_metric_name("ns:name") == "ns:name"
