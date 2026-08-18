# Case 83: Per-User Orders Fetch Loop (N+1)

GET /api/users must not load orders with a per-user query loop (N+1).

## Acceptance Criteria
1. The list must be served in at most 3 SQL queries for any number of users.
