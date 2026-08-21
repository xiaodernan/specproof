"""Request-scoped tenant isolation context for the repository layer.

Industrialization phase 1 (docs/architecture/MULTI_TENANT_DESIGN.md §2/§4):
resource queries must enforce tenant filtering in the repository layer, not
via per-route discipline. The tenant auth middleware publishes the
authenticated principal into this ContextVar around the whole request;
MySQLStore methods read it and only then add tenant predicates to their SQL.

Compatibility contract: when the context is unset — single-tenant
deployments, auth disabled, webhook-created jobs — every statement is
byte-identical to the pre-tenant implementation, so the existing API tests
stay green unmodified.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

TENANT_SCOPE_VAR: ContextVar[TenantScope | None] = ContextVar(
    "specproof_tenant_scope", default=None
)


@dataclass(frozen=True)
class TenantScope:
    """The authenticated caller's tenant context for repository queries."""

    tenant_id: str
    user_id: str = ""
    roles: frozenset[str] = field(default_factory=frozenset)

    def is_auditor(self) -> bool:
        """Auditors get the cross-tenant audit view: no tenant predicate."""
        return "auditor" in self.roles


def current_scope() -> TenantScope | None:
    """The active tenant scope, or None when tenant mode is not in play."""
    return TENANT_SCOPE_VAR.get()
