import { useEffect, useState } from "react";
import { PrincipalInfo, getAuthMe } from "../api";
import { roleSetAllows } from "./accessRoles";

// #116: "may this principal run the governed action?" for a single button or
// control, from the same shared role sets the sidebar uses (#112) and the same
// fail-open posture this hook implements: an UNKNOWN identity
// (legacy X-API-Key deployments, /auth/me unreachable) is rendered as allowed,
// because the server enforces the matrix regardless of what this says.
//
// `known` is what the page branches on: it is true only once /auth/me answered
// with a principal that carries a role list. A page that hides a control while
// `known` is false would take the admin's buttons away on a slow first paint.
//
// SINCE #117 THIS IS THE ONLY /auth/me ACCESS BODY in apps/web/src: the three
// page-level copies (useAuditAccess in pages/Audit.tsx, useBillingAccess in
// pages/Billing.tsx, identity/useIdentityAccess.ts) call this hook and keep only
// their own role set. tests/unit/test_access_role_parity.py refuses a fourth copy
// by shape, so the sentence above cannot silently become false again.

export type RoleAccess = {
  checked: boolean;
  known: boolean;
  allowed: boolean;
};

export function useRoleAccess(allowedRoles: readonly string[]): RoleAccess {
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.resolve()
      .then(() => getAuthMe())
      .then((me) => {
        if (alive && me && me.principal) setPrincipal(me.principal);
      })
      .catch(() => {
        // unknown identity: stay fail-open, the server still refuses
      })
      .finally(() => {
        if (alive) setChecked(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const roles = principal ? principal.roles : null;
  const known = checked && Array.isArray(roles);
  return {
    checked,
    known,
    allowed: !known || roleSetAllows(roles ?? [], allowedRoles),
  };
}
