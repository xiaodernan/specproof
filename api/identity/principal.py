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
    """RBAC + scope intersection."""
    return principal_denial(principal, resource, action) is None


def principal_denial(principal: Principal, resource: str, action: str) -> str | None:
    """Why this request is refused — naming the gate that actually closed.

    Two independent gates can deny the same call, and they have opposite fixes:
    the role matrix (§2) says the *person* may not, while a scoped local token
    says this *credential* may not even though the person may. Reporting a
    scope refusal as a role refusal sends an admin to add roles to a user who
    already had them, which is a privilege change made on a wrong diagnosis.
    """
    if not roles_allowed(principal.roles, resource, action):
        return (
            f"role {sorted(principal.roles)} may not "
            f"{action} on {resource}"
        )
    if principal.scopes:
        wanted = (f"{resource}:{action}", f"{resource}:*", "*")
        if not any(w in principal.scopes for w in wanted):
            return (
                f"token scopes {sorted(principal.scopes)} do not cover "
                f"{resource}:{action}; role {sorted(principal.roles)} does "
                f"allow it, so mint a token with --scopes {resource}:{action}"
            )
    # Empty scopes (OIDC id_tokens, unscoped tokens) mean "roles decide".
    return None



def scope_cells() -> tuple[str, ...]:
    """Every concrete 'resource:action' the matrix knows about."""
    return tuple(
        f"{resource}:{action}"
        for resource in RESOURCES
        for action in sorted(ALL_ACTIONS[resource])
    )


def scope_problems(raw: str) -> list[str]:
    """Human-readable reasons why a scope list grants nothing intended.

    A scope list NARROWS a token: once any scope is present, a request must be
    covered by it (see principal_denial). So a typo — "job:read", "cases:reed" —
    does not just fail to grant what the operator meant, it silently strips
    every permission the credential would otherwise have had, and the holder is
    then refused with a message that correctly says "token scopes [...] do not
    cover ...". Mint time is the only place this can be caught, and the matrix
    is the single source of what a scope may even name.
    """
    problems: list[str] = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        if item == "*":
            continue
        resource, sep, action = item.partition(":")
        if not sep or not resource or not action:
            problems.append(
                f"{item!r} is not a scope: use '*', '<resource>:*' or "
                f"'<resource>:<action>' (resources: {', '.join(RESOURCES)})"
            )
            continue
        if resource not in ALL_ACTIONS:
            problems.append(
                f"{item!r} names unknown resource {resource!r}; "
                f"resources are {', '.join(RESOURCES)}"
            )
            continue
        if action != "*" and action not in ALL_ACTIONS[resource]:
            problems.append(
                f"{item!r} names unknown action {action!r} on {resource!r}; "
                f"{resource} accepts {', '.join(sorted(ALL_ACTIONS[resource]))} or '*'"
            )
            continue
        if item in CELLS_WITHOUT_A_ROUTE:
            problems.append(
                f"'{item}' is not enforced by any route today - "
                + CELLS_WITHOUT_A_ROUTE[item]
            )
    return problems


#: Vocabulary cells that no HTTP request can ever be checked against, each with
#: the reason an operator needs before deciding to mint one.
#:
#: A scope list NARROWS a credential, so minting a cell nobody enforces does not
#: merely fail to add a right - it strips the rights the roles would otherwise
#: have had, and the holder is then refused with a message that names a permission
#: that never existed. `tests/unit/test_rbac_cells_reach_routes.py` reconciles this
#: declaration against the operations the app actually exposes, in both
#: directions, so the list cannot quietly collect a lie either way.
CELLS_WITHOUT_A_ROUTE: dict[str, str] = {
    "cases:verify": (
        "no route is ever classified as cases:verify. The certificate / "
        "rejection-notice endpoint GET /api/v1/jobs/{job_id}/certificate is a "
        "cases:read, and signature verification runs in the CLI verify flow, "
        "which does not consult this matrix. Read the certificate with "
        "cases:read instead."
    ),
}


def mintable_cells() -> tuple[str, ...]:
    """The cells that actually change what a credential can do."""
    return tuple(cell for cell in scope_cells() if cell not in CELLS_WITHOUT_A_ROUTE)

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
