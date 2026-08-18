# Case 35: Stock Decremented Off By One

Placing an order must decrement the product stock by exactly the ordered quantity; replaying the same request must not decrement again.

## Acceptance Criteria
1. After an order of quantity 3, the stock must be reduced by exactly 3.
