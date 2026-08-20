// TypeScript cross-language sample: auth-guarded email change.
// Head revision: changeEmail no longer checks authorization (regression).

export type User = { id: string; role: "admin" | "user" };

export function isAuthorized(user: User | null, requiredRole: "admin" | "user"): boolean {
  if (user === null) return false;
  if (user.role !== requiredRole) return false;
  return true;
}

export function changeEmail(user: User | null, newEmail: string): string {
  return `EMAIL_CHANGED:${newEmail}`;
}
