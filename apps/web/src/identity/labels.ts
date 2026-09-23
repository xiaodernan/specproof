// RBAC role / account-status glosses for the identity pages.
//
// Same contract as ui/toneMap: keep the canonical English token visible and
// append a Chinese gloss, so an admin can still read the exact value the
// backend stored. Unknown values pass through verbatim — never fabricate a
// meaning for a role or status we don't recognize.

const ROLE_CN: Record<string, string> = {
  viewer: "只读查看",
  operator: "操作员",
  auditor: "审计员",
  admin: "管理员",
};

export function roleLabel(role?: string | null): string {
  if (!role) return "—";
  const cn = ROLE_CN[role.toLowerCase()];
  return cn ? cn + " · " + role : role;
}

const USER_STATUS_CN: Record<string, string> = {
  active: "启用",
  disabled: "停用",
};

export function userStatusLabel(status?: string | null): string {
  if (!status) return "—";
  const cn = USER_STATUS_CN[status.toLowerCase()];
  return cn ? cn + " · " + status : status;
}
