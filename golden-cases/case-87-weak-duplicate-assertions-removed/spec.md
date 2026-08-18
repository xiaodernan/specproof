# Case 87: Duplicate-Rejection Assertions Removed

The repository's own test suite must keep its assertions: the duplicate-email rejection test must keep verifying rejection and stored state.

## Acceptance Criteria
1. Tests must keep asserting the rejection and the unchanged stored email.
