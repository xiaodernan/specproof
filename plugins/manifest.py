"""§6.10 plugin-marketplace manifest model — the protocol's single source of truth.

Guide reference: docs/工业化商业化终极开发指南.md §6.10 — one unified
plugin protocol for Checker, Execution Adapter, Policy Pack, Notification
Connector and Evidence Exporter. Every plugin ships a manifest carrying
identity, version, kind, declared permissions, input/output JSON schemas,
a signature block, a compatibility matrix and resource caps.

This module is the protocol's hub: field names, plugin kinds, the
permission catalog, signature constants and resource-limit defaults are
defined here once and imported everywhere else (validation, signing,
permissions, fixtures, tests). PROTOCOL ONLY — no runtime marketplace,
no plugin loading, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: Current manifest document schema version.
MANIFEST_SCHEMA_VERSION = "1.0"

#: Signature algorithms the protocol accepts today (extensible in a later
#: manifest_version bump).
SIGNATURE_ALGORITHMS: frozenset[str] = frozenset({"ed25519"})

#: Current signed-payload canonicalization version.
SIGNED_PAYLOAD_VERSION = 1


class PluginKind(StrEnum):
    """The five unified plugin kinds of the §6.10 protocol."""

    CHECKER = "checker"
    ADAPTER = "adapter"
    POLICY_PACK = "policy_pack"
    CONNECTOR = "connector"
    EXPORTER = "exporter"


class PluginPermission(StrEnum):
    """The declarable permission catalog.

    Any permission name outside this catalog is denied outright
    (default-deny); see plugins/permissions.py for evaluation.
    """

    FILESYSTEM_READ_WORKSPACE = "filesystem.read:workspace"
    FILESYSTEM_WRITE_WORKSPACE = "filesystem.write:workspace"
    NETWORK_EGRESS = "network.egress"
    NETWORK_EGRESS_GITHUB = "network.egress:github"
    HOST_EXEC = "host.exec"
    SECRETS_READ = "secrets.read"
    STORAGE_READ = "storage.read"
    STORAGE_WRITE = "storage.write"


#: Wire names of every declarable permission (shared by validation and
#: permission evaluation so the catalog has exactly one definition).
PLUGIN_PERMISSION_NAMES: frozenset[str] = frozenset(
    permission.value for permission in PluginPermission
)


@dataclass(frozen=True, slots=True)
class VersionRequirement:
    """One engine's accepted version range (inclusive, semver x.y.z)."""

    min_version: str
    max_version: str | None = None


@dataclass(frozen=True, slots=True)
class SignatureBlock:
    """Signature section of a manifest (all four fields required when present)."""

    algorithm: str
    key_id: str
    signed_payload_version: int
    value: str
    signed_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Resource caps enforced by the runtime.

    Absent caps fall back to DEFAULT_RESOURCE_LIMITS (fail-closed: a
    plugin that declares no caps runs under the tightest defaults).
    """

    memory_mb: int
    wall_clock_seconds: int
    max_input_bytes: int
    max_output_bytes: int
    max_file_writes: int


#: Manifest fields covered by a signature when signed_fields is omitted.
DEFAULT_SIGNED_FIELDS: tuple[str, ...] = (
    "manifest_version",
    "id",
    "version",
    "kind",
    "name",
    "description",
    "permissions",
    "input_schema",
    "output_schema",
    "compatibility",
    "resource_limits",
)

#: Fail-closed resource defaults applied when a manifest omits caps.
DEFAULT_RESOURCE_LIMITS = ResourceLimits(
    memory_mb=256,
    wall_clock_seconds=60,
    max_input_bytes=1_048_576,
    max_output_bytes=1_048_576,
    max_file_writes=0,
)


@dataclass(frozen=True, slots=True)
class Manifest:
    """A validated plugin manifest.

    "raw" keeps the original wire document so signature payloads can be
    canonicalized over exactly what the publisher shipped.
    """

    manifest_version: str
    id: str
    version: str
    kind: PluginKind
    name: str
    description: str
    permissions: tuple[PluginPermission, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    signature: SignatureBlock | None
    compatibility: dict[str, VersionRequirement]
    resource_limits: ResourceLimits
    raw: dict[str, Any]
