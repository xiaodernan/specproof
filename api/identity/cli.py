"""Bootstrap CLI for multi-tenant identity (phase 1 operations).

The API itself is fail-closed: before the first admin exists nobody can
mint tokens. These commands provision the first identity state from the
server environment (SPECPROOF_IDENTITY_URL, SPECPROOF_TOKEN_HMAC_KEY):

  python -m api.identity.cli init-admin <email>
      create tenant 'default' (or SPECPROOF_DEFAULT_TENANT_ID) + admin user

  python -m api.identity.cli mint-token <user_id> [--name NAME] [--scopes S]
      print a show-once sp_* token (S = comma-separated 'resource:action')

  python -m api.identity.cli list-users [--tenant TENANT_ID]

No default HMAC key exists by design: mint-token refuses to run without
SPECPROOF_TOKEN_HMAC_KEY (generate one with, e.g., python -c "import
secrets; print(secrets.token_hex(32))" and keep it in the secret manager).
"""

from __future__ import annotations

import argparse
import sys

from api.identity.store import get_identity_store
from api.identity.tokens import TokenConfigError, mint_token
from storage.identity import IdentityStore


def _default_tenant(store: IdentityStore) -> str:
    import os

    configured = os.getenv("SPECPROOF_DEFAULT_TENANT_ID", "").strip()
    if configured:
        return configured
    tenants = store.list_tenants()
    if tenants:
        return tenants[0].id
    tenant = store.create_tenant(name="default")
    print(f"created tenant default -> {tenant.id}")
    return tenant.id


def _init_admin(email: str) -> None:
    store = get_identity_store()
    tenant_id = _default_tenant(store)
    user = store.create_user(tenant_id=tenant_id, email=email, role="admin")
    print(f"admin user ready: id={user.id} email={user.email} tenant={user.tenant_id}")


def _mint(args: argparse.Namespace) -> None:
    store = get_identity_store()
    try:
        _row, token = mint_token(
            store,
            user_id=args.user_id,
            name=args.name or "bootstrap",
            scopes=args.scopes or "",
            ttl_days=args.ttl_days,
        )
    except TokenConfigError as exc:
        print(f"refusing to mint: {exc}", file=sys.stderr)
        sys.exit(2)
    print("SHOW-ONCE token (it is never stored and cannot be recovered):")
    print(token)


def _list_users(args: argparse.Namespace) -> None:
    store = get_identity_store()
    tenant_id = args.tenant or _default_tenant(store)
    for user in store.list_users(tenant_id):
        print(f"{user.id}  {user.email:40s}  {user.role:10s}  {user.status}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m api.identity.cli", description=__doc__.splitlines()[0],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-admin", help="create the default tenant + admin user")
    p_init.add_argument("email")

    p_mint = sub.add_parser("mint-token", help="print a show-once sp_* token")
    p_mint.add_argument("user_id")
    p_mint.add_argument("--name", default="")
    p_mint.add_argument("--scopes", default="")
    p_mint.add_argument("--ttl-days", type=int, default=None)

    p_list = sub.add_parser("list-users", help="list users of a tenant")
    p_list.add_argument("--tenant", default=None)

    args = parser.parse_args(argv)
    if args.command == "init-admin":
        _init_admin(args.email)
    elif args.command == "mint-token":
        _mint(args)
    elif args.command == "list-users":
        _list_users(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
