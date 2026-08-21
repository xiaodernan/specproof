"""§6.10 permission evaluation — default-deny.

§6.10: plugins have no network or host access by default; an enterprise
admin must explicitly approve before a plugin is enabled. The protocol
mirrors that as default-deny evaluation:

- unknown permission names are denied (never inferred);
- permissions the manifest did not declare are denied;
- sensitive permissions (network. / host. / secrets.) additionally
  require an explicit admin approval, even when declared.

evaluate_permission() is a pure function of the validated manifest and
optional admin approvals — no ambient state, no network.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from plugins.manifest import PLUGIN_PERMISSION_NAMES, Manifest, PluginPermission

#: Permission prefixes §6.10 reserves for explicit admin approval.
SENSITIVE_PREFIXES: tuple[str, ...] = ("network.", "host.", "secrets.")


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """Verdict for one permission request (granted or denied, with a reason)."""

    requested: str
    granted: bool
    reason: str
    declared: bool
    requires_admin_approval: bool


def _permission_name(permission: PluginPermission | str) -> str:
    return permission.value if isinstance(permission, PluginPermission) else permission


def _sensitive(name: str) -> bool:
    return name.startswith(SENSITIVE_PREFIXES)


def evaluate_permission(
    manifest: Manifest,
    permission: PluginPermission | str,
    *,
    admin_approvals: Collection[str] | None = None,
) -> PermissionDecision:
    """Default-deny evaluation of one permission request.

    admin_approvals is the set of sensitive permission names an
    administrator has explicitly approved for this plugin; when None (the
    default) no sensitive permission can be granted.
    """
    name = _permission_name(permission)
    sensitive = _sensitive(name)
    if name not in PLUGIN_PERMISSION_NAMES:
        return PermissionDecision(name, False, "unknown_permission", False, sensitive)
    declared = PluginPermission(name) in manifest.permissions
    if not declared:
        return PermissionDecision(name, False, "not_declared", False, sensitive)
    approvals = admin_approvals if admin_approvals is not None else frozenset()
    if sensitive and name not in approvals:
        return PermissionDecision(name, False, "requires_admin_approval", True, True)
    return PermissionDecision(name, True, "granted", True, sensitive)


def evaluate_permissions(
    manifest: Manifest,
    permissions: Iterable[PluginPermission | str],
    *,
    admin_approvals: Collection[str] | None = None,
) -> dict[str, PermissionDecision]:
    """Evaluate many permission requests at once (one decision per name)."""
    decisions: dict[str, PermissionDecision] = {}
    for permission in permissions:
        decision = evaluate_permission(
            manifest, permission, admin_approvals=admin_approvals
        )
        decisions[decision.requested] = decision
    return decisions
