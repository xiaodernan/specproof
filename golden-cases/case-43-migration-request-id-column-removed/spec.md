# Case 43: Order Request Id Column Removed

The orders.request_id column must not be removed - it backs the idempotency dedup.

## Acceptance Criteria
1. The orders.request_id column must not be removed.
