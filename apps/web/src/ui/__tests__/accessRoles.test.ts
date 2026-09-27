import { describe, expect, it } from "vitest";
import {
  AUDIT_ROLES,
  BILLING_ROLES,
  IDENTITY_ROLES,
  roleSetAllows,
} from "../accessRoles";

// The three sets themselves are re-derived from the RBAC matrix by
// tests/unit/test_access_role_parity.py; what is locked here is the decision the
// sidebar makes with them, because App.tsx's filter is the only thing standing
// between a role and a page it cannot load. The rule that is easy to get wrong
// and impossible to see in a screenshot: a principal with no roles at all must
// be treated as holding none, not as unrestricted.

describe("roleSetAllows", () => {
  it("admits a principal holding one of the allowed roles", () => {
    expect(roleSetAllows(["operator"], IDENTITY_ROLES)).toBe(true);
    expect(roleSetAllows(["auditor"], AUDIT_ROLES)).toBe(true);
    expect(roleSetAllows(["auditor"], BILLING_ROLES)).toBe(true);
  });

  it("refuses a principal holding none of them", () => {
    expect(roleSetAllows(["viewer"], IDENTITY_ROLES)).toBe(false);
    expect(roleSetAllows(["operator"], AUDIT_ROLES)).toBe(false);
    expect(roleSetAllows(["viewer"], BILLING_ROLES)).toBe(false);
  });

  it("refuses when the principal has no role list at all", () => {
    // /auth/me may answer with a principal whose roles never arrived; showing
    // the admin pages anyway would advertise exactly what the server refuses.
    expect(roleSetAllows(undefined, IDENTITY_ROLES)).toBe(false);
    expect(roleSetAllows(null, AUDIT_ROLES)).toBe(false);
    expect(roleSetAllows([], BILLING_ROLES)).toBe(false);
  });

  it("keeps the audit gate narrower than the identity one on purpose", () => {
    // operator manages users and tokens but must not read the audit trail; the
    // asymmetry comes from ROLE_MATRIX (auditor holds admin:audit, operator does
    // not), and harmonising the two sets is the bug this locks out.
    expect(IDENTITY_ROLES).toContain("operator");
    expect(BILLING_ROLES).toContain("operator");
    expect(AUDIT_ROLES).not.toContain("operator");
    expect(AUDIT_ROLES).toContain("auditor");
  });
});
