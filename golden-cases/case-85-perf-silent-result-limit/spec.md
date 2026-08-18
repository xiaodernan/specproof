# Case 85: Silent Result Limit

GET /api/users must return every user in a single batched query - no silent truncation.

## Acceptance Criteria
1. The list must contain every registered user.
