import { IDENTITY_ROLES } from "../ui/accessRoles";
import { useRoleAccess } from "../ui/useRoleAccess";

// UI-level visibility gate for the identity console. The role set is the shared
// IDENTITY_ROLES (admin/operator) the sidebar uses for the same route, so the
// two readers of "can I open 团队与权限" cannot disagree.
// It is deliberately fail-open on UNKNOWN identity (legacy X-API-Key mode or
// /auth/me unreachable) so legacy deployments keep the existing behavior;
// the backend always enforces fail-closed regardless of what the UI shows.
export function useIdentityAccess(): { checked: boolean; canManage: boolean } {
  // #117: the getAuthMe/fail-open body is ui/useRoleAccess.ts's now, shared with
  // the sidebar pages and the feedback vote button.
  const access = useRoleAccess(IDENTITY_ROLES);
  return { checked: access.checked, canManage: access.allowed };
}
