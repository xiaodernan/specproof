# Case 82: Per-User Count Loop (N+1)

GET /api/users must be served with a bounded number of SQL queries: per-user count lookups are forbidden.

## Acceptance Criteria
1. The list must be served in at most 3 SQL queries for any number of users.
