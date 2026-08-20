// TypeScript cross-language sample: auth-guarded email change.
// Base revision keeps the authorization guard in changeEmail.

export type User = { id: string; role: "admin" | "user" };

export function isAuthorized(user: User | null, requiredRole: "admin" | "user"): boolean {
  if (user === null) return false;
  if (user.role !== requiredRole) return false;
  return true;
}

export function changeEmail(user: User | null, newEmail: string): string {
  if (!isAuthorized(user, "user")) {
    return "UNAUTHORIZED";
  }
  return `EMAIL_CHANGED:${newEmail}`;
}
