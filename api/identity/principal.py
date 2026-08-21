"""Unified principal and the RBAC matrix (MULTI_TENANT_DESIGN.md §1/§2).

Both credential types — local scoped tokens (sp_*) and OIDC id_tokens — are
exchanged for one Principal {user_id, tenant_id, roles, scopes}. The matrix
below is the authoritative encoding of the design table:

| role     | jobs | cases/certificates | billing | admin            |
|----------|------|--------------------|---------|------------------|
| admin    | 全    | 全                 | 全      | 全               |
| operator | 全    | 读+触发             | 读      | 用户/Token 管理   |
| viewer   | 读    | 读                 | 无      | 无               |
| auditor  | 读    | 读+验签             | 读      | 审计视图          |

Actions per resource: jobs {read, write}; cases {read, trigger, verify};
billing {read}; admin {manage, users, tokens, audit}. "全" (all) is every
action of that resource.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

ROLE_VALUES: tuple[str, ...] = ("admin", "operator", "viewer", "auditor")

JOB_ACTIONS: frozenset[str] = frozenset({"read", "write"})
CASE_ACTIONS: frozenset[str] = frozenset({"read", "trigger", "verify"})
BILLING_ACTIONS: frozenset[str] = frozenset({"read"})
ADMIN_ACTIONS: frozenset[str] = frozenset({"manage", "users", "tokens", "audit"})

ALL_ACTIONS: dict[str, frozenset[str]] = {
    "jobs": JOB_ACTIONS,
    "cases": CASE_ACTIONS,
    "billing": BILLING_ACTIONS,
    "admin": ADMIN_ACTIONS,
}

#: RBAC matrix §2: role -> resource -> allowed actions.
ROLE_MATRIX: dict[str, dict[str, frozenset[str]]] = {
    "admin": {
        "jobs": JOB_ACTIONS,
        "cases": CASE_ACTIONS,
        "billing": BILLING_ACTIONS,
        "admin": ADMIN_ACTIONS,
    },
    "operator": {
        "jobs": JOB_ACTIONS,
        "cases": frozenset({"read", "trigger"}),
        "billing": frozenset({"read"}),
        "admin": frozenset({"users", "tokens"}),
    },
    "viewer": {
        "jobs": frozenset({"read"}),
        "cases": frozenset({"read"}),
        "billing": frozenset(),
        "admin": frozenset(),
    },
    "auditor": {
        "jobs": frozenset({"read"}),
        "cases": frozenset({"read", "verify"}),
        "billing": frozenset({"read"}),
        "admin": frozenset({"audit"}),
    },
}

#: resources the admin column governs (operator: user/token management).
RESOURCES: tuple[str, ...] = ("jobs", "cases", "billing", "admin")


@dataclass(frozen=True)
class Principal:
    """The unified request principal injected into request.state."""

    user_id: str
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "roles": sorted(self.roles),
            "scopes": sorted(self.scopes),
        }


@dataclass(frozen=True)
class ResourceAction:
    """The (resource, action) a request path/method maps onto."""

    resource: str
    action: str


def roles_allowed(roles: Collection[str], resource: str, action: str) -> bool:
    """True when ANY of the caller's roles grants the action on the resource."""
    for role in roles:
        granted = ROLE_MATRIX.get(role, {}).get(resource, frozenset())
        if action in granted:
            return True
    return False


def principal_allowed(principal: Principal, resource: str, action: str) -> bool:
    """RBAC + scope intersection.

    Roles decide the matrix (§2); when a local token carries explicit scopes
    the request must also be covered by them ("resource:action",
    "resource:*" or "*"). Empty scopes (OIDC, unscoped tokens) mean
    "roles decide".
    """
    if not roles_allowed(principal.roles, resource, action):
        return False
    if principal.scopes:
        wanted = (f"{resource}:{action}", f"{resource}:*", "*")
        return any(w in principal.scopes for w in wanted)
    return True


_ADMIN_SUB_RESOURCES: dict[str, str] = {
    "tenants": "manage",
    "users": "users",
    "tokens": "tokens",
    "audit": "audit",
}


def classify_request(method: str, path: str) -> ResourceAction | None:
    """Map an HTTP method + path onto the RBAC matrix.

    Returns None for paths the matrix does not govern (auth/oidc endpoints,
    static assets, the SPA). The mapping is conservative: everything under a
    protected prefix that is not explicitly classified is not blocked here
    (the endpoint itself is still principal-authenticated by the middleware).
    """
    if method == "OPTIONS":
        return None
    if path.startswith("/jobs"):
        action = "read" if method in ("GET", "HEAD") else "write"
        return ResourceAction("jobs", action)
    if path.startswith("/agent"):
        action = "read" if method in ("GET", "HEAD") else "write"
        return ResourceAction("jobs", action)
    if path.startswith("/api/v1/admin/"):
        rest = path[len("/api/v1/admin/"):].split("/", 1)[0]
        sub_action = _ADMIN_SUB_RESOURCES.get(rest)
        if sub_action is None:
            return None
        return ResourceAction("admin", sub_action)
    if path.startswith("/api/v1/billing"):
        return ResourceAction("billing", "read")
    if path.startswith("/api/v1/"):
        action = "read" if method in ("GET", "HEAD") else "trigger"
        return ResourceAction("cases", action)
    return None
