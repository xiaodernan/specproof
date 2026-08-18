# Case 86: Users Re-Queried Per User

GET /api/users must not re-query users inside a per-user loop (N+1).

## Acceptance Criteria
1. The list must be served in at most 3 SQL queries.
