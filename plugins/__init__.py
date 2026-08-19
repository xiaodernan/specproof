"""§6.10 plugin-marketplace protocol — manifests, validation, signatures, permissions.

PROTOCOL ONLY: manifest schema + fail-closed validation + honest
signature checking + default-deny permission evaluation for the five
unified plugin kinds (checker, adapter, policy_pack, connector,
exporter). There is no runtime marketplace, no plugin loading and no
network access anywhere in this package.
"""

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
from plugins.permissions import (
    SENSITIVE_PREFIXES,
    PermissionDecision,
    evaluate_permission,
    evaluate_permissions,
)
from plugins.signing import (
    KeyNotFoundError,
    SignatureResult,
    SignatureStatus,
    SignatureVerifier,
    canonical_signed_payload,
    check_manifest_signature,
)
from plugins.validation import (
    ManifestValidationError,
    parse_resource_limits,
    validate_manifest,
)

__all__ = [
    "DEFAULT_RESOURCE_LIMITS",
    "DEFAULT_SIGNED_FIELDS",
    "KeyNotFoundError",
    "MANIFEST_SCHEMA_VERSION",
    "Manifest",
    "ManifestValidationError",
    "PLUGIN_PERMISSION_NAMES",
    "PermissionDecision",
    "PluginKind",
    "PluginPermission",
    "ResourceLimits",
    "SENSITIVE_PREFIXES",
    "SIGNATURE_ALGORITHMS",
    "SIGNED_PAYLOAD_VERSION",
    "SignatureBlock",
    "SignatureResult",
    "SignatureStatus",
    "SignatureVerifier",
    "VersionRequirement",
    "canonical_signed_payload",
    "check_manifest_signature",
    "evaluate_permission",
    "evaluate_permissions",
    "parse_resource_limits",
    "validate_manifest",
]
