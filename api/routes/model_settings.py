"""Authenticated, server-side model setup and live diagnostics."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from api.auth import enforce_rate_limit, require_api_key
from providers.config import load_model_config, public_model_config, save_model_config

router = APIRouter(prefix="/api/v1/model", tags=["model-settings"],
                   dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)])


def require_model_admin(request: Request) -> None:
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        # This deployment-level endpoint changes the shared model configuration.
        # Tenant-scoped identities cannot mutate another tenant's provider route.
        raise HTTPException(403, "共享模型设置由部署管理员管理，请联系管理员配置模型服务。")


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    base_url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr = SecretStr("")
    model: str = Field(min_length=1, max_length=160)
    reasoning_effort: Literal["", "low", "medium", "high", "xhigh", "max"] = "max"
    protocol: Literal["responses", "chat_completions"] = "responses"


@router.get("/config", dependencies=[Depends(require_model_admin)])
def get_config() -> dict[str, Any]:
    try:
        return public_model_config()
    except (ValueError, OSError):
        raise HTTPException(503, "无法读取模型配置，请检查服务端配置文件。") from None


@router.post("/config", dependencies=[Depends(require_model_admin)])
def set_config(payload: ModelSettings) -> dict[str, Any]:
    try:
        data = payload.model_dump(exclude={"api_key"})
        data["api_key"] = payload.api_key.get_secret_value()
        return save_model_config(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except OSError:
        raise HTTPException(503, "模型配置保存失败，请检查服务端目录权限。") from None


@router.post("/test", dependencies=[Depends(require_model_admin)])
async def test_connection() -> dict[str, Any]:
    from providers.base import LLMMessage
    from providers.openai_compatible import OpenAICompatibleProvider

    try:
        cfg = load_model_config()
    except (ValueError, OSError):
        raise HTTPException(422, "模型配置无效，请检查保存的模型配置。") from None
    if not cfg["api_key"] or not cfg["base_url"]:
        raise HTTPException(422, "请先保存模型服务地址和 API Key，再测试连接。")
    started = time.monotonic()
    provider = None
    result: dict[str, Any] = {
        "model": cfg["model"], "protocol": cfg["protocol"],
        "reasoning_effort": cfg["reasoning_effort"],
    }
    try:
        provider = OpenAICompatibleProvider(timeout=45, max_retries=0)
        response = await asyncio.wait_for(provider.chat(
            [LLMMessage(role="user", content="Reply only with SPEC_OK.")],
            opts={"max_tokens": 512}, timeout=45,
        ), timeout=50)
        ok = bool(response.content and response.content.strip() == "SPEC_OK")
        result.update(ok=ok, message="模型已返回有效内容，可以开始 AI 开发。" if ok else
                      "接口已响应，但没有返回文本，请检查模型权限与输出配置。",
                      usage=response.usage)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        error_code = "connection_failed"
        if status == 401:
            message, error_code = "模型 API Key 无效或已过期，请重新配置。", "invalid_key"
        elif status == 403:
            message, error_code = "模型服务拒绝访问，请检查账号的模型权限。", "forbidden"
        elif status == 404:
            message, error_code = "模型或接口不存在，请核对服务地址、模型名和协议。", "not_found"
        elif status == 429:
            message = "模型服务限流或额度不足，请稍后重试或检查账户额度。"
            error_code = "rate_limited"
        elif isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
            message, error_code = "模型响应超时，请稍后重试。", "timeout"
        else:
            message = "模型请求失败，请检查服务地址、接口协议或网络连接。"
        result.update(ok=False, message=message, error_code=error_code)
    finally:
        if provider is not None:
            await provider.close()
    result["latency_ms"] = round((time.monotonic() - started) * 1000)
    return result
