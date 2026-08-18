# Case 23: Role Tightened - isAuthenticated AND hasRole(USER)

The change-email endpoint must require authentication: unauthenticated requests must receive 401.

## Acceptance Criteria
1. Unauthenticated requests must be rejected with 401.
