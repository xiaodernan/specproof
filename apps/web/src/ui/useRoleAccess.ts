import { useEffect, useRef, useState } from "react";
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
  // #121: the session's user_id once /auth/me has answered for this mount, or null
  // when it failed or there is no principal. A reader that must record WHO voted uses
  // this when `checked` is already true, and awaits `identity` when it is not: a
  // reviewer who clicked faster than /auth/me answered was being counted under their
  // local name, so one human showed up in acceptance_rate as several.
  userId: string | null;
  identity: Promise<string | null>;
};

export function useRoleAccess(allowedRoles: readonly string[]): RoleAccess {
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [checked, setChecked] = useState(false);
  const settleRef = useRef<(id: string | null) => void>(() => {});
  const [identity] = useState(
    () =>
      new Promise<string | null>((resolve) => {
        settleRef.current = resolve;
      })
  );

  useEffect(() => {
    let alive = true;
    let sessionId: string | null = null;
    Promise.resolve()
      .then(() => getAuthMe())
      .then((me) => {
        if (me && me.principal) {
          sessionId = me.principal.user_id;
          if (alive) setPrincipal(me.principal);
        }
      })
      .catch(() => {
        // unknown identity: stay fail-open, the server still refuses
      })
      .finally(() => {
        // Resolved even when this component unmounted: the promise is per-mount, and
        // a vote that is already awaiting it must not hang because the page moved on.
        settleRef.current(sessionId);
        if (alive) setChecked(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const roles = principal ? principal.roles : null;
  const known = checked && Array.isArray(roles);
  const userId = principal ? principal.user_id : null;
  return {
    checked,
    known,
    allowed: !known || roleSetAllows(roles ?? [], allowedRoles),
    userId,
    identity,
  };
}
