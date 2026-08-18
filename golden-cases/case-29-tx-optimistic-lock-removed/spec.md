# Case 29: Optimistic Lock Removed From Product

Product stock updates must use optimistic concurrency control (@Version): a stale write must be rejected, never silently overwritten.

## Acceptance Criteria
1. Writing a stale stock snapshot must raise an optimistic-lock failure and leave the stock at the first writer's value.
