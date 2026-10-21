"""Evidence Fragment schema (Phase 2, P2-1).

每个 Evidence Fragment 描述一次实验中实际观察到的内容，带
完整的 base/head 对比、归一化规则、证据引用和可重放性标记。
所有 Fragment 都可序列化为 JSON，写入 MongoDB Evidence Pack 和
MinIO 对象，支持离线回放和审计。

设计原则（诚实降级）：
- 只描述实际观测到的内容，未采集返回缺证据记录（绝不伪造）
- base/head 都有值时才做比较，单边缺失标记为缺证据
- 支持字段忽略、顺序归一化、敏感脱敏、随机遮罩、时间容差
- 无法可靠比较的部分返回 AMBIGUOUS，不强行判断
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _digest(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


# ── Fragment 状态 ─────────────────────────────────────────────────────

FragmentStatus = str  # COMPLIANT / REGRESSION / AMBIGUOUS / NON_REPRODUCIBLE / NO_EVIDENCE


@dataclass(frozen=True)
class EvidenceFragment:
    """单个实验的证据片段，base/head 对比结果."""

    # ── 标识 ──────────────────────────────────────────────────────
    experiment_id: str          # 关联的实验 ID
    fragment_type: str  # http | db | redis | mq | schema | perf | static | build | object
    collector_version: str      # 采集器版本，用于回放时验证兼容性
    collected_at: str           # 采集时间 (ISO-8601)

    # ── 观测结果 ──────────────────────────────────────────────────
    base: dict[str, Any] | None      # Base 侧观测值（None 表示未采集）
    head: dict[str, Any] | None      # Head 侧观测值（None 表示未采集）
    normalization: dict[str, Any] | None   # 归一化规则说明
    comparison: dict[str, Any] | None      # 比较结果（diff 字段、变化类型等）

    # ── 判定 ────────────────────────────────────────────────────────
    status: FragmentStatus  # COMPLIANT / REGRESSION / AMBIGUOUS / ...
    confidence: float = 1.0     # 0.0-1.0，判定置信度

    # ── 证据引用 ────────────────────────────────────────────────────
    evidence_ref: str | None = None      # MinIO/Mongo 对象引用
    reproducibility: str = "unknown"     # "reproducible" | "flaky" | "environment" | "unknown"

    # ── 扩展 ────────────────────────────────────────────────────────
    extension: dict[str, Any] = field(default_factory=dict)

    # ── 序列化 ──────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "fragment_type": self.fragment_type,
            "collector_version": self.collector_version,
            "collected_at": self.collected_at,
            "base": self.base,
            "head": self.head,
            "normalization": self.normalization,
            "comparison": self.comparison,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_ref": self.evidence_ref,
            "reproducibility": self.reproducibility,
            "extension": dict(self.extension),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceFragment:
        return cls(
            experiment_id=str(data["experiment_id"]),
            fragment_type=str(data["fragment_type"]),
            collector_version=str(data.get("collector_version", "1.0.0")),
            collected_at=str(data.get("collected_at") or _now_iso()),
            base=data.get("base"),
            head=data.get("head"),
            normalization=data.get("normalization"),
            comparison=data.get("comparison"),
            status=str(data["status"]),
            confidence=float(data.get("confidence") or 1.0),
            evidence_ref=data.get("evidence_ref"),
            reproducibility=str(data.get("reproducibility") or "unknown"),
            extension=dict(data.get("extension") or {}),
        )

    def digest(self) -> str:
        """Fragment 内容的 SHA-256 摘要，用于证据链完整性校验."""
        return _digest(self.to_dict())


# ── 具体 Fragment 子类型（类型别名，语义化使用）──────────────────────

@dataclass(frozen=True)
class HttpObservation(EvidenceFragment):
    """HTTP 观测：status/body/headers、请求计数、响应时间分位数."""


@dataclass(frozen=True)
class DbObservation(EvidenceFragment):
    """数据库观测：行内容、行数、事务状态、锁等待."""


@dataclass(frozen=True)
class RedisObservation(EvidenceFragment):
    """Redis 观测：key/value/TTL、失效时间、命中/未命中."""


@dataclass(frozen=True)
class MqObservation(EvidenceFragment):
    """消息队列观测：exchange/routingKey/payload/publish_count/consumer_id."""


@dataclass(frozen=True)
class SchemaObservation(EvidenceFragment):
    """Schema 观测：OpenAPI/schema diff、字段增删改."""


@dataclass(frozen=True)
class PerformanceObservation(EvidenceFragment):
    """性能观测：响应时间分位数、QPS、错误率."""


@dataclass(frozen=True)
class StaticObservation(EvidenceFragment):
    """静态观测：源码差分、AST 检查、契约检查器结果."""


@dataclass(frozen=True)
class BuildObservation(EvidenceFragment):
    """构建观测：编译退出码、构建时间、工具链版本."""


@dataclass(frozen=True)
class ObjectObservation(EvidenceFragment):
    """对象存储观测：bucket/object-name、size、content_type、sha256、version.

    The object store is where the evidence pack and the capsules live.
    Until this type existed, an object could be written and nothing in
    the evidence chain could say WHERE it is — the bytes were durable
    and the chain had no address for them (P1-7).
    """


__all__ = [
    "EvidenceFragment",
    "HttpObservation",
    "DbObservation",
    "RedisObservation",
    "MqObservation",
    "SchemaObservation",
    "PerformanceObservation",
    "StaticObservation",
    "BuildObservation",
    "ObjectObservation",
    "FragmentStatus",
    "_digest",
]
