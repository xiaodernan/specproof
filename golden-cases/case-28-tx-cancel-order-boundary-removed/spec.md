# Case 28: Cancel Order Transaction Boundary Removed

Cancelling an order must run inside a transaction so the status change and the stock restore stay atomic.

## Acceptance Criteria
1. Order cancellation must remain @Transactional.
