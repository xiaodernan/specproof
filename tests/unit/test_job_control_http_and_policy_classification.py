"""`agent/job_control.classify_job_error` 的未覆盖分支：HTTP 提供方分类 + 两个策略异常。

`test_worker_error_classify.py` 已钉住 TimeoutError / BuildFailure / ProviderAuthError /
ConnectionError / subprocess / MySQL OperationalError / Redis ConnectionError /
InvalidStateTransition / unknown。但**没钉**：
- 两个策略异常（`JobCancelledError` / `LeaseLostError`）；
- HTTP 提供方的四档（401/403、429、5xx、其余 4xx）—— 这四档直接决定 `retryable`，
  也就是「这个作业该不该重试」；
- `httpx` 的传输层错误（超时 / 连接失败）与 `ConnectTimeout` 的**优先级**；
- `RedisTimeoutError` / MySQL `InterfaceError`（只测了各自的兄弟类）；
- `OSError` 兜底。

只加测试，`agent/job_control.py` 一字未动。
"""

from __future__ import annotations

import httpx
import pytest
from pymysql.err import InterfaceError as MySQLLinkError
from redis.exceptions import TimeoutError as RedisTimeoutError

from agent.job_control import (
    JobCancelledError,
    LeaseLostError,
    classify_job_error,
)


def _classify(exc: BaseException) -> tuple[str, str, bool]:
    result = classify_job_error(exc)
    return result.cls, result.code, result.retryable


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.invalid/v1/chat")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"HTTP {status}", request=request, response=response
    )


# ── 策略异常 ──────────────────────────────────────────────────────────


def test_job_cancelled_is_policy_not_retryable() -> None:
    assert _classify(JobCancelledError("job-1", "differential_before")) == (
        "policy",
        "cancelled_at_checkpoint",
        False,
    )


def test_lease_lost_is_policy_not_retryable() -> None:
    assert _classify(LeaseLostError("job-1", "worker-1")) == (
        "policy",
        "lease_lost",
        False,
    )


# ── HTTP 提供方四档（决定 retryable） ─────────────────────────────────


@pytest.mark.parametrize("status", [401, 403])
def test_http_auth_rejection_is_provider_not_retryable(status: int) -> None:
    assert _classify(_http_status_error(status)) == (
        "provider",
        "provider_auth",
        False,
    )


def test_http_429_is_provider_rate_limited_retryable() -> None:
    assert _classify(_http_status_error(429)) == (
        "provider",
        "provider_rate_limited",
        True,
    )


@pytest.mark.parametrize("status", [500, 503])
def test_http_5xx_is_provider_server_error_retryable(status: int) -> None:
    assert _classify(_http_status_error(status)) == (
        "provider",
        "provider_server_error",
        True,
    )


@pytest.mark.parametrize("status", [400, 404])
def test_http_other_4xx_is_provider_http_error_not_retryable(status: int) -> None:
    assert _classify(_http_status_error(status)) == (
        "provider",
        "provider_http_error",
        False,
    )


# ── httpx 传输层 ──────────────────────────────────────────────────────


def test_http_timeout_is_system_retryable() -> None:
    assert _classify(httpx.TimeoutException("slow")) == (
        "system",
        "http_timeout",
        True,
    )


def test_http_connect_error_is_system_retryable() -> None:
    assert _classify(httpx.ConnectError("refused")) == (
        "system",
        "http_connect",
        True,
    )


def test_connect_timeout_prefers_timeout_over_connect() -> None:
    # ConnectTimeout 同时是 TimeoutException 与 ConnectError 的子类；代码里
    # TimeoutException 的分支在前 ⇒ 归类为 http_timeout，而不是 http_connect。
    assert _classify(httpx.ConnectTimeout("slow connect")) == (
        "system",
        "http_timeout",
        True,
    )


# ── 存储兄弟类 + OSError 兜底 ─────────────────────────────────────────


def test_redis_timeout_is_system_retryable() -> None:
    assert _classify(RedisTimeoutError("slow")) == (
        "system",
        "redis_unavailable",
        True,
    )


def test_mysql_interface_error_is_system_retryable() -> None:
    assert _classify(MySQLLinkError(0, "gone away")) == (
        "system",
        "mysql_unavailable",
        True,
    )


def test_os_error_is_system_retryable() -> None:
    assert _classify(OSError(28, "No space left on device")) == (
        "system",
        "os_error",
        True,
    )


# ── 全局不变量：统一词表 + 信封形状 ───────────────────────────────────


def test_every_classification_uses_the_unified_vocabulary() -> None:
    samples: list[BaseException] = [
        JobCancelledError("j", "s"),
        LeaseLostError("j", "w"),
        _http_status_error(429),
        httpx.TimeoutException("t"),
        OSError("e"),
        ValueError("v"),
    ]
    for exc in samples:
        result = classify_job_error(exc)
        assert result.cls in ("system", "repo", "provider", "policy", "unknown")
        assert set(result.as_dict()) == {"class", "code", "retryable", "note"}
        assert result.as_dict()["class"] == result.cls
