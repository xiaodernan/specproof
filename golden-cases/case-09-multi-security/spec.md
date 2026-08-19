# Case 09: Multiple Security Annotations Removed

Two unrelated protections are removed in a single PR: the authentication
guard on the change-email endpoint (@PreAuthorize) and the transaction
boundary around the email update (@Transactional on
UserService.changeEmail).

## Acceptance Criteria
1. Unauthenticated PUT /api/users/{id}/email must be rejected with 401 and
   must not modify the stored email.
2. The email update must run inside a transaction so a mid-update failure
   cannot leave partial writes.
