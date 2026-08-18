# Case 34: Equivalent Dedup Lookup

Placing an order must be idempotent per requestId: replaying the same request must return the existing order without a second stock decrement.

## Acceptance Criteria
1. Replaying a requestId must not create a second order row or decrement the stock twice.
