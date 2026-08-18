# Case 84: Batched Order Preload

GET /api/users must stay below the query bound even when orders are preloaded in one batch query.

## Acceptance Criteria
1. The list must be served in at most 3 SQL queries.
