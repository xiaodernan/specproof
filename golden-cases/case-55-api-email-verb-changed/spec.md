# Case 55: Email Endpoint Verb Changed PUT -> PATCH

The public API surface must remain backward-compatible: the email change endpoint must keep PUT.

## Acceptance Criteria
1. PUT /api/users/{id}/email must keep its verb.
