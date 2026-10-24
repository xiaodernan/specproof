"""Tests for OpenAPI Fuzzing (Phase 4)."""

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from experiments.openapi_fuzzing import (
    ApiOperation,
    FuzzResult,
    FuzzStrategy,
    OpenAPIFuzzer,
    OpenAPIFuzzReport,
    OpenAPISpecParser,
    PayloadGenerator,
    Shrinker,
)


def test_fuzz_strategy_enum() -> None:
    """All fuzz strategies defined."""
    assert FuzzStrategy.BOUNDARY.value == "boundary"
    assert FuzzStrategy.TYPE_MISMATCH.value == "type_mismatch"
    assert FuzzStrategy.REQUIRED_MISSING.value == "required_missing"
    assert FuzzStrategy.ENUM_VIOLATION.value == "enum_violation"
    assert FuzzStrategy.FORMAT_VIOLATION.value == "format_violation"
    assert FuzzStrategy.INJECTION.value == "injection"
    assert FuzzStrategy.OVERSIZED.value == "oversized"


def test_api_operation_creation() -> None:
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create a user",
        parameters=[],
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 50},
                    "age": {"type": "integer", "minimum": 0, "maximum": 150},
                    "email": {"type": "string", "format": "email"},
                },
                "required": ["name", "email"],
            }
        },
    )
    assert op.method == "POST"
    assert op.path == "/users"
    assert op.operation_id == "createUser"


def test_openapi_spec_parser_loads_yaml() -> None:
    """Parser loads YAML spec."""
    spec_content = """
openapi: "3.0.0"
info:
  title: Test API
  version: "1.0"
paths:
  /users:
    post:
      operationId: createUser
      summary: Create user
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
              required: [name]
"""
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = Path(tmpdir) / "spec.yaml"
        spec_path.write_text(spec_content, encoding="utf-8")
        parser = OpenAPISpecParser(spec_path)
        spec = parser.load()
        assert spec["openapi"] == "3.0.0"
        operations = parser.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_id == "createUser"


def test_openapi_spec_parser_loads_json() -> None:
    """Parser loads JSON spec."""
    spec_content = {
        "openapi": "3.0.0",
        "info": {"title": "Test", "version": "1.0"},
        "paths": {
            "/items": {
                "get": {
                    "operationId": "listItems",
                    "summary": "List items",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = Path(tmpdir) / "spec.json"
        spec_path.write_text(json.dumps(spec_content), encoding="utf-8")
        parser = OpenAPISpecParser(spec_path)
        spec = parser.load()
        assert spec["openapi"] == "3.0.0"
        operations = parser.get_operations()
        assert len(operations) == 1
        assert operations[0].method == "GET"


def test_payload_generator_valid_payload() -> None:
    """Generator produces valid payload from schema."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer", "minimum": 0, "maximum": 150},
                    "active": {"type": "boolean"},
                },
                "required": ["name"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payload = generator.generate_valid_payload(op)
    assert "name" in payload
    assert isinstance(payload["name"], str)
    if "age" in payload:
        assert isinstance(payload["age"], int)
        assert 0 <= payload["age"] <= 150
    if "active" in payload:
        assert isinstance(payload["active"], bool)


def test_boundary_payloads() -> None:
    """Boundary strategy generates boundary values."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "age": {"type": "integer", "minimum": 18, "maximum": 100},
                    "name": {"type": "string", "minLength": 2, "maxLength": 20},
                },
                "required": ["age", "name"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.BOUNDARY)
    # Should have boundary values for age (17, 18, 100, 101) and name lengths (1, 2, 20, 21)
    ages = [p["age"] for p in payloads if "age" in p]
    assert 17 in ages
    assert 18 in ages
    assert 100 in ages
    assert 101 in ages


def test_type_mismatch_payloads() -> None:
    """Type mismatch strategy generates wrong types."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                    "active": {"type": "boolean"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "metadata": {"type": "object"},
                },
                "required": ["name"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.TYPE_MISMATCH)
    # Should have type mismatches for each field
    types_tested = set()
    for p in payloads:
        for k, v in p.items():
            if k == "name" and isinstance(v, int):
                types_tested.add("string_as_int")
            elif k == "age" and isinstance(v, str):
                types_tested.add("int_as_string")
            elif k == "active" and isinstance(v, str):
                types_tested.add("bool_as_string")
    assert len(types_tested) >= 2


def test_required_missing_payloads() -> None:
    """Required missing strategy omits required fields."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                },
                "required": ["name", "email"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.REQUIRED_MISSING)
    # Should have payloads missing name and missing email
    missing_fields = set()
    for p in payloads:
        for req in ["name", "email"]:
            if req not in p:
                missing_fields.add(req)
    assert "name" in missing_fields
    assert "email" in missing_fields


def test_enum_violation_payloads() -> None:
    """Enum violation strategy uses values outside enum."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["admin", "user", "guest"]},
                },
                "required": ["role"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.ENUM_VIOLATION)
    for p in payloads:
        assert p["role"] not in ["admin", "user", "guest"]
        assert p["role"].startswith("NOT_IN_ENUM_")


def test_format_violation_payloads() -> None:
    """Format violation strategy generates invalid formats."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "format": "email"},
                    "birthday": {"type": "string", "format": "date-time"},
                },
                "required": ["email"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.FORMAT_VIOLATION)
    emails = [p["email"] for p in payloads if "email" in p]
    assert any("@" not in e for e in emails)


def test_injection_payloads() -> None:
    """Injection strategy generates injection payloads."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "bio": {"type": "string"},
                },
                "required": ["name"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.INJECTION)
    # Should have SQL injection, XSS, command injection, etc.
    all_values: list[Any] = []
    for p in payloads:
        all_values.extend(p.values())
    assert any("OR '1'='1" in str(v) for v in all_values)
    assert any("<script>" in str(v) for v in all_values)


def test_oversized_payloads() -> None:
    """Oversized strategy generates large payloads."""
    op = ApiOperation(
        method="POST",
        path="/users",
        operation_id="createUser",
        summary="Create user",
        request_body={
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            }
        },
    )
    generator = PayloadGenerator([op])
    payloads = generator.generate_fuzz_payloads(op, FuzzStrategy.OVERSIZED)
    # Should have very long strings or large arrays
    large_found = False
    for p in payloads:
        for v in p.values():
            if isinstance(v, str) and len(v) > 50000:
                large_found = True
            if isinstance(v, list) and len(v) > 5000:
                large_found = True
    assert large_found


def test_shrinker_removes_fields() -> None:
    """Shrinker removes fields while keeping failure."""
    def test_fn(payload: dict[str, Any]) -> bool:
        # Failure is REPRODUCED if 'required_field' is PRESENT
        # (removing it makes the test pass)
        return "required_field" in payload

    original = {
        "required_field": "value",
        "optional_field": "can_remove",
        "another": "field",
    }
    shrunk = Shrinker.shrink(original, test_fn)
    assert "optional_field" not in shrunk
    assert "another" not in shrunk
    assert "required_field" in shrunk


def test_shrinker_shortens_strings() -> None:
    """Shrinker shortens string values."""
    def test_fn(payload: dict[str, Any]) -> bool:
        # Failure is REPRODUCED if 'long_field' length > 10
        return payload.get("long_field", "") and len(payload["long_field"]) > 10

    original = {"long_field": "x" * 100}
    shrunk = Shrinker.shrink(original, test_fn)
    # Should shrink to a length that still triggers failure (> 10)
    assert len(shrunk["long_field"]) > 10
    assert len(shrunk["long_field"]) < 100


def test_fuzz_result_creation() -> None:
    op = ApiOperation(
        method="POST",
        path="/test",
        operation_id="testOp",
        summary="Test",
    )
    result = FuzzResult(
        strategy=FuzzStrategy.BOUNDARY,
        operation=op,
        payload={"field": "value"},
        status_code=500,
        response_body="Internal Server Error",
        response_time_ms=100,
        is_failure=True,
        failure_reason="server_error",
    )
    assert result.is_failure
    assert result.status_code == 500


def test_openapi_fuzz_report_to_fragments() -> None:
    """Report converts to EvidenceFragments."""
    op = ApiOperation(
        method="POST",
        path="/test",
        operation_id="testOp",
        summary="Test",
    )
    result = FuzzResult(
        strategy=FuzzStrategy.BOUNDARY,
        operation=op,
        payload={"field": "value"},
        status_code=500,
        response_body="error",
        response_time_ms=50,
        is_failure=True,
        failure_reason="server_error",
    )
    report = OpenAPIFuzzReport(
        spec_path=Path("spec.yaml"),
        base_url="http://localhost",
        results=[result],
    )
    fragments = report.to_fragments()
    assert len(fragments) == 1
    assert fragments[0].fragment_type == "http"
    assert fragments[0].head is not None
    assert fragments[0].head["strategy"] == "boundary"


def test_openapi_fuzzer_init() -> None:
    """Fuzzer initializes with spec and base URL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = Path(tmpdir) / "spec.yaml"
        spec_path.write_text("openapi: '3.0.0'\npaths: {}\n", encoding="utf-8")
        fuzzer = OpenAPIFuzzer(spec_path=spec_path, base_url="http://localhost:8080")
        assert fuzzer.base_url == "http://localhost:8080"
        assert fuzzer.spec_path == spec_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
