# Case 37: Multi-Write Place Order Loses Transaction

Placing an order must run inside a single transaction: the stock decrement and the order insert must be atomic.

## Acceptance Criteria
1. All order placement writes must stay inside one transaction.
