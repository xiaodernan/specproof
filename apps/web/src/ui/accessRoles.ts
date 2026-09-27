// #112: the role sets that decide whether a governed surface is reachable.
//
// Each set mirrors ONE cell of the RBAC matrix (MULTI_TENANT_DESIGN §2) that the
// server enforces on the calls the surface itself makes: the identity console
// reads admin:users + admin:tokens, the billing console reads billing:read, the
// audit trail reads admin:audit.
// tests/unit/test_access_role_parity.py re-derives every set from
// api/identity/principal.py — ROLE_MATRIX applied to classify_request() over the
// paths these pages actually request — so editing the matrix cannot leave the
// sidebar advertising a page the server would refuse, or hiding a page someone
// can still open. Before that gate the identity and billing sets each existed
// twice (a nav copy in App.tsx and a page copy), and only the audit set was
// shared; a drift between the two copies is invisible to every test that renders
// one side alone.

export const IDENTITY_ROLES: readonly string[] = ["admin", "operator"];
export const BILLING_ROLES: readonly string[] = ["admin", "operator", "auditor"];
export const AUDIT_ROLES: readonly string[] = ["admin", "auditor"];

/** True when the principal holds at least one of `allowed`. */
export function roleSetAllows(
  roles: string[] | undefined | null,
  allowed: readonly string[],
): boolean {
  return Array.isArray(roles) && roles.some(role => allowed.includes(role));
}
