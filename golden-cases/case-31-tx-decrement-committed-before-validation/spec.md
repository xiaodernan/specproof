# Case 31: Stock Decrement Committed Before Validation

A failed order placement must roll back every stock change: when the quantity exceeds the available stock, the stock must remain unchanged.

## Acceptance Criteria
1. An oversized order must be rejected AND leave the stock exactly as it was.
