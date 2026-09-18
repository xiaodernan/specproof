"""Private server-side model configuration, separate from workspace credentials."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_ROOT = Path(__file__).resolve().parents[1]
_ENV_FIELDS = {
    "base_url": "LLM_BASE_URL", "api_key": "LLM_API_KEY", "model": "LLM_MODEL",
    "reasoning_effort": "LLM_REASONING_EFFORT", "protocol": "LLM_PROTOCOL",
}


def config_path() -> Path:
    return Path(os.getenv("SPECPROOF_MODEL_CONFIG", str(_ROOT / ".local" / "llm.json")))


def normalize_base_url(value: str) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("模型服务地址必须是有效的 http 或 https URL。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("模型服务地址不能包含凭据、查询参数或片段。")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
    if not path.endswith("/v1"):
        path += "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def load_model_config() -> dict[str, str]:
    result = {"base_url": "", "api_key": "", "model": "deepseek-v4-pro",
              "reasoning_effort": "", "protocol": "chat_completions", "source": "unconfigured"}
    env = {field: os.environ[name].strip() for field, name in _ENV_FIELDS.items()
           if name in os.environ}
    route_from_env = "base_url" in env or "model" in env
    path = config_path()
    if path.is_file() and not route_from_env:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise ValueError("模型配置文件无法读取或格式无效。") from exc
        if not isinstance(raw, dict) or any(
            key in raw and not isinstance(raw[key], str) for key in _ENV_FIELDS
        ):
            raise ValueError("模型配置字段必须为文本。")
        result.update({key: raw[key].strip() for key in _ENV_FIELDS if key in raw})
        result["source"] = "local_file"
    # Explicit empty values deliberately clear a credential or optional effort.
    result.update(env)
    if env:
        result["source"] = "environment"
    if "protocol" not in env and (route_from_env or result["source"] == "unconfigured"):
        result["protocol"] = (
            "responses" if result["model"].startswith("gpt-6") else "chat_completions"
        )
    if "reasoning_effort" not in env and route_from_env:
        result["reasoning_effort"] = "max" if result["model"].startswith("gpt-6") else ""
    if result["protocol"] not in {"responses", "chat_completions", "chat"}:
        raise ValueError("模型接口协议无效，请选择 Responses 或 Chat Completions。")
    if result["reasoning_effort"] not in {"", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("模型推理强度无效。")
    if result["base_url"]:
        result["base_url"] = normalize_base_url(result["base_url"])
    return result


def public_model_config() -> dict[str, Any]:
    cfg = load_model_config()
    key = cfg["api_key"]
    return {field: value for field, value in cfg.items() if field != "api_key"} | {
        "configured": bool(cfg["base_url"] and key and key != "replace_me"),
        "key_hint": "已保存" if key and key != "replace_me" else "未设置",
    }


def save_model_config(values: dict[str, str]) -> dict[str, Any]:
    if any(name in os.environ for name in _ENV_FIELDS.values()):
        raise ValueError("当前模型由部署环境变量管理，请在部署配置中修改后重启服务。")
    cfg = load_model_config()
    for key, value in values.items():
        if key in _ENV_FIELDS and (key != "api_key" or value.strip()):
            cfg[key] = value.strip()
    cfg["base_url"] = normalize_base_url(cfg["base_url"])
    if not cfg["api_key"] or cfg["api_key"] == "replace_me":
        raise ValueError("请填写模型服务商提供的 API Key。")
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".llm-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({key: cfg[key] for key in _ENV_FIELDS}, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return public_model_config()
