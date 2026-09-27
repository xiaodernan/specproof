import { useEffect, useState } from "react";
import { PrincipalInfo, getAuthMe } from "../api";
import { IDENTITY_ROLES, roleSetAllows } from "../ui/accessRoles";

// UI-level visibility gate for the identity console. The role set is the shared
// IDENTITY_ROLES (admin/operator) the sidebar uses for the same route, so the
// two readers of "can I open 团队与权限" cannot disagree.
// It is deliberately fail-open on UNKNOWN identity (legacy X-API-Key mode or
// /auth/me unreachable) so legacy deployments keep the existing behavior;
// the backend always enforces fail-closed regardless of what the UI shows.
export function useIdentityAccess(): { checked: boolean; canManage: boolean } {
  const [principal, setPrincipal] = useState<PrincipalInfo | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let alive = true;
    getAuthMe()
      .then((me) => {
        if (alive && me && me.principal) setPrincipal(me.principal);
      })
      .catch(() => {
        // unknown identity: render as before (legacy mode answers 503 anyway)
      })
      .finally(() => {
        if (alive) setChecked(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const canManage =
    !checked ||
    principal == null ||
    !Array.isArray(principal.roles) ||
    roleSetAllows(principal.roles, IDENTITY_ROLES);
  return { checked, canManage };
}
