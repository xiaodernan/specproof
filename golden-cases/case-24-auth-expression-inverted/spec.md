# Case 24: Authorization Expression Inverted

The change-email endpoint must require authentication: unauthenticated requests must receive 401 Unauthorized.

## Acceptance Criteria
1. Unauthenticated PUT /api/users/{id}/email must be rejected with 401 and must not modify the stored email.
