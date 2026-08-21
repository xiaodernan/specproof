"""§6.10 manifest validation — fail-closed structural checks.

validate_manifest() enforces the manifest schema declared in
plugins/manifest.py: identity fields, kind, declared permissions,
input/output JSON schemas, the signature block (algorithm / key_id /
signed_payload_version / value are required whenever a signature is
present), the compatibility matrix and resource caps.

Unknown fields, unknown permissions, malformed subschemas and invalid
caps are rejected, never ignored — a manifest that fails validation must
never be loaded by a marketplace runtime.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from plugins.manifest import (
    DEFAULT_RESOURCE_LIMITS,
    DEFAULT_SIGNED_FIELDS,
    MANIFEST_SCHEMA_VERSION,
    PLUGIN_PERMISSION_NAMES,
    SIGNATURE_ALGORITHMS,
    SIGNED_PAYLOAD_VERSION,
    Manifest,
    PluginKind,
    PluginPermission,
    ResourceLimits,
    SignatureBlock,
    VersionRequirement,
)

_ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}")
_VERSION_RE = re.compile(r"(0|[1-9][0-9]*).(0|[1-9][0-9]*).(0|[1-9][0-9]*)")
_JSON_SCHEMA_TYPES = frozenset(
    {"null", "boolean", "object", "array", "number", "integer", "string"}
)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "manifest_version",
        "id",
        "version",
        "kind",
        "name",
        "description",
        "permissions",
        "input_schema",
        "output_schema",
        "signature",
        "compatibility",
        "resource_limits",
    }
)
_SIGNATURE_FIELDS = frozenset(
    {"algorithm", "key_id", "signed_payload_version", "value", "signed_fields"}
)
_SIGNABLE_FIELDS = _TOP_LEVEL_FIELDS - {"signature"}
_LIMIT_FIELDS = frozenset(
    {
        "memory_mb",
        "wall_clock_seconds",
        "max_input_bytes",
        "max_output_bytes",
        "max_file_writes",
    }
)


class ManifestValidationError(ValueError):
    """Raised when a manifest document fails protocol validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = list(errors) if errors is not None else []


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _require_str(
    data: Mapping[str, Any], key: str, errors: list[str], *, prefix: str = ""
) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        _error(errors, f"{prefix}{key}: expected a string, got {type(value).__name__}")
        return ""
    return value


def _require_nonempty_str(
    data: Mapping[str, Any], key: str, errors: list[str], *, prefix: str = ""
) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        _error(errors, f"{prefix}{key}: expected a string, got {type(value).__name__}")
        return ""
    if value == "":
        _error(errors, f"{prefix}{key}: must not be empty")
    return value


def _require_mapping(
    data: Mapping[str, Any], key: str, errors: list[str]
) -> dict[str, Any] | None:
    value = data.get(key)
    if value is None:
        _error(errors, f"{key}: is required")
        return None
    if not isinstance(value, dict):
        _error(errors, f"{key}: expected an object, got {type(value).__name__}")
        return None
    return value


def _require_list_of_str(
    data: Mapping[str, Any], key: str, errors: list[str], *, prefix: str = ""
) -> list[str]:
    value = data.get(key)
    if value is None:
        _error(errors, f"{prefix}{key}: is required")
        return []
    if not isinstance(value, list):
        _error(errors, f"{prefix}{key}: expected an array, got {type(value).__name__}")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            _error(
                errors,
                f"{prefix}{key}[{index}]: expected a string, "
                f"got {type(item).__name__}",
            )
        else:
            result.append(item)
    return result


def _valid_schema_type(schema_type: Any) -> bool:
    if isinstance(schema_type, str):
        return schema_type in _JSON_SCHEMA_TYPES
    if isinstance(schema_type, list):
        return bool(schema_type) and all(
            isinstance(entry, str) and entry in _JSON_SCHEMA_TYPES
            for entry in schema_type
        )
    return False


def _check_json_schema_shape(value: dict[str, Any], label: str, errors: list[str]) -> None:
    schema_type = value.get("type")
    if schema_type is not None and not _valid_schema_type(schema_type):
        _error(
            errors,
            f"{label}.type: expected a JSON-schema type name or an array of them",
        )
    properties = value.get("properties")
    if properties is not None and not isinstance(properties, dict):
        _error(errors, f"{label}.properties: expected an object of subschemas")
    elif isinstance(properties, dict):
        for prop_name, subschema in properties.items():
            if not isinstance(subschema, dict):
                _error(
                    errors,
                    f"{label}.properties.{prop_name}: expected an object subschema",
                )
    required = value.get("required")
    if required is not None and not (
        isinstance(required, list)
        and all(isinstance(item, str) and item for item in required)
    ):
        _error(errors, f"{label}.required: expected an array of property-name strings")
    items = value.get("items")
    if items is not None and not isinstance(items, dict):
        _error(errors, f"{label}.items: expected an object subschema")
    ref = value.get("$ref")
    if ref is not None and not isinstance(ref, str):
        _error(errors, f"{label}.$ref: expected a string")


def _version_tuple(text: str) -> tuple[int, int, int]:
    major, minor, patch = text.split(".")
    return (int(major), int(minor), int(patch))


def parse_resource_limits(data: Mapping[str, Any]) -> ResourceLimits:
    """Parse resource caps; raise ManifestValidationError on unknown/invalid keys.

    Absent keys fall back to DEFAULT_RESOURCE_LIMITS.
    """
    errors: list[str] = []
    values: dict[str, int] = {}
    for key, value in data.items():
        if key not in _LIMIT_FIELDS:
            _error(errors, f"resource_limits.{key}: unknown limit key")
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            _error(
                errors,
                f"resource_limits.{key}: expected an integer, "
                f"got {type(value).__name__}",
            )
            continue
        minimum = 0 if key == "max_file_writes" else 1
        if value < minimum:
            _error(errors, f"resource_limits.{key}: must be >= {minimum}, got {value}")
            continue
        values[key] = value
    if errors:
        raise ManifestValidationError("resource limits are invalid", errors)
    return replace(DEFAULT_RESOURCE_LIMITS, **values)


def _validate_signature(value: Any, errors: list[str]) -> SignatureBlock | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _error(errors, f"signature: expected an object, got {type(value).__name__}")
        return None
    for key in value:
        if key not in _SIGNATURE_FIELDS:
            _error(errors, f"signature: unknown field {key!r}")

    algorithm = _require_nonempty_str(value, "algorithm", errors, prefix="signature.")
    if algorithm and algorithm not in SIGNATURE_ALGORITHMS:
        _error(
            errors,
            f"signature.algorithm: must be one of {sorted(SIGNATURE_ALGORITHMS)}",
        )
    key_id = _require_nonempty_str(value, "key_id", errors, prefix="signature.")
    signature_value = _require_nonempty_str(value, "value", errors, prefix="signature.")

    signed_payload_version: int | None = None
    raw_version = value.get("signed_payload_version")
    if raw_version is None:
        _error(errors, "signature.signed_payload_version: is required")
    elif isinstance(raw_version, bool) or not isinstance(raw_version, int):
        _error(
            errors,
            "signature.signed_payload_version: expected an integer, "
            f"got {type(raw_version).__name__}",
        )
    elif raw_version != SIGNED_PAYLOAD_VERSION:
        _error(
            errors,
            f"signature.signed_payload_version: expected {SIGNED_PAYLOAD_VERSION}, "
            f"got {raw_version}",
        )
    else:
        signed_payload_version = raw_version

    signed_fields = DEFAULT_SIGNED_FIELDS
    if "signed_fields" in value:
        entries = _require_list_of_str(
            value, "signed_fields", errors, prefix="signature."
        )
        if not entries:
            _error(errors, "signature.signed_fields: must not be empty")
        unknown_fields = sorted(set(entries) - _SIGNABLE_FIELDS)
        if unknown_fields:
            _error(errors, f"signature.signed_fields: unknown field(s) {unknown_fields}")
        if len(set(entries)) != len(entries):
            _error(errors, "signature.signed_fields: duplicate entries")
        signed_fields = tuple(entries)

    if errors:
        return None
    assert signed_payload_version is not None
    return SignatureBlock(
        algorithm=algorithm,
        key_id=key_id,
        signed_payload_version=signed_payload_version,
        value=signature_value,
        signed_fields=signed_fields,
    )


def _validate_compatibility(
    value: Any, errors: list[str]
) -> dict[str, VersionRequirement]:
    if value is None:
        _error(errors, "compatibility: is required")
        return {}
    if not isinstance(value, dict):
        _error(errors, f"compatibility: expected an object, got {type(value).__name__}")
        return {}
    if not value:
        _error(errors, "compatibility: must declare at least one engine")
        return {}
    matrix: dict[str, VersionRequirement] = {}
    for engine, spec in value.items():
        if not isinstance(engine, str) or not engine:
            _error(
                errors,
                f"compatibility: engine name must be a non-empty string, "
                f"got {engine!r}",
            )
            continue
        if not isinstance(spec, dict):
            _error(
                errors,
                f"compatibility.{engine}: expected an object, got {type(spec).__name__}",
            )
            continue
        for key in spec:
            if key not in ("min_version", "max_version"):
                _error(errors, f"compatibility.{engine}: unknown field {key!r}")
        min_version = _require_nonempty_str(
            spec, "min_version", errors, prefix=f"compatibility.{engine}."
        )
        if min_version and not _VERSION_RE.fullmatch(min_version):
            _error(errors, f"compatibility.{engine}.min_version: expected semver x.y.z")
        max_version: str | None = None
        if "max_version" in spec:
            max_version = _require_nonempty_str(
                spec, "max_version", errors, prefix=f"compatibility.{engine}."
            )
            if max_version and not _VERSION_RE.fullmatch(max_version):
                _error(
                    errors,
                    f"compatibility.{engine}.max_version: expected semver x.y.z",
                )
        if (
            min_version
            and max_version
            and _VERSION_RE.fullmatch(min_version)
            and _VERSION_RE.fullmatch(max_version)
            and _version_tuple(min_version) > _version_tuple(max_version)
        ):
            _error(errors, f"compatibility.{engine}: min_version exceeds max_version")
        matrix[engine] = VersionRequirement(
            min_version=min_version, max_version=max_version
        )
    return matrix


def validate_manifest(data: object) -> Manifest:
    """Validate a manifest document, raising ManifestValidationError with all errors."""
    if not isinstance(data, Mapping):
        raise ManifestValidationError(
            "manifest must be a JSON object",
            [f"root: expected an object, got {type(data).__name__}"],
        )
    raw = dict(data)
    errors: list[str] = []
    for key in raw:
        if key not in _TOP_LEVEL_FIELDS:
            _error(errors, f"unknown field {key!r}")

    manifest_version = _require_nonempty_str(raw, "manifest_version", errors)
    if manifest_version and manifest_version != MANIFEST_SCHEMA_VERSION:
        _error(
            errors,
            f"manifest_version: expected {MANIFEST_SCHEMA_VERSION!r}, "
            f"got {manifest_version!r}",
        )

    plugin_id = _require_nonempty_str(raw, "id", errors)
    if plugin_id and not _ID_RE.fullmatch(plugin_id):
        _error(errors, f"id: must match {_ID_RE.pattern}")

    version = _require_nonempty_str(raw, "version", errors)
    if version and not _VERSION_RE.fullmatch(version):
        _error(errors, "version: expected semver x.y.z without prerelease/build tags")

    name = ""
    if "name" in raw:
        name = _require_nonempty_str(raw, "name", errors)
    description = ""
    if "description" in raw:
        description = _require_str(raw, "description", errors)

    kind: PluginKind | None = None
    kind_raw = _require_nonempty_str(raw, "kind", errors)
    if kind_raw:
        try:
            kind = PluginKind(kind_raw)
        except ValueError:
            _error(
                errors,
                f"kind: must be one of {sorted(kind.value for kind in PluginKind)}",
            )

    permissions: list[PluginPermission] = []
    for entry in _require_list_of_str(raw, "permissions", errors):
        if entry not in PLUGIN_PERMISSION_NAMES:
            _error(errors, f"permissions: unknown permission {entry!r} (not in catalog)")
            continue
        permissions.append(PluginPermission(entry))
    if len(set(permissions)) != len(permissions):
        _error(errors, "permissions: duplicate entries")

    input_schema = _require_mapping(raw, "input_schema", errors)
    if input_schema is not None:
        _check_json_schema_shape(input_schema, "input_schema", errors)
    output_schema = _require_mapping(raw, "output_schema", errors)
    if output_schema is not None:
        _check_json_schema_shape(output_schema, "output_schema", errors)

    signature = _validate_signature(raw.get("signature"), errors)
    compatibility = _validate_compatibility(raw.get("compatibility"), errors)

    resource_limits = DEFAULT_RESOURCE_LIMITS
    raw_limits = raw.get("resource_limits")
    if raw_limits is not None and not isinstance(raw_limits, dict):
        _error(
            errors,
            f"resource_limits: expected an object, got {type(raw_limits).__name__}",
        )
    elif isinstance(raw_limits, dict):
        try:
            resource_limits = parse_resource_limits(raw_limits)
        except ManifestValidationError as exc:
            errors.extend(exc.errors)

    if errors:
        label = plugin_id or "<unknown>"
        raise ManifestValidationError(
            f"manifest {label!r} is invalid: {len(errors)} error(s)",
            errors,
        )
    assert kind is not None
    assert input_schema is not None
    assert output_schema is not None
    return Manifest(
        manifest_version=manifest_version,
        id=plugin_id,
        version=version,
        kind=kind,
        name=name,
        description=description,
        permissions=tuple(permissions),
        input_schema=input_schema,
        output_schema=output_schema,
        signature=signature,
        compatibility=compatibility,
        resource_limits=resource_limits,
        raw=raw,
    )
