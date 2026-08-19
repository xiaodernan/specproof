"""§6.10 plugin-protocol unit tests (protocol only — no marketplace runtime).

Covers the five required scenarios: a valid manifest validates; a missing
permission is default-denied; an unsigned manifest is honestly marked
unsigned; a bad schema is rejected; resource caps are parsed (with
fail-closed defaults). No network, no plugin execution.
"""

import base64
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from plugins import (
    KeyNotFoundError,
    ManifestValidationError,
    PluginKind,
    PluginPermission,
    ResourceLimits,
    SignatureStatus,
    check_manifest_signature,
    evaluate_permission,
    evaluate_permissions,
    parse_resource_limits,
    validate_manifest,
)
from plugins.manifest import DEFAULT_RESOURCE_LIMITS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_MANIFEST = PROJECT_ROOT / "plugins" / "fixtures" / "example_checker_manifest.json"
EXAMPLE_INPUT = PROJECT_ROOT / "plugins" / "fixtures" / "example_checker_input.json"
PLUGIN_ID = "com.example.checkers.auth-annotation-audit"


def _load_example() -> dict[str, Any]:
    return json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))


def _valid_manifest(**overrides: Any) -> dict[str, Any]:
    data = _load_example()
    data.update(overrides)
    return data


def _malformed_input_schema(data: dict[str, Any]) -> None:
    data["input_schema"] = {"type": "object", "properties": "not-an-object"}


def _signature_missing_key_id(data: dict[str, Any]) -> None:
    data["signature"] = {
        "algorithm": "ed25519",
        "signed_payload_version": 1,
        "value": "AA==",
    }


def _signature_unknown_algorithm(data: dict[str, Any]) -> None:
    data["signature"] = {
        "algorithm": "md5",
        "key_id": "key-001",
        "signed_payload_version": 1,
        "value": "AA==",
    }


def _signed_manifest() -> dict[str, Any]:
    return _valid_manifest(
        signature={
            "algorithm": "ed25519",
            "key_id": "key-001",
            "signed_payload_version": 1,
            "value": base64.b64encode(b"example-signature").decode("ascii"),
        }
    )


class _AcceptingVerifier:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []

    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        self.payloads.append(payload)
        return True


class _RejectingVerifier:
    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        return False


class _MissingKeyVerifier:
    def verify(self, payload: bytes, signature: bytes, key_id: str) -> bool:
        raise KeyNotFoundError(key_id)


def test_valid_example_manifest_validates() -> None:
    manifest = validate_manifest(_load_example())
    assert manifest.manifest_version == "1.0"
    assert manifest.id == PLUGIN_ID
    assert manifest.version == "1.2.0"
    assert manifest.kind is PluginKind.CHECKER
    assert manifest.permissions == (PluginPermission.FILESYSTEM_READ_WORKSPACE,)
    assert manifest.signature is None
    assert manifest.resource_limits == ResourceLimits(
        memory_mb=512,
        wall_clock_seconds=300,
        max_input_bytes=1048576,
        max_output_bytes=1048576,
        max_file_writes=0,
    )
    assert set(manifest.compatibility) == {"specproof", "python"}
    assert manifest.compatibility["specproof"].min_version == "0.1.0"
    assert manifest.compatibility["specproof"].max_version == "2.0.0"
    input_fixture = json.loads(EXAMPLE_INPUT.read_text(encoding="utf-8"))
    assert set(input_fixture) == {"repository", "base_sha", "head_sha"}


def test_missing_permission_is_denied() -> None:
    manifest = validate_manifest(_valid_manifest())

    declared = evaluate_permission(manifest, "filesystem.read:workspace")
    assert declared.granted and declared.reason == "granted"

    missing = evaluate_permission(manifest, "filesystem.write:workspace")
    assert not missing.granted
    assert missing.reason == "not_declared"

    unknown = evaluate_permission(manifest, "filesystem.read:/etc")
    assert not unknown.granted
    assert unknown.reason == "unknown_permission"

    # §6.10: network/host stay denied even when declared, until admin approves.
    networked = validate_manifest(
        _valid_manifest(
            permissions=["filesystem.read:workspace", "network.egress"]
        )
    )
    denied = evaluate_permission(networked, "network.egress")
    assert not denied.granted
    assert denied.reason == "requires_admin_approval"

    approved = evaluate_permission(
        networked, "network.egress", admin_approvals=frozenset({"network.egress"})
    )
    assert approved.granted

    decisions = evaluate_permissions(
        networked, ["filesystem.read:workspace", "network.egress"]
    )
    assert decisions["network.egress"].reason == "requires_admin_approval"


def test_unsigned_manifest_is_marked_unsigned() -> None:
    manifest = validate_manifest(_valid_manifest())
    result = check_manifest_signature(manifest, verifier=None)
    assert result.status is SignatureStatus.UNSIGNED
    assert result.key_id is None
    assert "no signature" in result.detail

    signed_manifest = validate_manifest(_signed_manifest())

    no_verifier = check_manifest_signature(signed_manifest, verifier=None)
    assert no_verifier.status is SignatureStatus.UNSIGNED
    assert no_verifier.key_id == "key-001"
    assert "not checked" in no_verifier.detail

    # Missing key is an honest "cannot check" — never INVALID.
    missing_key = check_manifest_signature(signed_manifest, _MissingKeyVerifier())
    assert missing_key.status is SignatureStatus.UNSIGNED
    assert missing_key.key_id == "key-001"
    assert "key-001" in missing_key.detail

    accepting = _AcceptingVerifier()
    signed_ok = check_manifest_signature(signed_manifest, accepting)
    assert signed_ok.status is SignatureStatus.SIGNED
    payload = json.loads(accepting.payloads[0])
    assert payload["id"] == PLUGIN_ID
    assert "signature" not in payload

    invalid = check_manifest_signature(signed_manifest, _RejectingVerifier())
    assert invalid.status is SignatureStatus.INVALID
    assert "mismatch" in invalid.detail


_BAD_MANIFEST_MUTATIONS: list[tuple[str, Callable[[dict[str, Any]], None]]] = [
    ("missing id", lambda data: data.pop("id")),
    ("unknown kind", lambda data: data.update(kind="wizard")),
    ("permissions not a list", lambda data: data.update(permissions="filesystem.read:workspace")),
    ("unknown permission", lambda data: data.update(permissions=["network.egress:anywhere"])),
    ("input_schema malformed", _malformed_input_schema),
    ("signature missing key_id", _signature_missing_key_id),
    ("signature unknown algorithm", _signature_unknown_algorithm),
    ("negative memory cap", lambda data: data.update(resource_limits={"memory_mb": -1})),
    ("empty compatibility", lambda data: data.update(compatibility={})),
    ("unknown top-level field", lambda data: data.update(plugin_hooks=[])),
]


@pytest.mark.parametrize(
    ("label", "mutate"),
    _BAD_MANIFEST_MUTATIONS,
    ids=[entry[0] for entry in _BAD_MANIFEST_MUTATIONS],
)
def test_bad_schema_is_rejected(label: str, mutate: Callable[[dict[str, Any]], None]) -> None:
    data = _valid_manifest()
    mutate(data)
    with pytest.raises(ManifestValidationError) as exc_info:
        validate_manifest(data)
    assert exc_info.value.errors, label + ": expected validation errors"


def test_resource_caps_are_parsed() -> None:
    explicit = parse_resource_limits(
        {
            "memory_mb": 1024,
            "wall_clock_seconds": 120,
            "max_input_bytes": 512,
            "max_output_bytes": 256,
            "max_file_writes": 4,
        }
    )
    assert explicit == ResourceLimits(1024, 120, 512, 256, 4)

    assert parse_resource_limits({}) == DEFAULT_RESOURCE_LIMITS

    for bad in (
        {"memory_mb": -1},
        {"wall_clock_seconds": "60"},
        {"max_file_writes": -1},
        {"max_output_bytes": 1.5},
        {"unknown_cap": 1},
    ):
        with pytest.raises(ManifestValidationError):
            parse_resource_limits(bad)

    no_caps = _valid_manifest()
    no_caps.pop("resource_limits")
    assert validate_manifest(no_caps).resource_limits == DEFAULT_RESOURCE_LIMITS
