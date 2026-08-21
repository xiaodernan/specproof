"""Multi-tenant identity (industrialization phase 1).

Authentication (local sp_* tokens, OIDC RS256) and authorization (the §2
RBAC matrix) per docs/architecture/MULTI_TENANT_DESIGN.md. The ASGI
TenantAuthMiddleware that wires these into the request lifecycle lives in
api/middleware.py.
"""

from api.identity.authn import authenticate_bearer, provision_oidc_user
from api.identity.config import auth_enabled
from api.identity.oidc import OidcError, OidcValidator, get_oidc_validator
from api.identity.principal import (
    ADMIN_ACTIONS,
    ALL_ACTIONS,
    ROLE_MATRIX,
    ROLE_VALUES,
    Principal,
    classify_request,
    principal_allowed,
    roles_allowed,
)
from api.identity.store import get_identity_store, identity_url
from api.identity.tokens import check_secret, hash_secret, mint_token, verify_local_token

__all__ = [
    "ADMIN_ACTIONS",
    "ALL_ACTIONS",
    "OidcError",
    "OidcValidator",
    "Principal",
    "ROLE_MATRIX",
    "ROLE_VALUES",
    "authenticate_bearer",
    "auth_enabled",
    "check_secret",
    "classify_request",
    "get_identity_store",
    "get_oidc_validator",
    "hash_secret",
    "identity_url",
    "mint_token",
    "principal_allowed",
    "provision_oidc_user",
    "roles_allowed",
    "verify_local_token",
]
