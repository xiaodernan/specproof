"""抓取面的第一条真 HTTP 腿：真起服务、真 GET `/metrics`、把 exposition 解析回结构化名字。

源码级门（#161 parity / #217 清单 / #291 渲染契约）都只读**源码或产物文本**，从没有一次
真实 HTTP 抓取（#295 边界⑥ 明说）。这条腿补的正是那一步：把指标注册进进程内注册表，起真实
的 ThreadingHTTPServer（端口 0 由内核分配），用 `http.client` 发 GET，再把响应的 Prometheus
文本**解析回** `name -> (type, value)` 的字典，逐格对账。

为什么值得单独一条腿：`render_text` 的字符串测试（`test_metrics_http.py` 的子串断言）能过，
但「线上真的把这个名字、这个类型、这个值发出来了」是另一件事——中间隔着 HTTP 头、Content-Length、
分块、以及抓取端真正读到的字节。子串命中不等于往返忠实。

带反向控制：一个**没有注册**的名字必须**不出现**在响应里；未知路径必须 404。否则「解析回读」
本身就可能在读一个恒真的空集而不自知。
"""

from __future__ import annotations

import http.client
import re

from observability import metrics
from observability.metrics_http import serve_metrics_in_thread

#: `# TYPE specproof_<name> <type>` — the exposition's type declaration line.
_TYPE_LINE = re.compile(r"^# TYPE specproof_(\S+) (\w+)$")
#: `specproof_<name> <value>` — a plain sample line (counter / gauge / histogram _sum/_count).
_SAMPLE_LINE = re.compile(r"^specproof_(\S+?) (\S+)$")
#: `specproof_<name>_bucket{le="..."} <value>` — a histogram bucket line.
_BUCKET_LINE = re.compile(r'^specproof_(\S+)_bucket\{le="([^"]+)"\} (\S+)$')


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        return resp.status, body
    finally:
        conn.close()


def _parse_exposition(text: str) -> dict[str, dict[str, object]]:
    """Parse Prometheus text back into ``{name: {type, samples, buckets}}``.

    ``samples`` maps the sample suffix (``""`` for a bare counter/gauge, or
    ``_sum`` / ``_count``) to its raw string value; ``buckets`` maps a histogram
    name to ``{le: value}``. This is deliberately a small, strict parser: any
    line that matches neither shape is ignored (comments, blanks), so a malformed
    sample would simply be absent from the result — which is exactly what the
    round-trip assertions catch.
    """
    out: dict[str, dict[str, object]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TYPE_LINE.match(line)
        if m:
            name, kind = m.group(1), m.group(2)
            out.setdefault(name, {"type": kind, "samples": {}, "buckets": {}})
            continue
        m = _BUCKET_LINE.match(line)
        if m:
            base, le, value = m.group(1), m.group(2), m.group(3)
            entry = out.setdefault(base, {"type": "histogram", "samples": {}, "buckets": {}})
            buckets = entry["buckets"]
            assert isinstance(buckets, dict)
            buckets[le] = value
            continue
        m = _SAMPLE_LINE.match(line)
        if m:
            token, value = m.group(1), m.group(2)
            # Histogram _sum/_count arrive as `<base>_sum` / `<base>_count`.
            for suffix in ("_sum", "_count"):
                if token.endswith(suffix):
                    base = token[: -len(suffix)]
                    entry = out.setdefault(
                        base, {"type": "histogram", "samples": {}, "buckets": {}}
                    )
                    samples = entry["samples"]
                    assert isinstance(samples, dict)
                    samples[suffix] = value
                    break
            else:
                entry = out.setdefault(
                    token, {"type": "untyped", "samples": {}, "buckets": {}}
                )
                samples = entry["samples"]
                assert isinstance(samples, dict)
                samples[""] = value
    return out


def test_http_leg_round_trips_counter_gauge_and_histogram() -> None:
    metrics._counters.clear()
    metrics._gauges.clear()
    metrics._histograms.clear()
    metrics.incr("scrape_leg_counter_total", 4)
    metrics.set_gauge("scrape_leg_gauge", 7.5)
    metrics.observe_duration("scrape_leg_duration_seconds", 120.0)
    server = serve_metrics_in_thread(host="127.0.0.1", port=0)
    port = int(server.server_address[1])
    try:
        status, body = _get(port, "/metrics")
        assert status == 200
        parsed = _parse_exposition(body)
        # 计数器：类型 + 值都必须原样往返
        assert parsed["scrape_leg_counter_total"]["type"] == "counter"
        assert parsed["scrape_leg_counter_total"]["samples"][""] == "4"
        # 量规：浮点值透传，不被截断
        assert parsed["scrape_leg_gauge"]["type"] == "gauge"
        assert parsed["scrape_leg_gauge"]["samples"][""] == "7.5"
        # 直方图：类型 + 桶 + _sum/_count 都在
        hist = parsed["scrape_leg_duration_seconds"]
        assert hist["type"] == "histogram"
        assert hist["buckets"]["+Inf"] == "1"
        assert hist["samples"]["_count"] == "1"
        assert hist["samples"]["_sum"] == "120.0"
    finally:
        server.shutdown()
        server.server_close()
        metrics._counters.clear()
        metrics._gauges.clear()
        metrics._histograms.clear()


def test_http_leg_serves_sanitized_names_on_the_wire() -> None:
    # 名字里的 - 与 . 必须在**线上**被清洗：抓取端读到的是清洗后的名字
    metrics._counters.clear()
    try:
        metrics.incr("scrape-leg.dotted", 1)
        server = serve_metrics_in_thread(host="127.0.0.1", port=0)
        port = int(server.server_address[1])
        try:
            status, body = _get(port, "/metrics")
            assert status == 200
            parsed = _parse_exposition(body)
            assert "scrape_leg_dotted" in parsed
            assert parsed["scrape_leg_dotted"]["samples"][""] == "1"
            # 原始非法名不得出现在线上字节里
            assert "scrape-leg.dotted" not in body
        finally:
            server.shutdown()
            server.server_close()
    finally:
        metrics._counters.clear()


def test_http_leg_reverse_control_unregistered_name_is_absent() -> None:
    # 反向控制：没注册过的名字绝不能出现，否则「解析回读」可能在读一个恒真的空集
    metrics._counters.clear()
    metrics._gauges.clear()
    try:
        metrics.incr("scrape_leg_only_this", 1)
        server = serve_metrics_in_thread(host="127.0.0.1", port=0)
        port = int(server.server_address[1])
        try:
            status, body = _get(port, "/metrics")
            assert status == 200
            parsed = _parse_exposition(body)
            assert "scrape_leg_only_this" in parsed
            assert "scrape_leg_never_registered" not in parsed
            # 未知路径仍是 404（抓取端打错端点时要能分辨）
            status_404, _ = _get(port, "/metrics/typo")
            assert status_404 == 404
        finally:
            server.shutdown()
            server.server_close()
    finally:
        metrics._counters.clear()
        metrics._gauges.clear()
