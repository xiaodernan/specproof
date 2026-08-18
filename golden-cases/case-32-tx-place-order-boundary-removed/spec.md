# Case 32: Place Order Transaction Boundary Removed

Placing an order must run inside a transaction so the stock decrement, the order row and the event remain atomic.

## Acceptance Criteria
1. Order placement must remain @Transactional.
