"""抓取面全量对账：代码能发射的**每一个**字面量指标名，线上都必须以正确类型出现。

#326 的 HTTP 腿只验了「我注册的 == 我解析回来的」（三五个名字）。本文件把对账推到名字册：
名字集来自 #161 parity 门的 `emitted_types()`（它 AST/正则扫过 `EMIT_DIRS` 下每个
`incr`/`set_gauge`/`observe_duration` 调用，把字面量名与模块常量都解析出来，并给每个名字
一个类型）。于是这条腿回答的是「**代码说它能发射的每一个名字，抓取端真的读得到吗**」——
一个名字若在源码里有 emit 站点、却在 HTTP 链路上丢失（清洗把它并掉、类型写错、被截断），
源码级门全绿也照样漏过去；只有真发一次 GET 才看得见。

口径（诚实边界）：
- 只覆盖**字面量**发射名（`emitted_types()` 明确排除运行期拼接前缀——那些名字在运行前不可列举，
  由 `concatenated_prefix_types()` 管，属另一条腿）。
- `up` 由 `render_text` 无条件发射（硬编码那一行），**不**经注册表；本文件跳过注册它，只断言它在线。
- 注册用的是「每个名字 1 次」的最小剂量：本条腿判的是**可服务性**（名字/类型到达抓取端），
  不是数值语义（数值语义由 `test_metrics_render_format_contract.py` / `test_metrics_http.py` 管）。
"""

from __future__ import annotations

import http.client
import re

from observability import metrics
from observability.metrics import sanitize_metric_name
from observability.metrics_http import serve_metrics_in_thread
from tests.unit.test_observability_metric_parity import emitted_types

_TYPE_LINE = re.compile(r"^# TYPE specproof_(\S+) (\w+)$")
_BUCKET_LINE = re.compile(r'^specproof_(\S+)_bucket\{le="[^"]+"\} \S+$')
_SAMPLE_LINE = re.compile(r"^specproof_(\S+?) \S+$")


def _get(port: int, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8")
    finally:
        conn.close()


def _served_types(text: str) -> dict[str, str]:
    """Base name -> exposition type, from the served text.

    Reads `# TYPE` lines (authoritative) and falls back to the sample shape for
    a histogram's `_bucket` siblings when the type line is absent. A counter or
    gauge always has a `# TYPE` line because `render_text` writes one per store.
    """
    served: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        m = _TYPE_LINE.match(line)
        if m:
            served[m.group(1)] = m.group(2)
            continue
        m = _BUCKET_LINE.match(line)
        if m:
            served.setdefault(m.group(1), "histogram")
            continue
        m = _SAMPLE_LINE.match(line)
        if m:
            token = m.group(1)
            for suffix in ("_sum", "_count"):
                if token.endswith(suffix):
                    served.setdefault(token[: -len(suffix)], "histogram")
                    break
    return served


def _register(name: str, kind: str) -> None:
    if kind == "counter":
        metrics.incr(name, 1)
    elif kind == "gauge":
        metrics.set_gauge(name, 1.0)
    elif kind == "histogram":
        metrics.observe_duration(name, 1.0)
    else:  # pragma: no cover - emitted_types only yields the three above
        raise AssertionError(f"unexpected emit kind {kind!r} for {name!r}")


def test_every_emitted_name_is_served_with_its_declared_type() -> None:
    emitted = emitted_types()
    # 断言名字册不是空的——否则下面的循环会「全绿」地什么也不验（恒真空集陷阱）
    assert len(emitted) > 10, (
        f"emitted_types() returned only {len(emitted)} names; scan read nothing"
    )
    metrics._counters.clear()
    metrics._gauges.clear()
    metrics._histograms.clear()
    try:
        for name, kind in emitted.items():
            if name == "up":
                continue  # render_text 无条件发射，不经注册表（见模块 docstring）
            _register(name, kind)
        server = serve_metrics_in_thread(host="127.0.0.1", port=0)
        port = int(server.server_address[1])
        try:
            status, body = _get(port, "/metrics")
            assert status == 200
            served = _served_types(body)
        finally:
            server.shutdown()
            server.server_close()

        missing: list[str] = []
        wrong_type: list[str] = []
        for name, kind in emitted.items():
            wire = sanitize_metric_name(name)
            if wire not in served:
                missing.append(f"{name} -> specproof_{wire}")
            elif served[wire] != kind:
                wrong_type.append(f"{name}: declared {kind}, served {served[wire]}")
        assert not missing, (
            "emitted names the scrape surface does not serve (lost on the wire): "
            + ", ".join(sorted(missing))
        )
        assert not wrong_type, "served type disagrees with the emit call: " + ", ".join(
            sorted(wrong_type)
        )
        # `up` 是 render_text 的硬编码行，必须在线
        assert served.get("up") == "gauge"
    finally:
        metrics._counters.clear()
        metrics._gauges.clear()
        metrics._histograms.clear()
