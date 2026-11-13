"""LLM 用量与缓存健康——token 级账本的只读聚合端点(#BB5)。

数据源是 providers/usage_ledger.py 的 JSONL 账本(provider 边界逐调用一行,
无 prompt 内容/无租户标识/无业务数据,红线 §四 成立)。本路由只读:

* ``GET /api/v1/llm/usage/summary?window_hours=24``——窗口内调用量/错误率/
  流式占比/token 总量/缓存命中率(含诚实口径:hit_rate 只对网关上报了
  cached 的调用子集计算,子集大小一并给出)/延迟分位/按 kind 拆分/按小时
  趋势桶。

鉴权与 /api/v1/model 同族:require_api_key(多租户下 Bearer principal 视为
已满足,单租户走 legacy key),加 enforce_rate_limit。这是系统级聚合遥测,
与 /health 同类——不含任何租户维度数据,不存在跨租户读取问题。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from api.auth import enforce_rate_limit, require_api_key
from providers.usage_ledger import summary as ledger_summary

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/llm",
    tags=["llm-usage"],
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)

#: 窗口上限:30 天。更大的窗口只是把磁盘上有限的记录反复聚合。
MAX_WINDOW_HOURS = 24 * 30


@router.get("/usage/summary")
async def usage_summary(
    window_hours: float = Query(default=24.0, gt=0.0),
) -> dict[str, Any]:
    """Token 级用量与缓存健康聚合(只读,尽力而为的账本)。"""
    return ledger_summary(window_hours=min(window_hours, MAX_WINDOW_HOURS))
